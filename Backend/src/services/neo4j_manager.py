"""
Neo4j Knowledge Graph Manager — manages the graph database for
rich entity/relationship storage and traversal.

Replaces the in-memory NetworkX graph with a persistent Neo4j store.

Nodes:  Chunk, Cluster, Document, Session
Edges:  BELONGS_TO, SIMILAR_TO, BRIDGES_TO, PART_OF, HAS_DOCUMENT
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from neo4j import AsyncGraphDatabase, AsyncDriver

from ..config import get_settings
from ..models.schemas import GraphNode, GraphEdge


# ═══════════════════════════════════════════════════════
#  Connection Manager (singleton-style)
# ═══════════════════════════════════════════════════════

class Neo4jManager:
    """
    Manages the async Neo4j driver lifecycle.
    Call `connect()` on startup and `close()` on shutdown.
    """

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
        # Verify connectivity
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
        """Create constraints and indexes for the knowledge graph schema."""
        async with self.driver.session() as session:
            await session.run(
                "CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (c:Chunk) REQUIRE c.id IS UNIQUE"
            )
            await session.run(
                "CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (cl:Cluster) REQUIRE cl.id IS UNIQUE"
            )
            await session.run(
                "CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (d:Document) REQUIRE d.id IS UNIQUE"
            )
            await session.run(
                "CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (s:Session) REQUIRE s.id IS UNIQUE"
            )
            await session.run(
                "CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (n:UserNote) REQUIRE n.id IS UNIQUE"
            )
            # Full-text index for chunk content search
            await session.run(
                "CREATE FULLTEXT INDEX chunkContentIndex IF NOT EXISTS "
                "FOR (c:Chunk) ON EACH [c.content]"
            )
            # Full-text index for user notes search
            await session.run(
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
    High-level operations on the Neo4j knowledge graph.

    Provides methods to:
    - Upsert sessions, documents, chunks, clusters, user notes
    - Create similarity / bridge / hierarchy edges
    - Query subgraphs for a session
    - Retrieve context for RAG (graph-aware retrieval)
    - Query user notes for contextual chunking
    """

    def __init__(self, manager: Neo4jManager | None = None) -> None:
        self._mgr = manager or neo4j_manager

    # ── Session / Document nodes ──

    async def upsert_session(self, session_id: str, title: str) -> None:
        async with self._mgr.driver.session() as s:
            await s.run(
                "MERGE (sess:Session {id: $id}) "
                "SET sess.title = $title",
                id=session_id, title=title,
            )

    async def upsert_document(
        self, doc_id: str, session_id: str, filename: str,
    ) -> None:
        async with self._mgr.driver.session() as s:
            await s.run(
                "MERGE (d:Document {id: $doc_id}) "
                "SET d.filename = $filename "
                "WITH d "
                "MATCH (sess:Session {id: $session_id}) "
                "MERGE (sess)-[:HAS_DOCUMENT]->(d)",
                doc_id=doc_id, session_id=session_id, filename=filename,
            )

    # ── Chunk nodes ──

    async def upsert_chunks(
        self,
        chunks: List[Dict[str, Any]],
        session_id: str,
    ) -> None:
        """
        Batch-upsert chunk nodes and link them to their document + session.

        Each dict: {id, content, document_id, token_count, context?, cluster_id?}
        """
        async with self._mgr.driver.session() as s:
            await s.run(
                "UNWIND $chunks AS ch "
                "MERGE (c:Chunk {id: ch.id}) "
                "SET c.content     = ch.content, "
                "    c.token_count = ch.token_count, "
                "    c.context     = ch.context, "
                "    c.session_id  = $session_id "
                "WITH c, ch "
                "MATCH (d:Document {id: ch.document_id}) "
                "MERGE (c)-[:PART_OF]->(d) "
                "WITH c "
                "MATCH (sess:Session {id: $session_id}) "
                "MERGE (c)-[:BELONGS_TO]->(sess)",
                chunks=[
                    {
                        "id": c["id"],
                        "content": c.get("content", "")[:5000],
                        "document_id": c.get("document_id", ""),
                        "token_count": c.get("token_count", 0),
                        "context": c.get("context", ""),
                    }
                    for c in chunks
                ],
                session_id=session_id,
            )

    # ── Cluster nodes + hierarchy edges ──

    async def upsert_clusters(
        self,
        clusters: List[Dict[str, Any]],
        session_id: str,
    ) -> None:
        """
        Upsert cluster nodes and link them to the session.
        Each dict: {id, label, summary, method}
        """
        async with self._mgr.driver.session() as s:
            await s.run(
                "UNWIND $clusters AS cl "
                "MERGE (c:Cluster {id: cl.id}) "
                "SET c.label   = cl.label, "
                "    c.summary = cl.summary, "
                "    c.method  = cl.method "
                "WITH c "
                "MATCH (sess:Session {id: $session_id}) "
                "MERGE (c)-[:BELONGS_TO]->(sess)",
                clusters=clusters,
                session_id=session_id,
            )

    async def assign_chunks_to_clusters(
        self,
        assignments: List[Dict[str, str]],
    ) -> None:
        """
        Create MEMBER_OF edges from chunks to clusters.
        Each dict: {chunk_id, cluster_id}
        """
        async with self._mgr.driver.session() as s:
            await s.run(
                "UNWIND $assignments AS a "
                "MATCH (ch:Chunk {id: a.chunk_id}) "
                "MATCH (cl:Cluster {id: a.cluster_id}) "
                "MERGE (ch)-[:MEMBER_OF]->(cl)",
                assignments=assignments,
            )

    # ── Similarity edges ──

    async def create_similarity_edges(
        self,
        edges: List[Dict[str, Any]],
    ) -> None:
        """
        Batch-create SIMILAR_TO relationships.
        Each dict: {source_id, target_id, similarity}
        """
        async with self._mgr.driver.session() as s:
            await s.run(
                "UNWIND $edges AS e "
                "MATCH (a:Chunk {id: e.source_id}) "
                "MATCH (b:Chunk {id: e.target_id}) "
                "MERGE (a)-[r:SIMILAR_TO]->(b) "
                "SET r.similarity = e.similarity",
                edges=edges,
            )

    # ── Bridge edges (cross-session) ──

    async def create_bridge_edges(
        self,
        edges: List[Dict[str, Any]],
    ) -> None:
        """
        Create BRIDGES_TO edges across sessions.
        Each dict: {source_id, target_id, similarity}
        """
        async with self._mgr.driver.session() as s:
            await s.run(
                "UNWIND $edges AS e "
                "MATCH (a:Chunk {id: e.source_id}) "
                "MATCH (b:Chunk {id: e.target_id}) "
                "MERGE (a)-[r:BRIDGES_TO]->(b) "
                "SET r.similarity = e.similarity",
                edges=edges,
            )

    # ── Query: full session sub-graph ──

    async def get_session_graph(
        self,
        session_id: str,
    ) -> Tuple[List[GraphNode], List[GraphEdge]]:
        """
        Retrieve all nodes and edges for a session from Neo4j.
        Returns (nodes, edges) matching the existing schema.
        """
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []

        async with self._mgr.driver.session() as s:
            # Chunk nodes
            result = await s.run(
                "MATCH (c:Chunk)-[:BELONGS_TO]->(sess:Session {id: $sid}) "
                "OPTIONAL MATCH (c)-[:MEMBER_OF]->(cl:Cluster) "
                "RETURN c.id AS id, c.content AS content, "
                "       c.token_count AS token_count, "
                "       c.context AS context, "
                "       cl.id AS cluster_id",
                sid=session_id,
            )
            async for record in result:
                label = (record["content"] or "")[:80]
                nodes.append(GraphNode(
                    id=record["id"],
                    label=label,
                    type="chunk",
                    cluster_id=record["cluster_id"],
                    metadata={
                        "token_count": record["token_count"] or 0,
                        "context": record["context"] or "",
                    },
                ))

            # Cluster nodes
            result = await s.run(
                "MATCH (cl:Cluster)-[:BELONGS_TO]->(sess:Session {id: $sid}) "
                "OPTIONAL MATCH (ch:Chunk)-[:MEMBER_OF]->(cl) "
                "RETURN cl.id AS id, cl.label AS label, cl.summary AS summary, "
                "       count(ch) AS chunk_count",
                sid=session_id,
            )
            async for record in result:
                nodes.append(GraphNode(
                    id=record["id"],
                    label=record["label"] or "Cluster",
                    type="cluster",
                    metadata={
                        "summary": record["summary"] or "",
                        "chunk_count": record["chunk_count"],
                    },
                ))

            # Hierarchy edges: chunk → cluster
            result = await s.run(
                "MATCH (c:Chunk)-[:BELONGS_TO]->(sess:Session {id: $sid}) "
                "MATCH (c)-[:MEMBER_OF]->(cl:Cluster) "
                "RETURN c.id AS source, cl.id AS target",
                sid=session_id,
            )
            async for record in result:
                edges.append(GraphEdge(
                    source=record["source"],
                    target=record["target"],
                    weight=1.0,
                    edge_type="hierarchy",
                ))

            # Similarity edges
            result = await s.run(
                "MATCH (a:Chunk)-[:BELONGS_TO]->(sess:Session {id: $sid}) "
                "MATCH (a)-[r:SIMILAR_TO]->(b:Chunk) "
                "WHERE b.session_id = $sid "
                "RETURN a.id AS source, b.id AS target, r.similarity AS weight",
                sid=session_id,
            )
            async for record in result:
                edges.append(GraphEdge(
                    source=record["source"],
                    target=record["target"],
                    weight=float(record["weight"]),
                    edge_type="similarity",
                ))

        return nodes, edges

    # ── Query: context for RAG (graph-enhanced retrieval) ──

    async def get_chunk_neighbours(
        self,
        chunk_ids: List[str],
        depth: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        For a set of seed chunk IDs, traverse up to `depth` hops
        and return neighbouring chunks with their relationship paths.
        This gives the LLM rich graph context beyond vector similarity.
        """
        neighbours: List[Dict[str, Any]] = []
        async with self._mgr.driver.session() as s:
            result = await s.run(
                "UNWIND $ids AS seed_id "
                "MATCH (start:Chunk {id: seed_id}) "
                "MATCH path = (start)-[*1.." + str(depth) + "]-(neighbour:Chunk) "
                "WHERE neighbour.id <> seed_id "
                "WITH DISTINCT neighbour, "
                "     min(length(path)) AS hops "
                "RETURN neighbour.id AS id, "
                "       neighbour.content AS content, "
                "       neighbour.context AS context, "
                "       hops "
                "ORDER BY hops ASC "
                "LIMIT 20",
                ids=chunk_ids,
            )
            async for record in result:
                neighbours.append({
                    "id": record["id"],
                    "content": record["content"] or "",
                    "context": record["context"] or "",
                    "hops": record["hops"],
                })
        return neighbours

    # ── User Notes: store & query for contextual chunking ──

    async def upsert_user_note(
        self,
        note_id: str,
        session_id: str,
        document_id: str,
        content: str,
    ) -> None:
        """
        Store a user note as a node in the knowledge graph, linked to
        its session and document. This allows the chunker to pull
        user-provided context during contextual enrichment.
        """
        async with self._mgr.driver.session() as s:
            await s.run(
                "MERGE (n:UserNote {id: $note_id}) "
                "SET n.content = $content, "
                "    n.session_id = $session_id "
                "WITH n "
                "MATCH (sess:Session {id: $session_id}) "
                "MERGE (n)-[:BELONGS_TO]->(sess) "
                "WITH n "
                "MATCH (d:Document {id: $doc_id}) "
                "MERGE (n)-[:ANNOTATES]->(d)",
                note_id=note_id,
                content=content[:5000],
                session_id=session_id,
                doc_id=document_id,
            )

    async def get_user_notes_for_session(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all user notes for a session — used during contextual
        chunking to provide domain context.
        """
        notes: List[Dict[str, Any]] = []
        async with self._mgr.driver.session() as s:
            result = await s.run(
                "MATCH (n:UserNote)-[:BELONGS_TO]->(sess:Session {id: $sid}) "
                "OPTIONAL MATCH (n)-[:ANNOTATES]->(d:Document) "
                "RETURN n.id AS id, n.content AS content, "
                "       d.filename AS document "
                "ORDER BY n.id",
                sid=session_id,
            )
            async for record in result:
                notes.append({
                    "id": record["id"],
                    "content": record["content"] or "",
                    "document": record["document"] or "",
                })
        return notes

    async def search_notes_fulltext(
        self,
        query: str,
        session_id: str,
        limit: int = 5,
    ) -> List[str]:
        """
        Full-text search across user notes in a session.
        Returns matching note content strings.
        """
        parts: List[str] = []
        async with self._mgr.driver.session() as s:
            result = await s.run(
                "CALL db.index.fulltext.queryNodes('noteContentIndex', $q) "
                "YIELD node, score "
                "WHERE node.session_id = $sid AND score > 0.3 "
                "RETURN node.content AS content, score "
                "ORDER BY score DESC "
                "LIMIT $lim",
                q=query[:100],
                sid=session_id,
                lim=limit,
            )
            async for record in result:
                parts.append(record["content"] or "")
        return parts

    # ── Cleanup ──

    async def delete_session_graph(self, session_id: str) -> None:
        """Remove all nodes and edges for a session."""
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
