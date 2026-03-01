"""
Data-access repositories — encapsulate all raw SQL / ORM queries.
Follows the Repository pattern so services never touch the session directly.

Embeddings are NOT stored in SQL — they live in ChromaDB (see chroma_store.py).
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import select, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .db import (
    Organisation, User, Session, Document, Entity,
    Edge, SessionBridge, HyperEdge, HyperEdgeMember,
    ChatMessage, CostLog,
)


# ─────────────────────────────────────────────────────
#  Base Repository (Template Method)
# ─────────────────────────────────────────────────────

class BaseRepository[T]:
    """Generic async CRUD operations for any ORM model."""

    model: type

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, entity_id: str) -> Optional[T]:
        return await self._db.get(self.model, entity_id)

    async def list_all(self) -> List[T]:
        result = await self._db.execute(select(self.model))
        return list(result.scalars().all())

    async def add(self, entity: T) -> T:
        self._db.add(entity)
        await self._db.flush()
        return entity

    async def add_many(self, entities: Sequence[T]) -> List[T]:
        self._db.add_all(entities)
        await self._db.flush()
        return list(entities)

    async def delete(self, entity: T) -> None:
        await self._db.delete(entity)
        await self._db.flush()

    async def commit(self) -> None:
        await self._db.commit()


# ─────────────────────────────────────────────────────
#  Concrete Repositories
# ─────────────────────────────────────────────────────

class OrganisationRepository(BaseRepository[Organisation]):
    model = Organisation


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self._db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()


class SessionRepository(BaseRepository[Session]):
    model = Session

    async def list_by_owner(self, owner_id: str) -> List[Session]:
        result = await self._db.execute(
            select(Session)
            .where(Session.owner_id == owner_id)
            .order_by(Session.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_with_relations(self, session_id: str) -> Optional[Session]:
        result = await self._db.execute(
            select(Session)
            .where(Session.id == session_id)
            .options(
                selectinload(Session.documents),
                selectinload(Session.entities),
            )
        )
        return result.scalar_one_or_none()


class DocumentRepository(BaseRepository[Document]):
    model = Document

    async def list_by_session(self, session_id: str) -> List[Document]:
        result = await self._db.execute(
            select(Document)
            .where(Document.session_id == session_id)
            .order_by(Document.uploaded_at.desc())
        )
        return list(result.scalars().all())


class EntityRepository(BaseRepository[Entity]):
    """Replaces the old ChunkRepository — entities are typed business objects."""
    model = Entity

    async def list_by_session(self, session_id: str) -> List[Entity]:
        result = await self._db.execute(
            select(Entity).where(Entity.session_id == session_id)
        )
        return list(result.scalars().all())

    async def list_by_document(self, document_id: str) -> List[Entity]:
        result = await self._db.execute(
            select(Entity).where(Entity.document_id == document_id)
        )
        return list(result.scalars().all())

    async def list_by_type(self, session_id: str, entity_type: str) -> List[Entity]:
        result = await self._db.execute(
            select(Entity)
            .where(Entity.session_id == session_id)
            .where(Entity.entity_type == entity_type)
        )
        return list(result.scalars().all())

    async def delete_by_session(self, session_id: str) -> None:
        await self._db.execute(
            delete(Entity).where(Entity.session_id == session_id)
        )
        await self._db.flush()


class EdgeRepository(BaseRepository[Edge]):
    """Intra-session graph edges between entities."""
    model = Edge

    async def list_by_session(self, session_id: str) -> List[Edge]:
        result = await self._db.execute(
            select(Edge).where(Edge.session_id == session_id)
        )
        return list(result.scalars().all())

    async def delete_by_session(self, session_id: str) -> None:
        await self._db.execute(
            delete(Edge).where(Edge.session_id == session_id)
        )
        await self._db.flush()


class SessionBridgeRepository(BaseRepository[SessionBridge]):
    """Cross-session bridges between entities."""
    model = SessionBridge

    async def list_by_sessions(self, session_ids: List[str]) -> List[SessionBridge]:
        result = await self._db.execute(
            select(SessionBridge).where(
                or_(
                    SessionBridge.session_a_id.in_(session_ids),
                    SessionBridge.session_b_id.in_(session_ids),
                )
            )
        )
        return list(result.scalars().all())

    async def delete_all(self) -> None:
        await self._db.execute(delete(SessionBridge))
        await self._db.flush()


class HyperEdgeRepository(BaseRepository[HyperEdge]):
    """Hyperedges connecting 3+ entities."""
    model = HyperEdge

    async def list_by_session(self, session_id: str) -> List[HyperEdge]:
        result = await self._db.execute(
            select(HyperEdge)
            .where(HyperEdge.session_id == session_id)
            .options(selectinload(HyperEdge.members))
        )
        return list(result.scalars().all())

    async def delete_by_session(self, session_id: str) -> None:
        # Members cascade-delete with hyperedge
        await self._db.execute(
            delete(HyperEdge).where(HyperEdge.session_id == session_id)
        )
        await self._db.flush()


class ChatMessageRepository(BaseRepository[ChatMessage]):
    model = ChatMessage

    async def list_by_session(self, session_id: str, limit: int = 50) -> List[ChatMessage]:
        result = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


class CostLogRepository(BaseRepository[CostLog]):
    model = CostLog

    async def sum_by_category(self, category: str) -> tuple[int, float]:
        """Return (total_tokens, total_cost_usd) for a category."""
        result = await self._db.execute(
            select(
                func.coalesce(func.sum(CostLog.tokens), 0),
                func.coalesce(func.sum(CostLog.cost_usd), 0.0),
            ).where(CostLog.category == category)
        )
        row = result.one()
        return int(row[0]), float(row[1])
