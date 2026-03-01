"""
/api/documents — upload & parse documents into a session.
Supports contextual chunking via user notes.
Entities (typed business-object chunks) replace plain chunks.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db import Document, Entity, Session, User
from ..models.repository import DocumentRepository, EntityRepository, SessionRepository
from ..models.schemas import DocumentOut, DocumentListOut
from ..services.extractor import ExtractorFactory
from ..services.chunker import TextChunker
from .dependencies import get_db, get_current_user

router = APIRouter(prefix="/api/documents", tags=["Documents"])

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".csv", ".xlsx", ".xls", ".txt"}


# ═══════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════

@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    user_notes: str = Form(""),
    contextual: bool = Form(False),
    entity_type: str = Form("Custom"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate session ownership
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    # Validate extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported file type: {ext}. Allowed: {_ALLOWED_EXTENSIONS}",
        )

    # Read & extract
    file_bytes = await file.read()
    text, page_count = ExtractorFactory.extract_text(file_bytes, file.filename or "file.txt")

    # Persist document
    doc_repo = DocumentRepository(db)
    doc = Document(
        session_id=session_id,
        filename=file.filename or "unknown",
        file_type=ext.lstrip("."),
        page_count=page_count,
        raw_text=text,
    )
    await doc_repo.add(doc)

    # Chunk — full LangGraph pipeline (contextual + Neo4j graph) or basic semantic
    chunker = TextChunker()
    if contextual:
        chunk_results = await chunker.chunk_with_context(
            text,
            user_notes=user_notes,
            session_id=session_id,
        )
    else:
        chunk_results = chunker.chunk(text)

    # Create Entity records (vectors will be added later via /embeddings/generate)
    entity_repo = EntityRepository(db)
    entity_records = [
        Entity(
            session_id=session_id,
            document_id=doc.id,
            entity_type=entity_type,
            content=cr.content,
            token_count=cr.token_count,
            metadata_={
                "chunk_index": cr.index,
                "context": getattr(cr, "context", ""),
                "strategy": getattr(cr, "strategy", "semantic"),
                "graph_context": getattr(cr, "graph_context", ""),
            },
        )
        for cr in chunk_results
    ]
    await entity_repo.add_many(entity_records)
    await doc_repo.commit()

    # Sync to Neo4j (best-effort)
    try:
        from ..services.neo4j_manager import neo4j_manager, KnowledgeGraphService
        if neo4j_manager._driver is not None:
            kg = KnowledgeGraphService()
            await kg.upsert_session(session_id, session.name)
            await kg.upsert_document(doc.id, session_id, doc.filename)
            await kg.upsert_chunks(
                [
                    {
                        "id": e.id,
                        "content": e.content,
                        "document_id": e.document_id,
                        "token_count": e.token_count,
                        "context": e.metadata_.get("context", ""),
                    }
                    for e in entity_records
                ],
                session_id,
            )
            if user_notes:
                import uuid
                note_id = f"note-{uuid.uuid4().hex[:12]}"
                await kg.upsert_user_note(
                    note_id=note_id,
                    session_id=session_id,
                    document_id=doc.id,
                    content=user_notes,
                )
    except Exception:
        pass  # Neo4j sync is best-effort

    return DocumentOut(
        id=doc.id,
        session_id=doc.session_id,
        filename=doc.filename,
        file_type=doc.file_type,
        page_count=doc.page_count,
        entity_count=len(entity_records),
        uploaded_at=doc.uploaded_at,
    )


@router.get("/{session_id}", response_model=DocumentListOut)
async def list_documents(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    doc_repo = DocumentRepository(db)
    entity_repo = EntityRepository(db)
    docs = await doc_repo.list_by_session(session_id)

    result = []
    for d in docs:
        entities = await entity_repo.list_by_document(d.id)
        result.append(DocumentOut(
            id=d.id,
            session_id=d.session_id,
            filename=d.filename,
            file_type=d.file_type,
            page_count=d.page_count,
            entity_count=len(entities),
            uploaded_at=d.uploaded_at,
        ))
    return DocumentListOut(documents=result)
