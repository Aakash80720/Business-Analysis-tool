"""
FastAPI dependency injection — provides DB sessions, services, and auth.
"""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models.db import db_manager, User
from ..models.repository import UserRepository
from ..utils.auth import AuthService
from ..utils.cost_tracker import CostTracker
from ..services.embedder import EmbeddingService
from ..services.chat_engine import ChatEngine


_bearer = HTTPBearer(auto_error=False)
_auth_service = AuthService()

_DEV_USER_EMAIL = "dev@localhost"


# ── DB session ──

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in db_manager.get_session():
        yield session


# ── Auth ──

async def _get_or_create_dev_user(db: AsyncSession) -> User:
    """Return a persistent dev user, creating one on first call."""
    repo = UserRepository(db)
    user = await repo.get_by_email(_DEV_USER_EMAIL)
    if user is None:
        user = User(
            email=_DEV_USER_EMAIL,
            hashed_password="nologin",
            full_name="Dev User",
        )
        await repo.add(user)
        await repo.commit()
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    cfg = get_settings()

    # ── Dev bypass: skip auth in development if no token is provided ──
    if credentials is None:
        if cfg.app_env == "development":
            return await _get_or_create_dev_user(db)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    try:
        payload = _auth_service.decode_token(credentials.credentials)
        user_id: str = payload["sub"]
    except Exception:
        if cfg.app_env == "development":
            return await _get_or_create_dev_user(db)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        if cfg.app_env == "development":
            return await _get_or_create_dev_user(db)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


# ── Service factories (injected per-request with a live DB session) ──

def get_cost_tracker(db: AsyncSession = Depends(get_db)) -> CostTracker:
    return CostTracker(db)


def get_embedding_service(
    cost_tracker: CostTracker = Depends(get_cost_tracker),
) -> EmbeddingService:
    return EmbeddingService(cost_tracker=cost_tracker)


def get_chat_engine(
    cost_tracker: CostTracker = Depends(get_cost_tracker),
) -> ChatEngine:
    return ChatEngine(cost_tracker=cost_tracker)
