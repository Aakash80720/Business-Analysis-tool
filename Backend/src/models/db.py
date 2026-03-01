"""
SQLAlchemy async engine, session factory, declarative base, and ORM table models.

Schema based on the business-entity–centric design:
  Organisation → Users → Sessions → Documents → Entities
  Entities linked by Edges (intra-session) and SessionBridges (cross-session).
  Vectors stored in ChromaDB (not in SQL).

Uses Repository pattern — raw DB access is encapsulated in models/repository.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from ..config import get_settings


# ═══════════════════════════════════════════════════════
#  Engine & Session Factory
# ═══════════════════════════════════════════════════════

class DatabaseManager:
    """Owns the async engine and session factory (singleton-style)."""

    def __init__(self) -> None:
        cfg = get_settings()
        connect_args: dict = {}
        if cfg.is_sqlite:
            connect_args = {"check_same_thread": False}

        self.engine = create_async_engine(
            cfg.effective_database_url,
            echo=(cfg.app_env == "development"),
            connect_args=connect_args,
        )
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False,
        )

    async def create_tables(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            yield session


db_manager = DatabaseManager()


# ═══════════════════════════════════════════════════════
#  Declarative Base & Helpers
# ═══════════════════════════════════════════════════════

class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════
#  ORM Models
# ═══════════════════════════════════════════════════════

class Organisation(Base):
    __tablename__ = "organisations"

    id         = Column(String(32), primary_key=True, default=_uuid)
    name       = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    users    = relationship("User", back_populates="organisation", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="organisation", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id              = Column(String(32), primary_key=True, default=_uuid)
    org_id          = Column(String(32), ForeignKey("organisations.id"), nullable=True)
    role            = Column(String(32), default="member")   # admin | member | viewer
    email           = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name       = Column(String(255), default="")
    created_at      = Column(DateTime(timezone=True), default=_utcnow)

    organisation = relationship("Organisation", back_populates="users")
    sessions     = relationship("Session", back_populates="owner", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "sessions"

    id         = Column(String(32), primary_key=True, default=_uuid)
    org_id     = Column(String(32), ForeignKey("organisations.id"), nullable=True)
    owner_id   = Column(String(32), ForeignKey("users.id"), nullable=False)
    name       = Column(String(512), nullable=False)
    visibility = Column(String(16), default="private")   # private | team | org
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    organisation = relationship("Organisation", back_populates="sessions")
    owner        = relationship("User", back_populates="sessions")
    documents    = relationship("Document", back_populates="session", cascade="all, delete-orphan")
    entities     = relationship("Entity", back_populates="session", cascade="all, delete-orphan")
    edges        = relationship("Edge", back_populates="session", cascade="all, delete-orphan")
    messages     = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id          = Column(String(32), primary_key=True, default=_uuid)
    session_id  = Column(String(32), ForeignKey("sessions.id"), nullable=False)
    filename    = Column(String(512), nullable=False)
    file_type   = Column(String(10), nullable=False)
    page_count  = Column(Integer, default=0)
    raw_text    = Column(Text, default="")
    uploaded_at = Column(DateTime(timezone=True), default=_utcnow)

    session  = relationship("Session", back_populates="documents")
    entities = relationship("Entity", back_populates="document", cascade="all, delete-orphan")


class Entity(Base):
    """
    Business-entity chunk.

    entity_type: Goal | KPI | OKR | Risk | Action | Owner | Custom
    Embeddings live in ChromaDB (keyed by entity.id), NOT in this table.
    cluster_id is set by K-Means after embedding.
    """
    __tablename__ = "entities"

    id          = Column(String(32), primary_key=True, default=_uuid)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=False)
    session_id  = Column(String(32), ForeignKey("sessions.id"), nullable=False)
    entity_type = Column(String(32), default="Custom")   # Goal|KPI|OKR|Risk|Action|Owner|Custom
    content     = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    cluster_id  = Column(Integer, nullable=True)          # K-Means assigned cluster
    metadata_   = Column("metadata", JSON, default=dict)
    created_at  = Column(DateTime(timezone=True), default=_utcnow)

    document = relationship("Document", back_populates="entities")
    session  = relationship("Session", back_populates="entities")


class Edge(Base):
    """Intra-session graph edge between entities."""
    __tablename__ = "edges"

    id                = Column(String(32), primary_key=True, default=_uuid)
    session_id        = Column(String(32), ForeignKey("sessions.id"), nullable=False)
    source_entity_id  = Column(String(32), ForeignKey("entities.id"), nullable=False)
    target_entity_id  = Column(String(32), ForeignKey("entities.id"), nullable=False)
    relationship_type = Column(String(64), default="similarity")  # achieved_by|measured_by|threatens|supports|similarity
    confidence        = Column(Float, default=1.0)
    created_at        = Column(DateTime(timezone=True), default=_utcnow)

    session       = relationship("Session", back_populates="edges")
    source_entity = relationship("Entity", foreign_keys=[source_entity_id])
    target_entity = relationship("Entity", foreign_keys=[target_entity_id])


class SessionBridge(Base):
    """Cross-session bridge between entities in different sessions."""
    __tablename__ = "session_bridges"

    id               = Column(String(32), primary_key=True, default=_uuid)
    session_a_id     = Column(String(32), ForeignKey("sessions.id"), nullable=False)
    session_b_id     = Column(String(32), ForeignKey("sessions.id"), nullable=False)
    entity_a_id      = Column(String(32), ForeignKey("entities.id"), nullable=False)
    entity_b_id      = Column(String(32), ForeignKey("entities.id"), nullable=False)
    similarity_score = Column(Float, nullable=False)
    strength_tier    = Column(String(16), default="moderate")   # strong | moderate | weak
    ai_explanation   = Column(Text, default="")
    created_at       = Column(DateTime(timezone=True), default=_utcnow)

    session_a = relationship("Session", foreign_keys=[session_a_id])
    session_b = relationship("Session", foreign_keys=[session_b_id])
    entity_a  = relationship("Entity", foreign_keys=[entity_a_id])
    entity_b  = relationship("Entity", foreign_keys=[entity_b_id])


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id          = Column(String(32), primary_key=True, default=_uuid)
    session_id  = Column(String(32), ForeignKey("sessions.id"), nullable=False)
    role        = Column(String(16), nullable=False)
    content     = Column(Text, nullable=False)
    tokens_used = Column(Integer, default=0)
    cost_usd    = Column(Float, default=0.0)
    created_at  = Column(DateTime(timezone=True), default=_utcnow)

    session = relationship("Session", back_populates="messages")


class CostLog(Base):
    __tablename__ = "cost_logs"

    id         = Column(String(32), primary_key=True, default=_uuid)
    category   = Column(String(32), nullable=False)
    tokens     = Column(Integer, default=0)
    cost_usd   = Column(Float, default=0.0)
    model      = Column(String(64), default="")
    created_at = Column(DateTime(timezone=True), default=_utcnow)
