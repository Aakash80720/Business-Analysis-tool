"""
Neo4j Knowledge Graph Manager — persistent contextual knowledge graph.

Node labels:  Entity (with entity_type property), HyperEdge, Document, Session, UserNote
Relationship types:
  structural  — BELONGS_TO, PART_OF, HAS_DOCUMENT, ANNOTATES
  semantic    — ACHIEVED_BY, MEASURED_BY, THREATENS, SUPPORTS, MITIGATES,
                OWNS, DEPENDS_ON, CONTRADICTS, RELATED_TO
  statistical — SIMILAR_TO, BRIDGES_TO
  hyperedge   — MEMBER_OF_HYPEREDGE
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from neo4j import AsyncGraphDatabase, AsyncDriver

from ..config import get_settings
from ..models.schemas import GraphNode, GraphEdge, HyperEdgeOut

logger = logging.getLogger(__name__)

# Canonical relationship labels that the LLM may produce
_VALID_REL_TYPES = frozenset({
    "achieved_by", "measured_by", "threatens", "supports",
    "mitigates", "owns", "depends_on", "contradicts", "related_to",
    "similarity", "bridge",
})


def _neo4j_rel_type(rel: str) -> str:
    """Convert a lowercase relationship_type to a Neo4j relationship label."""
    r = rel.lower().strip()
    if r not in _VALID_REL_TYPES:
        r = "RELATED_TO"
    return r.upper()


# ═══════════════════════════════════════════════════════
#  Connection Manager (singleton)
# ═══════════════════════════════════════════════════════

class Neo4jManager:
    """Async Neo4j driver lifecycle manager."""

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        if self._driver is not None:
            return
        cfg = get_settings()
        self._driver = AsyncGraphDatabase.driver(
            cfg.neo4j_uri,
            auth=(cfg.neo4j_user, cfg.neo4j_password),
        )
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4j not connected. Call connect() first.")
        return self._driver

    async def ensure_indexes(self) -> None:
        """Create uniqueness constraints and full-text indexes."""
        async with self.driver.session() as s:
            for label in ("Entity", "HyperEdge", "Document", "Session", "UserNote"):
                await s.run(
                    f"CREATE CONSTRAINT IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                )
            # Full-text for entity content search
            await s.run(
                "CREATE FULLTEXT INDEX entityContentIndex IF NOT EXISTS "
                "FOR (e:Entity) ON EACH [e.content]"
            )
            await s.run(
                "CREATE FULLTEXT INDEX noteContentIndex IF NOT EXISTS "
                "FOR (n:UserNote) ON EACH [n.content]"
            )


# Module-level singleton
neo4j_manager = Neo4jManager()


# ═══════════════════════════════════════════════════════
#  Knowledge Graph Service
# ═══════════════════════════════════════════════════════

class KnowledgeGraphService:
    """
    High-level operations on the Neo4j contextual knowledge graph.

    Supports:
    - Entity nodes with ``entity_type`` (Goal, KPI, Risk, …)
    - Labeled directional relationships (ACHIEVED_BY, MEASURED_BY, …)
    - HyperEdge nodes connecting 3+ entities
    - Similarity + bridge statistical edges
    - Graph-enhanced RAG context retrieval
    """

    def __init__(self, manager: Neo4jManager | None = None) -> None:
        self._mgr = manager or neo4j_manager

    # ── Session / Document ──

    async def upsert_session(self, session_id: str, title: str) -> None:
        async with self._mgr.driver.session() as s:
            await s.run(
                "MERGE (sess:Session {id: $id}) SET sess.title = $title",
                id=session_id, title=title,
            )

    async def upsert_document(self, doc_id: str, session_id: str, filename: str) -> None:
        async with self._mgr.driver.session() as s:
            await s.run(
                "MERGE (d:Document {id: $doc_id}) SET d.filename = $filename "
                "WITH d "
                "MATCH (sess:Session {id: $session_id}) "
                "MERGE (sess)-[:HAS_DOCUMENT]->(d)",
                doc_id=doc_id, session_id=session_id, filename=filename,
            )

    # ── Entity nodes ──

    async def upsert_entities(
        self,
        entities: List[Dict[str, Any]],
        session_id: str,
    ) -> None:
        """
        Batch-upsert Entity nodes and link to Document + Session.

        Each dict: {id, content, entity_type, document_id, token_count}
        """
        async with self._mgr.driver.session() as s:
            await s.run(
                "UNWIND $entities AS ent "
                "MERGE (e:Entity {id: ent.id}) "
                "SET e.content      = ent.content, "
                "    e.entity_type  = ent.entity_type, "
                "    e.token_count  = ent.token_count, "
                "    e.session_id   = $session_id "
                "WITH e, ent "
                "MATCH (d:Document {id: ent.document_id}) "
                "MERGE (e)-[:PART_OF]->(d) "
                "WITH e "
                "MATCH (sess:Session {id: $session_id}) "
                "MERGE (e)-[:BELONGS_TO]->(sess)",
                entities=[
                    {
                        "id": e["id"],
                        "content": e.get("content", "")[:5000],
                        "entity_type": e.get("entity_type", "Custom"),
                        "document_id": e.get("document_id", ""),
                        "token_count": e.get("token_count", 0),
                    }
                    for e in entities
                ],
                session_id=session_id,
            )

    # ── Labeled relationship edges ──

    async def create_labeled_edges(
        self,
        edges: List[Dict[str, Any]],
    ) -> None:
        """
        Batch-create labeled directional relationships between entities.

        Each dict: {source_entity_id, target_entity_id, relationship_type,
                     confidence, explanation}

        Because Neo4j relationship types must be literal labels in Cypher
        we group by type and run one query per type for efficiency.
        """
        from collections import defaultdict
        grouped: Dict[str, list] = defaultdict(list)
        for e in edges:
            rt = _neo4j_rel_type(e.get("relationship_type", "related_to"))
            grouped[rt].append(e)

        async with self._mgr.driver.session() as s:
            for rel_type, batch in grouped.items():
                # APOC-free: use dynamic Cypher via f-string (safe — rel_type is validated)
                await s.run(
                    f"UNWIND $edges AS e "
                    f"MATCH (a:Entity {{id: e.source_entity_id}}) "
                    f"MATCH (b:Entity {{id: e.target_entity_id}}) "
                    f"MERGE (a)-[r:{rel_type}]->(b) "
                    f"SET r.confidence = e.confidence, "
                    f"    r.explanation = e.explanation",
                    edges=[
                        {
                            "source_entity_id": e["source_entity_id"],
                            "target_entity_id": e["target_entity_id"],
                            "confidence": e.get("confidence", 0.5),
                            "explanation": e.get("explanation", "")[:512],
                        }
                        for e in batch
                    ],
                )

    # ── Similarity edges ──

    async def create_similarity_edges(self, edges: List[Dict[str, Any]]) -> None:
        """Each dict: {source_id, target_id, similarity}"""
        async with self._mgr.driver.session() as s:
            await s.run(
                "UNWIND $edges AS e "
                "MATCH (a:Entity {id: e.source_id}) "
                "MATCH (b:Entity {id: e.target_id}) "
                "MERGE (a)-[r:SIMILAR_TO]->(b) "
                "SET r.similarity = e.similarity",
                edges=edges,
            )

    # ── Bridge edges (cross-session) ──

    async def create_bridge_edges(self, edges: List[Dict[str, Any]]) -> None:
        async with self._mgr.driver.session() as s:
            await s.run(
                "UNWIND $edges AS e "
                "MATCH (a:Entity {id: e.source_id}) "
                "MATCH (b:Entity {id: e.target_id}) "
                "MERGE (a)-[r:BRIDGES_TO]->(b) "
                "SET r.similarity = e.similarity",
                edges=edges,
            )

    # ── HyperEdge nodes ──

    async def upsert_hyperedges(
        self,
        hyperedges: List[Dict[str, Any]],
        session_id: str,
    ) -> None:
        """
        Create HyperEdge nodes and link them to member entities via
        MEMBER_OF_HYPEREDGE relationships.

        Each dict: {id, label, relationship_type, member_ids, confidence, explanation}
        """
        async with self._mgr.driver.session() as s:
            # Create HyperEdge nodes
            await s.run(
                "UNWIND $hes AS he "
                "MERGE (h:HyperEdge {id: he.id}) "
                "SET h.label             = he.label, "
                "    h.relationship_type = he.relationship_type, "
                "    h.confidence        = he.confidence, "
                "    h.explanation       = he.explanation, "
                "    h.session_id        = $session_id "
                "WITH h "
                "MATCH (sess:Session {id: $session_id}) "
                "MERGE (h)-[:BELONGS_TO]->(sess)",
                hes=hyperedges,
                session_id=session_id,
            )
            # Link members
            member_pairs = [
                {"hyperedge_id": he["id"], "entity_id": mid}
                for he in hyperedges
                for mid in he.get("member_ids", [])
            ]
            if member_pairs:
                await s.run(
                    "UNWIND $pairs AS p "
                    "MATCH (h:HyperEdge {id: p.hyperedge_id}) "
                    "MATCH (e:Entity {id: p.entity_id}) "
                    "MERGE (e)-[:MEMBER_OF_HYPEREDGE]->(h)",
                    pairs=member_pairs,
                )

    # ── Query: full session knowledge graph ──

    async def get_session_graph(
        self,
        session_id: str,
    ) -> Tuple[List[GraphNode], List[GraphEdge], List[HyperEdgeOut]]:
        """
        Retrieve the full knowledge graph for a session.

        Returns (nodes, edges, hyperedges).
        """
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        hyperedges: List[HyperEdgeOut] = []

        async with self._mgr.driver.session() as s:
            # ── Entity nodes ──
            result = await s.run(
                "MATCH (e:Entity)-[:BELONGS_TO]->(sess:Session {id: $sid}) "
                "RETURN e.id AS id, e.content AS content, "
                "       e.entity_type AS entity_type, "
                "       e.token_count AS token_count",
                sid=session_id,
            )
            async for rec in result:
                nodes.append(GraphNode(
                    id=rec["id"],
                    label=(rec["content"] or "")[:80],
                    type="entity",
                    entity_type=rec["entity_type"] or "Custom",
                    metadata={"token_count": rec["token_count"] or 0},
                ))

            # ── All relationships between entities in this session ──
            result = await s.run(
                "MATCH (a:Entity {session_id: $sid})-[r]->(b:Entity {session_id: $sid}) "
                "RETURN a.id AS source, b.id AS target, "
                "       type(r) AS rel_type, "
                "       r.confidence AS confidence, "
                "       r.similarity AS similarity, "
                "       r.explanation AS explanation",
                sid=session_id,
            )
            async for rec in result:
                rel = (rec["rel_type"] or "RELATED_TO").lower()
                weight = float(rec["confidence"] or rec["similarity"] or 0.5)
                edges.append(GraphEdge(
                    source=rec["source"],
                    target=rec["target"],
                    weight=weight,
                    edge_type=rel,
                    relationship_type=rel,
                    explanation=rec["explanation"] or "",
                ))

            # ── HyperEdge nodes + members ──
            result = await s.run(
                "MATCH (h:HyperEdge)-[:BELONGS_TO]->(sess:Session {id: $sid}) "
                "OPTIONAL MATCH (e:Entity)-[:MEMBER_OF_HYPEREDGE]->(h) "
                "RETURN h.id AS id, h.label AS label, "
                "       h.relationship_type AS rel, "
                "       h.confidence AS confidence, "
                "       h.explanation AS explanation, "
                "       collect(e.id) AS member_ids",
                sid=session_id,
            )
            async for rec in result:
                hyperedges.append(HyperEdgeOut(
                    id=rec["id"],
                    label=rec["label"] or "",
                    relationship_type=rec["rel"] or "related_to",
                    member_ids=rec["member_ids"] or [],
                    confidence=float(rec["confidence"] or 0.5),
                    explanation=rec["explanation"] or "",
                ))

        return nodes, edges, hyperedges

    # ── Query: context for RAG (graph-enhanced retrieval) ──

    async def get_entity_neighbours(
        self,
        entity_ids: List[str],
        depth: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        For seed entity IDs, traverse up to ``depth`` hops across ANY
        labeled relationship and return neighbouring entities with the
        relationship path description.
        """
        neighbours: List[Dict[str, Any]] = []
        async with self._mgr.driver.session() as s:
            result = await s.run(
                "UNWIND $ids AS seed_id "
                "MATCH (start:Entity {id: seed_id}) "
                "MATCH path = (start)-[*1.." + str(depth) + "]-(neighbour:Entity) "
                "WHERE neighbour.id <> seed_id "
                "WITH DISTINCT neighbour, "
                "     min(length(path)) AS hops, "
                "     [r IN relationships(head(collect(path))) | type(r)] AS rel_chain "
                "RETURN neighbour.id AS id, "
                "       neighbour.content AS content, "
                "       neighbour.entity_type AS entity_type, "
                "       hops, "
                "       rel_chain "
                "ORDER BY hops ASC "
                "LIMIT 20",
                ids=entity_ids,
            )
            async for rec in result:
                neighbours.append({
                    "id": rec["id"],
                    "content": rec["content"] or "",
                    "entity_type": rec["entity_type"] or "Custom",
                    "hops": rec["hops"],
                    "relationships": rec["rel_chain"] or [],
                })
        return neighbours

    # ── User Notes ──

    async def upsert_user_note(
        self, note_id: str, session_id: str, document_id: str, content: str,
    ) -> None:
        async with self._mgr.driver.session() as s:
            await s.run(
                "MERGE (n:UserNote {id: $note_id}) "
                "SET n.content = $content, n.session_id = $session_id "
                "WITH n "
                "MATCH (sess:Session {id: $session_id}) MERGE (n)-[:BELONGS_TO]->(sess) "
                "WITH n "
                "MATCH (d:Document {id: $doc_id}) MERGE (n)-[:ANNOTATES]->(d)",
                note_id=note_id, content=content[:5000],
                session_id=session_id, doc_id=document_id,
            )

    async def get_user_notes_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        notes: List[Dict[str, Any]] = []
        async with self._mgr.driver.session() as s:
            result = await s.run(
                "MATCH (n:UserNote)-[:BELONGS_TO]->(sess:Session {id: $sid}) "
                "OPTIONAL MATCH (n)-[:ANNOTATES]->(d:Document) "
                "RETURN n.id AS id, n.content AS content, d.filename AS document "
                "ORDER BY n.id",
                sid=session_id,
            )
            async for rec in result:
                notes.append({
                    "id": rec["id"],
                    "content": rec["content"] or "",
                    "document": rec["document"] or "",
                })
        return notes

    async def search_notes_fulltext(self, query: str, session_id: str, limit: int = 5) -> List[str]:
        parts: List[str] = []
        async with self._mgr.driver.session() as s:
            result = await s.run(
                "CALL db.index.fulltext.queryNodes('noteContentIndex', $q) "
                "YIELD node, score "
                "WHERE node.session_id = $sid AND score > 0.3 "
                "RETURN node.content AS content, score "
                "ORDER BY score DESC LIMIT $lim",
                q=query[:100], sid=session_id, lim=limit,
            )
            async for rec in result:
                parts.append(rec["content"] or "")
        return parts

    # ── Cleanup ──

    async def delete_session_graph(self, session_id: str) -> None:
        """Remove all nodes and relationships for a session."""
        async with self._mgr.driver.session() as s:
            await s.run(
                "MATCH (n)-[:BELONGS_TO]->(sess:Session {id: $sid}) "
                "DETACH DELETE n",
                sid=session_id,
            )
            await s.run(
                "MATCH (sess:Session {id: $sid}) DETACH DELETE sess",
                sid=session_id,
            )
