"""
/api/embeddings — generate vector embeddings for session entities.
Stores vectors in ChromaDB (not in SQL).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db import User
from ..models.repository import SessionRepository, EntityRepository
from ..models.schemas import EmbeddingRequest, EmbeddingResult
from ..services.embedder import EmbeddingService
from ..services.chroma_store import get_chroma_store
from .dependencies import get_db, get_current_user, get_embedding_service

router = APIRouter(prefix="/api/embeddings", tags=["Embeddings"])


@router.post("/generate", response_model=EmbeddingResult)
async def generate_embeddings(
    body: EmbeddingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    embedder: EmbeddingService = Depends(get_embedding_service),
):
    # Validate ownership
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(body.session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    # Fetch all entities for this session
    entity_repo = EntityRepository(db)
    entities = await entity_repo.list_by_session(body.session_id)
    if not entities:
        return EmbeddingResult(
            session_id=body.session_id, entities_embedded=0, tokens_used=0, cost_usd=0,
        )

    # Check which entities already have embeddings in ChromaDB
    store = get_chroma_store()
    existing = store.get_by_ids([e.id for e in entities])
    existing_ids = {item["id"] for item in existing if item.get("embedding")}
    to_embed = [e for e in entities if e.id not in existing_ids]

    if not to_embed:
        return EmbeddingResult(
            session_id=body.session_id, entities_embedded=0, tokens_used=0, cost_usd=0,
        )

    # Embed and store in ChromaDB
    entity_dicts = [
        {
            "id": e.id,
            "content": e.content,
            "session_id": e.session_id,
            "document_id": e.document_id,
            "entity_type": e.entity_type,
        }
        for e in to_embed
    ]
    count, total_tokens = await embedder.embed_and_store(entity_dicts)

    # Estimate cost (pricing baked into CostTracker)
    cost = (total_tokens / 1_000) * 0.00002  # approx for text-embedding-3-small

    return EmbeddingResult(
        session_id=body.session_id,
        entities_embedded=count,
        tokens_used=total_tokens,
        cost_usd=round(cost, 6),
    )
