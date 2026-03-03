"""
/api/graph — build & query the contextual knowledge graph.

Pipeline:
  1. Similarity edges  (cosine on ChromaDB embeddings)
  2. LLM-extracted labeled edges  (achieved_by, measured_by, …)
  3. Hyperedges  (single concept connecting 3+ entities)
  4. Cross-session bridges

Persistence:  SQL (Edge / HyperEdge tables) + Neo4j (optional).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db import (
    User,
    Edge as EdgeModel,
    SessionBridge as SessionBridgeModel,
    HyperEdge as HyperEdgeModel,
    HyperEdgeMember as HyperEdgeMemberModel,
)
from ..models.repository import (
    SessionRepository, EntityRepository, EdgeRepository,
    SessionBridgeRepository, HyperEdgeRepository,
)
from ..models.schemas import (
    GraphResponse, BridgeResponse, HyperEdgeOut, KnowledgeGraphBuildRequest,
)
from ..services.graph_builder import GraphBuilder
from ..services.bridge_engine import BridgeEngine
from ..services.chroma_store import get_chroma_store
from .dependencies import get_db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["Graph"])


# ── Neo4j helper (optional, graceful) ──────────────

async def _try_sync_to_neo4j(
    session_id: str,
    session_name: str,
    entity_dicts: list[dict],
    similarity_edges: list[dict],
    labeled_edges: list[dict],
    hyperedges: list[dict],
) -> None:
    """Push the full knowledge graph to Neo4j. Non-fatal on failure."""
    try:
        from ..services.neo4j_manager import neo4j_manager, KnowledgeGraphService
        if neo4j_manager._driver is None:
            return
        kg = KnowledgeGraphService()
        await kg.upsert_session(session_id, session_name)
        await kg.upsert_entities(entity_dicts, session_id)
        if similarity_edges:
            await kg.create_similarity_edges(similarity_edges)
        if labeled_edges:
            await kg.create_labeled_edges(labeled_edges)
        if hyperedges:
            await kg.upsert_hyperedges(hyperedges, session_id)
    except Exception:
        logger.debug("Neo4j sync failed (non-fatal)", exc_info=True)


# ═══════════════════════════════════════════════════════
#  Build knowledge graph (similarity + LLM extraction)
# ═══════════════════════════════════════════════════════

@router.post("/build", response_model=GraphResponse)
async def build_graph(
    body: KnowledgeGraphBuildRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Build the full contextual knowledge graph for a session:

    1. Compute cosine-similarity edges from ChromaDB embeddings.
    2. Call the LLM to extract labeled directional edges + hyperedges.
    3. Persist everything in SQL (Edge / HyperEdge tables).
    4. Best-effort sync to Neo4j.
    """
    session_id = body.session_id

    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    entity_repo = EntityRepository(db)
    entities = await entity_repo.list_by_session(session_id)
    if len(entities) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Need ≥2 entities to build graph")

    # ── 1. Similarity edges ──
    store = get_chroma_store()
    chroma_data = store.get_by_session(session_id)

    builder = GraphBuilder(similarity_threshold=body.similarity_threshold)
    sim_edge_dicts: list[dict] = []
    if body.include_similarity:
        sim_edge_dicts = builder.get_similarity_edge_dicts(chroma_data)

    # ── 2. LLM-extracted labeled edges + hyperedges ──
    entity_dicts = [
        {
            "id": e.id, "content": e.content, "entity_type": e.entity_type,
            "cluster_id": e.cluster_id, "document_id": e.document_id,
            "token_count": e.token_count,
        }
        for e in entities
    ]

    llm_edge_dicts, hyperedge_dicts, entity_annotations = await builder.extract_relationships(entity_dicts)

    # ── 3. Persist to SQL ──
    edge_repo = EdgeRepository(db)
    he_repo = HyperEdgeRepository(db)

    # Clear old edges + hyperedges for this session
    await edge_repo.delete_by_session(session_id)
    await he_repo.delete_by_session(session_id)

    # Similarity edges
    for ed in sim_edge_dicts:
        await edge_repo.add(EdgeModel(
            session_id=session_id,
            source_entity_id=ed["source_entity_id"],
            target_entity_id=ed["target_entity_id"],
            relationship_type="similarity",
            confidence=ed["confidence"],
        ))

    # Labeled edges
    for ed in llm_edge_dicts:
        await edge_repo.add(EdgeModel(
            session_id=session_id,
            source_entity_id=ed["source_entity_id"],
            target_entity_id=ed["target_entity_id"],
            relationship_type=ed["relationship_type"],
            confidence=ed.get("confidence", 0.5),
            explanation=ed.get("explanation", ""),
        ))

    # Hyperedges + members
    neo4j_hyperedges: list[dict] = []
    hyperedge_outs: list[HyperEdgeOut] = []
    for hd in hyperedge_dicts:
        he_id = uuid.uuid4().hex[:32]
        he = HyperEdgeModel(
            id=he_id,
            session_id=session_id,
            label=hd["label"],
            relationship_type=hd["relationship_type"],
            confidence=hd.get("confidence", 0.5),
            explanation=hd.get("explanation", ""),
        )
        await he_repo.add(he)
        for mid in hd["member_ids"]:
            member = HyperEdgeMemberModel(hyperedge_id=he_id, entity_id=mid)
            db.add(member)
        await db.flush()

        neo4j_hyperedges.append({
            "id": he_id, "label": hd["label"],
            "relationship_type": hd["relationship_type"],
            "member_ids": hd["member_ids"],
            "confidence": hd.get("confidence", 0.5),
            "explanation": hd.get("explanation", ""),
        })
        hyperedge_outs.append(HyperEdgeOut(
            id=he_id, label=hd["label"],
            relationship_type=hd["relationship_type"],
            member_ids=hd["member_ids"],
            confidence=hd.get("confidence", 0.5),
            explanation=hd.get("explanation", ""),
        ))

    await db.commit()

    # ── 4. Build response ──
    llm_graph_edges = GraphBuilder.edges_to_graph_edges(llm_edge_dicts)
    nodes, edges = builder.build(
        entity_dicts, chroma_data,
        extra_edges=llm_graph_edges,
        annotations=entity_annotations,
    )

    # ── 5. Neo4j sync (best-effort) ──
    neo4j_entity_dicts = [
        {"id": e.id, "content": e.content, "entity_type": e.entity_type,
         "document_id": e.document_id, "token_count": e.token_count}
        for e in entities
    ]
    neo4j_sim = [
        {"source_id": ed["source_entity_id"], "target_id": ed["target_entity_id"],
         "similarity": ed["confidence"]}
        for ed in sim_edge_dicts
    ]
    await _try_sync_to_neo4j(
        session_id, session.name,
        neo4j_entity_dicts, neo4j_sim, llm_edge_dicts, neo4j_hyperedges,
    )

    return GraphResponse(
        session_id=session_id, nodes=nodes, edges=edges,
        hyperedges=hyperedge_outs,
    )


