"""
/api/sessions — CRUD for analysis sessions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from ..models.db import Session, User
from ..models.repository import SessionRepository
from ..models.schemas import SessionCreate, SessionOut, SessionListOut
from .dependencies import get_db, get_current_user

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


# ═══════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════

@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = SessionRepository(db)
    session = Session(
        name=body.name,
        visibility=body.visibility,
        owner_id=user.id,
        org_id=getattr(user, "org_id", None),
    )
    await repo.add(session)
    await repo.commit()
    return _to_out(session)


@router.get("", response_model=SessionListOut)
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = SessionRepository(db)
    sessions = await repo.list_by_owner(user.id)
    return SessionListOut(sessions=[_to_out(s) for s in sessions])


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = SessionRepository(db)
    session = await repo.get_with_relations(session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return _to_out(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    # Also clean up ChromaDB vectors for this session
    try:
        from ..services.chroma_store import get_chroma_store
        get_chroma_store().delete_by_session(session_id)
    except Exception:
        pass

    await repo.delete(session)
    await repo.commit()


# ═══════════════════════════════════════════════════════
#  Helper
# ═══════════════════════════════════════════════════════

def _safe_len(obj, attr_name: str) -> int:
    """Return len() of a relationship if it's already loaded, else 0."""
    state = attributes.instance_state(obj)
    if attr_name in state.dict:
        val = state.dict[attr_name]
        return len(val) if val else 0
    return 0


def _to_out(s: Session) -> SessionOut:
    return SessionOut(
        id=s.id,
        name=s.name,
        visibility=s.visibility or "private",
        owner_id=s.owner_id,
        org_id=s.org_id,
        document_count=_safe_len(s, "documents"),
        entity_count=_safe_len(s, "entities"),
        created_at=s.created_at,
        updated_at=s.updated_at or s.created_at,
    )
