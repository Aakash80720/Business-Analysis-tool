"""
Knowledge-graph builder — contextual, LLM-extracted relationships + hyperedges.

Pipeline
--------
1.  **Similarity edges** (cosine on ChromaDB embeddings) — fast, statistical.
2.  **LLM-extracted edges** (via ChatOpenAI) — labeled, directional, business-aware.
3.  **Hyperedges** (LLM) — a single concept connecting 3+ entities.

Dual-mode persistence:
  • Neo4j   → rich traversal + RAG expansion
  • SQL     → Edge / HyperEdge tables (always persisted)
  • In-memory NetworkX fallback for analytics
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import networkx as nx
from sklearn.metrics.pairwise import cosine_similarity

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from ..config import get_settings
from ..prompts import RELATIONSHIP_EXTRACTION_SYSTEM, RELATIONSHIP_EXTRACTION_HUMAN
from ..models.schemas import GraphNode, GraphEdge, HyperEdgeOut

logger = logging.getLogger(__name__)

# Maximum entities sent to the LLM per batch (keeps token count manageable)
_LLM_BATCH_SIZE = 40


# ═══════════════════════════════════════════════════════
#  Knowledge-Graph Builder
# ═══════════════════════════════════════════════════════

class GraphBuilder:
    """
    Constructs a full knowledge graph (nodes, labeled edges, hyperedges)
    from business entities and their embeddings.

    Usage::

        builder = GraphBuilder()
        nodes, edges = builder.build(entity_dicts, chroma_data)
        llm_edges, hyperedges = await builder.extract_relationships(entity_dicts)
    """

    def __init__(self, similarity_threshold: float = 0.75) -> None:
        self._threshold = similarity_threshold

    # ─────────────────────────────────────────────────
    #  In-memory graph (nodes + similarity edges)
    # ─────────────────────────────────────────────────

    def build(
        self,
        entities: List[Dict[str, Any]],
        chroma_data: Optional[List[Dict[str, Any]]] = None,
        extra_edges: Optional[List[GraphEdge]] = None,
        hyperedges: Optional[List[HyperEdgeOut]] = None,
        annotations: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[List[GraphNode], List[GraphEdge]]:
        """
        Build the in-memory graph representation.

        Returns (nodes, edges) — edges include both similarity and any
        ``extra_edges`` (e.g. LLM-extracted labeled relationships).

        ``annotations`` maps entity id → {label, entity_type, properties}
        from the LLM extraction pass.
        """
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        ann = annotations or {}

        emb_lookup: Dict[str, list] = {}
        if chroma_data:
            for cd in chroma_data:
                emb = cd.get("embedding")
                if emb is not None and len(emb) > 0:
                    emb_lookup[cd["id"]] = emb if isinstance(emb, list) else list(emb)

        embeddings: List[np.ndarray] = []
        entity_ids: List[str] = []

        for ent in entities:
            full_content = ent.get("content", "")
            ent_ann = ann.get(ent["id"], {})
            # Use LLM-generated label if available, else derive from content
            label = ent_ann.get("label", "") or full_content[:120]
            # Use refined entity type from LLM if available
            entity_type = ent_ann.get("entity_type", "") or ent.get("entity_type", "Custom")
            # Merge extracted properties into metadata
            properties = ent_ann.get("properties", {})
            base_meta = {
                "document_id": ent.get("document_id", ""),
                "token_count": ent.get("token_count", 0),
            }
            # Properties go into metadata under a 'properties' key and also top-level
            merged_meta = {**base_meta, **properties}

            nodes.append(GraphNode(
                id=ent["id"],
                label=label,
                content=full_content,
                type="entity",
                entity_type=entity_type,
                cluster_id=ent.get("cluster_id"),
                metadata=merged_meta,
                properties=properties,
            ))
            emb = emb_lookup.get(ent["id"])
            if emb is not None and len(emb) > 0:
                embeddings.append(np.array(emb))
                entity_ids.append(ent["id"])

        # Similarity edges
        if len(embeddings) >= 2:
            edges.extend(
                self._compute_similarity_edges(entity_ids, np.array(embeddings))
            )

        # Merge LLM-extracted edges
        if extra_edges:
            edges.extend(extra_edges)

        return nodes, edges

    # ─────────────────────────────────────────────────
    #  Similarity (cosine) edges
    # ─────────────────────────────────────────────────

    def _compute_similarity_edges(
        self,
        ids: List[str],
        embeddings: np.ndarray,
    ) -> List[GraphEdge]:
        sim_matrix = cosine_similarity(embeddings)
        edges: List[GraphEdge] = []
        n = len(ids)
        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i, j] >= self._threshold:
                    edges.append(GraphEdge(
                        source=ids[i],
                        target=ids[j],
                        weight=float(round(sim_matrix[i, j], 4)),
                        edge_type="similarity",
                        relationship_type="similarity",
                    ))
        return edges

    def get_similarity_edge_dicts(
        self,
        entities_with_embeddings: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Return similarity edges as plain dicts for DB / Neo4j insertion."""
        embeddings: List[np.ndarray] = []
        entity_ids: List[str] = []
        for ent in entities_with_embeddings:
            emb = ent.get("embedding")
            if emb is not None and len(emb) > 0:
                embeddings.append(np.array(emb))
                entity_ids.append(ent["id"])

        if len(embeddings) < 2:
            return []

        sim_matrix = cosine_similarity(np.array(embeddings))
        result: List[Dict[str, Any]] = []
        n = len(entity_ids)
        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i, j] >= self._threshold:
                    result.append({
                        "source_entity_id": entity_ids[i],
                        "target_entity_id": entity_ids[j],
                        "confidence": float(round(sim_matrix[i, j], 4)),
                        "relationship_type": "similarity",
                    })
        return result

    # ─────────────────────────────────────────────────
    #  LLM-based relationship extraction
    # ─────────────────────────────────────────────────

    async def extract_relationships(
        self,
        entities: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """
        Use an LLM to extract labeled, directional relationships,
        hyperedges, and per-entity annotations (label, properties, refined type)
        from a list of business entities.

        Parameters
        ----------
        entities : list of dicts with keys ``id``, ``content``, ``entity_type``

        Returns
        -------
        (edges, hyperedges, entity_annotations)

        ``edges``               : [{source_entity_id, target_entity_id, relationship_type,
                                    confidence, explanation}, …]
        ``hyperedges``          : [{label, relationship_type, member_ids:[…],
                                    confidence, explanation}, …]
        ``entity_annotations``  : {entity_id: {label, entity_type, properties:{…}}, …}
        """
        if len(entities) < 2:
            return [], [], {}

        cfg = get_settings()
        llm = ChatOpenAI(
            model=cfg.openai_model,
            api_key=cfg.openai_api_key,
            temperature=0.0,
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", RELATIONSHIP_EXTRACTION_SYSTEM),
            ("human", RELATIONSHIP_EXTRACTION_HUMAN),
        ])
        chain = prompt | llm | StrOutputParser()

        # Collect valid entity ids for validation
        valid_ids = {e["id"] for e in entities}

        all_edges: List[Dict[str, Any]] = []
        all_hyperedges: List[Dict[str, Any]] = []
        all_annotations: Dict[str, Dict[str, Any]] = {}

        # Process in batches to stay within context limits
        for start in range(0, len(entities), _LLM_BATCH_SIZE):
            batch = entities[start: start + _LLM_BATCH_SIZE]
            entities_block = "\n".join(
                f"- id={e['id']}  type={e.get('entity_type', 'Custom')}  "
                f"content=\"{e['content'][:300]}\""
                for e in batch
            )

            try:
                raw = await chain.ainvoke({"entities_block": entities_block})
                parsed = self._parse_llm_json(raw)
            except Exception:
                logger.warning("LLM relationship extraction failed for batch starting at %d", start, exc_info=True)
                continue

            # --- parse entity annotations ---
            for ann in parsed.get("entities", []):
                eid = ann.get("id", "")
                if eid not in valid_ids:
                    continue
                all_annotations[eid] = {
                    "label": ann.get("label", "")[:256],
                    "entity_type": ann.get("entity_type", "Custom"),
                    "properties": ann.get("properties", {}),
                }

            # --- validate & normalise edges ---
            for edge in parsed.get("edges", []):
                src = edge.get("source", "")
                tgt = edge.get("target", "")
                if src not in valid_ids or tgt not in valid_ids or src == tgt:
                    continue
                all_edges.append({
                    "source_entity_id": src,
                    "target_entity_id": tgt,
                    "relationship_type": edge.get("relationship", "related_to"),
                    "confidence": min(max(float(edge.get("confidence", 0.5)), 0.0), 1.0),
                    "explanation": edge.get("explanation", "")[:512],
                })

            # --- validate & normalise hyperedges ---
            for he in parsed.get("hyperedges", []):
                member_ids = [m for m in he.get("member_ids", []) if m in valid_ids]
                if len(member_ids) < 3:
                    continue
                all_hyperedges.append({
                    "label": he.get("label", "")[:512],
                    "relationship_type": he.get("relationship", "related_to"),
                    "member_ids": member_ids,
                    "confidence": min(max(float(he.get("confidence", 0.5)), 0.0), 1.0),
                    "explanation": he.get("explanation", "")[:512],
                })

        return all_edges, all_hyperedges, all_annotations

    # ─────────────────────────────────────────────────
    #  Helpers
    # ─────────────────────────────────────────────────

    @staticmethod
    def _parse_llm_json(raw: str) -> Dict[str, Any]:
        """Robustly parse LLM JSON output, stripping markdown fences if present."""
        text = raw.strip()
        if text.startswith("```"):
            # Remove opening fence (```json or ```)
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        return json.loads(text.strip())

    @staticmethod
    def edges_to_graph_edges(edge_dicts: List[Dict[str, Any]]) -> List[GraphEdge]:
        """Convert raw edge dicts to ``GraphEdge`` schema objects."""
        return [
            GraphEdge(
                source=e["source_entity_id"],
                target=e["target_entity_id"],
                weight=e.get("confidence", 0.5),
                edge_type=e.get("relationship_type", "related_to"),
                relationship_type=e.get("relationship_type", "related_to"),
                explanation=e.get("explanation", ""),
            )
            for e in edge_dicts
        ]

    @staticmethod
    def to_networkx(
        nodes: List[GraphNode],
        edges: List[GraphEdge],
    ) -> nx.Graph:
        """Materialise as a NetworkX graph for analytical queries."""
        G = nx.DiGraph()
        for n in nodes:
            G.add_node(n.id, **n.model_dump())
        for e in edges:
            G.add_edge(
                e.source, e.target,
                weight=e.weight,
                edge_type=e.edge_type,
                relationship_type=e.relationship_type,
            )
        return G
