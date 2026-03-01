"""
Graph builder — constructs a knowledge graph from entities + ChromaDB embeddings.

Dual-mode:
  • If Neo4j is available → persist to Neo4j and query back
  • Fallback             → in-memory NetworkX (original behaviour)

Single Responsibility: translates DB entities → graph data structure.
Embeddings are fetched from ChromaDB (not from SQL).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import networkx as nx
from sklearn.metrics.pairwise import cosine_similarity

from ..config import get_settings
from ..models.schemas import GraphNode, GraphEdge


# ═══════════════════════════════════════════════════════
#  Graph Builder (in-memory fallback + Neo4j integration)
# ═══════════════════════════════════════════════════════

class GraphBuilder:
    """
    Builds a force-directed-graph-ready data structure from entities
    and their embeddings (pulled from ChromaDB).

    Edges are created between entities whose cosine similarity exceeds
    ``similarity_threshold``.
    """

    def __init__(self, similarity_threshold: float = 0.75) -> None:
        self._threshold = similarity_threshold

    def build(
        self,
        entities: List[Dict[str, Any]],
        chroma_data: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[GraphNode], List[GraphEdge]]:
        """
        Build the in-memory graph representation.

        Parameters
        ----------
        entities    : entity dicts (id, content, entity_type, cluster_id, document_id, token_count)
        chroma_data : optional pre-fetched ChromaDB results with embeddings
                      [{id, embedding, …}]

        Returns (nodes, edges).
        """
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []

        # Build embedding lookup from ChromaDB data
        emb_lookup: Dict[str, list] = {}
        if chroma_data:
            for cd in chroma_data:
                if cd.get("embedding"):
                    emb_lookup[cd["id"]] = cd["embedding"]

        # --- entity nodes ---
        embeddings: List[np.ndarray] = []
        entity_ids: List[str] = []

        for ent in entities:
            nodes.append(GraphNode(
                id=ent["id"],
                label=ent["content"][:80],
                type="entity",
                entity_type=ent.get("entity_type", "Custom"),
                cluster_id=ent.get("cluster_id"),
                metadata={
                    "document_id": ent.get("document_id", ""),
                    "token_count": ent.get("token_count", 0),
                },
            ))

            emb = emb_lookup.get(ent["id"])
            if emb:
                embeddings.append(np.array(emb))
                entity_ids.append(ent["id"])

        # --- similarity edges ---
        if len(embeddings) >= 2:
            sim_edges = self._compute_similarity_edges(
                entity_ids, np.array(embeddings),
            )
            edges.extend(sim_edges)

        return nodes, edges

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
                    ))
        return edges

    def get_similarity_edge_dicts(
        self,
        entities_with_embeddings: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Compute similarity edges and return as plain dicts
        for Neo4j batch insertion / Edge record creation.
        """
        embeddings: List[np.ndarray] = []
        entity_ids: List[str] = []
        for ent in entities_with_embeddings:
            if ent.get("embedding"):
                embeddings.append(np.array(ent["embedding"]))
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

    @staticmethod
    def to_networkx(
        nodes: List[GraphNode],
        edges: List[GraphEdge],
    ) -> nx.Graph:
        """Optional: materialise as a NetworkX graph for advanced analytics."""
        G = nx.Graph()
        for n in nodes:
            G.add_node(n.id, **n.model_dump())
        for e in edges:
            G.add_edge(e.source, e.target, weight=e.weight, edge_type=e.edge_type)
        return G
