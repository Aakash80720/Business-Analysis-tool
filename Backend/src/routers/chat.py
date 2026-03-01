"""
/api/chat — RAG chat grounded in session documents.

Conversation history is managed by LangGraph's MemorySaver (keyed by
session_id as the thread_id).  Vector retrieval is handled by ChromaDB
inside the ChatEngine — the router just passes the session_id.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db import User, ChatMessage
from ..models.repository import (
    SessionRepository, ChatMessageRepository,
)
from ..models.schemas import ChatRequest, ChatResponse, ChatMessageOut
from ..services.chat_engine import ChatEngine
from .dependencies import get_db, get_current_user, get_chat_engine

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    engine: ChatEngine = Depends(get_chat_engine),
):
    # Validate session
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(body.session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    # Run RAG — ChromaDB retrieval + LangGraph memory handles everything
    result = await engine.answer(
        body.message,
        session_id=body.session_id,
    )

    # Persist messages to SQL (audit trail / backup)
    msg_repo = ChatMessageRepository(db)
    user_msg = ChatMessage(
        session_id=body.session_id,
        role="user",
        content=body.message,
    )
    assistant_msg = ChatMessage(
        session_id=body.session_id,
        role="assistant",
        content=result.reply,
        tokens_used=result.tokens_used,
        cost_usd=result.cost_usd,
    )
    await msg_repo.add(user_msg)
    await msg_repo.add(assistant_msg)
    await msg_repo.commit()

    return ChatResponse(
        reply=result.reply,
        sources=result.sources,
        tokens_used=result.tokens_used,
        cost_usd=result.cost_usd,
    )


@router.get("/{session_id}/history", response_model=list[ChatMessageOut])
async def get_chat_history(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    engine: ChatEngine = Depends(get_chat_engine),
):
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    # Primary source: LangGraph memory (real-time, in-process)
    lg_history = await engine.get_memory_history(session_id)
    if lg_history:
        return [
            ChatMessageOut(
                role=m["role"],
                content=m["content"],
                tokens_used=0,
                cost_usd=0.0,
                created_at=None,
            )
            for m in lg_history
        ]

    # Fallback: SQL audit log
    msg_repo = ChatMessageRepository(db)
    messages = await msg_repo.list_by_session(session_id)

    return [
        ChatMessageOut(
            role=m.role,
            content=m.content,
            tokens_used=m.tokens_used,
            cost_usd=m.cost_usd,
            created_at=m.created_at,
        )
        for m in messages
    ]
