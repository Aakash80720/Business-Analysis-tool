"""
/api/graph — build & return the knowledge graph + cross-session bridges.
Integrates Neo4j for persistent knowledge graph storage.
Entities replace chunks; embeddings come from ChromaDB.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db import User, Edge as EdgeModel, SessionBridge as SessionBridgeModel
from ..models.repository import (
    SessionRepository, EntityRepository, EdgeRepository, SessionBridgeRepository,
)
from ..models.schemas import GraphResponse, BridgeResponse
from ..services.graph_builder import GraphBuilder
from ..services.bridge_engine import BridgeEngine
from ..services.chroma_store import get_chroma_store
from .dependencies import get_db, get_current_user

router = APIRouter(prefix="/api/graph", tags=["Graph"])


# ── Neo4j helper (optional, graceful) ──

async def _try_sync_to_neo4j(
    session_id: str,
    session_name: str,
    entity_dicts: list[dict],
    similarity_edges: list[dict],
) -> None:
    """Sync graph data to Neo4j if available. Non-fatal on failure."""
    try:
        from ..services.neo4j_manager import neo4j_manager, KnowledgeGraphService
        if neo4j_manager._driver is None:
            return
        kg = KnowledgeGraphService()
        await kg.upsert_session(session_id, session_name)
        await kg.upsert_chunks(entity_dicts, session_id)
        if similarity_edges:
            await kg.create_similarity_edges(similarity_edges)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════
#  Build graph edges (clustering + similarity)
# ═══════════════════════════════════════════════════════

@router.post("/build", response_model=GraphResponse)
async def build_graph(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Build similarity edges for a session and persist as Edge records."""
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    entity_repo = EntityRepository(db)
    entities = await entity_repo.list_by_session(session_id)
    if len(entities) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Need ≥2 entities to build graph")

    # Fetch embeddings from ChromaDB
    store = get_chroma_store()
    chroma_data = store.get_by_session(session_id)

    # Build similarity edges
    builder = GraphBuilder()
    sim_edge_dicts = builder.get_similarity_edge_dicts(chroma_data)

    # Persist Edge records in SQL
    edge_repo = EdgeRepository(db)
    await edge_repo.delete_by_session(session_id)

    for ed in sim_edge_dicts:
        edge = EdgeModel(
            session_id=session_id,
            source_entity_id=ed["source_entity_id"],
            target_entity_id=ed["target_entity_id"],
            relationship_type=ed["relationship_type"],
            confidence=ed["confidence"],
        )
        await edge_repo.add(edge)
    await edge_repo.commit()

    # Build response graph
    entity_dicts = [
        {
            "id": e.id, "content": e.content, "entity_type": e.entity_type,
            "cluster_id": e.cluster_id, "document_id": e.document_id,
            "token_count": e.token_count,
        }
        for e in entities
    ]
    nodes, edges = builder.build(entity_dicts, chroma_data)

    # Sync to Neo4j (best-effort)
    neo4j_entity_dicts = [
        {"id": e.id, "content": e.content, "document_id": e.document_id, "token_count": e.token_count}
        for e in entities
    ]
    neo4j_sim_edges = [
        {"source_id": ed["source_entity_id"], "target_id": ed["target_entity_id"], "similarity": ed["confidence"]}
        for ed in sim_edge_dicts
    ]
    await _try_sync_to_neo4j(session_id, session.name, neo4j_entity_dicts, neo4j_sim_edges)

    return GraphResponse(session_id=session_id, nodes=nodes, edges=edges)


# ═══════════════════════════════════════════════════════
#  Full graph for a session
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

    # Try Neo4j first for richer graph data
    try:
        from ..services.neo4j_manager import neo4j_manager, KnowledgeGraphService
        if neo4j_manager._driver is not None:
            kg = KnowledgeGraphService()
            nodes, edges = await kg.get_session_graph(session_id)
            if nodes:
                return GraphResponse(session_id=session_id, nodes=nodes, edges=edges)
    except Exception:
        pass

    # Fallback: in-memory graph builder using entities + ChromaDB
    entity_repo = EntityRepository(db)
    entities = await entity_repo.list_by_session(session_id)

    entity_dicts = [
        {
            "id": e.id, "content": e.content, "entity_type": e.entity_type,
            "cluster_id": e.cluster_id, "document_id": e.document_id,
            "token_count": e.token_count,
        }
        for e in entities
    ]

    store = get_chroma_store()
    chroma_data = store.get_by_session(session_id)

    builder = GraphBuilder()
    nodes, edges = builder.build(entity_dicts, chroma_data)

    return GraphResponse(session_id=session_id, nodes=nodes, edges=edges)


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

    # Optionally persist bridge records
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