# ═══════════════════════════════════════════════════════
#  Full graph for a session (read-only)
# ═══════════════════════════════════════════════════════

@router.get("/{session_id}", response_model=GraphResponse)
async def get_graph(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    # ── Try Neo4j first ──
    try:
        from ..services.neo4j_manager import neo4j_manager, KnowledgeGraphService
        if neo4j_manager._driver is not None:
            kg = KnowledgeGraphService()
            nodes, edges, hyperedges = await kg.get_session_graph(session_id)
            if nodes:
                return GraphResponse(
                    session_id=session_id, nodes=nodes,
                    edges=edges, hyperedges=hyperedges,
                )
    except Exception:
        pass

    # ── Fallback: SQL + ChromaDB ──
    entity_repo = EntityRepository(db)
    entities = await entity_repo.list_by_session(session_id)

    entity_dicts = [
        {"id": e.id, "content": e.content, "entity_type": e.entity_type,
         "cluster_id": e.cluster_id, "document_id": e.document_id,
         "token_count": e.token_count}
        for e in entities
    ]

    store = get_chroma_store()
    chroma_data = store.get_by_session(session_id)

    # Rebuild labeled edges from SQL
    edge_repo = EdgeRepository(db)
    sql_edges = await edge_repo.list_by_session(session_id)
    extra_edges = GraphBuilder.edges_to_graph_edges([
        {"source_entity_id": e.source_entity_id, "target_entity_id": e.target_entity_id,
         "relationship_type": e.relationship_type, "confidence": e.confidence,
         "explanation": getattr(e, "explanation", "")}
        for e in sql_edges if e.relationship_type != "similarity"
    ])

    builder = GraphBuilder()
    nodes, edges = builder.build(entity_dicts, chroma_data, extra_edges=extra_edges)

    # Rebuild hyperedges from SQL
    he_repo = HyperEdgeRepository(db)
    sql_hes = await he_repo.list_by_session(session_id)
    hyperedge_outs = [
        HyperEdgeOut(
            id=he.id, label=he.label,
            relationship_type=he.relationship_type,
            member_ids=[m.entity_id for m in he.members],
            confidence=he.confidence,
            explanation=he.explanation or "",
        )
        for he in sql_hes
    ]

    return GraphResponse(
        session_id=session_id, nodes=nodes,
        edges=edges, hyperedges=hyperedge_outs,
    )


# ═══════════════════════════════════════════════════════
#  Cross-session bridges
# ═══════════════════════════════════════════════════════

@router.get("/bridges", response_model=BridgeResponse)
async def get_bridges(
    session_ids: list[str] = Query(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    store = get_chroma_store()
    all_entities = store.get_all_with_embeddings(
        session_ids=session_ids if session_ids else None,
    )

    engine = BridgeEngine()
    bridge_records, involved = engine.find_bridges(all_entities)
    graph_edges = engine.bridges_to_graph_edges(bridge_records)

    bridge_repo = SessionBridgeRepository(db)
    await bridge_repo.delete_all()
    for br in bridge_records:
        record = SessionBridgeModel(
            session_a_id=br["session_a_id"],
            session_b_id=br["session_b_id"],
            entity_a_id=br["entity_a_id"],
            entity_b_id=br["entity_b_id"],
            similarity_score=br["similarity_score"],
            strength_tier=br["strength_tier"],
        )
        await bridge_repo.add(record)
    await bridge_repo.commit()

    return BridgeResponse(bridges=graph_edges, session_ids=involved)
