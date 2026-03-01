"""
FastAPI application entry point.

Responsibilities:
  • Wire routers
  • Set up CORS
  • Run DB init on startup
  • Expose auth endpoints (register / login)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models.db import db_manager, User
from .models.repository import UserRepository
from .models.schemas import RegisterRequest, LoginRequest, TokenResponse
from .utils.auth import AuthService
from .utils.cost_tracker import CostTracker
from .models.schemas import CostSummary

# ── Routers ──
from .routers.sessions import router as sessions_router
from .routers.documents import router as documents_router
from .routers.embeddings import router as embeddings_router
from .routers.graph import router as graph_router
from .routers.chat import router as chat_router
from .routers.dependencies import get_db, get_current_user


# ═══════════════════════════════════════════════════════
#  Lifespan
# ═══════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    # SQL tables
    await db_manager.create_tables()

    # ChromaDB (local persistent vector store)
    try:
        from .services.chroma_store import get_chroma_store
        store = get_chroma_store()
        print(f"✅ ChromaDB ready — {store.count} vectors")
    except Exception as e:
        print(f"⚠️  ChromaDB init failed: {e}")

    # Neo4j (optional — graceful if not available)
    try:
        from .services.neo4j_manager import neo4j_manager
        await neo4j_manager.connect()
        await neo4j_manager.ensure_indexes()
        print("✅ Neo4j connected")
    except Exception as e:
        print(f"⚠️  Neo4j not available (falling back to in-memory graph): {e}")

    yield

    # Shutdown Neo4j
    try:
        from .services.neo4j_manager import neo4j_manager
        await neo4j_manager.close()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════
#  App factory
# ═══════════════════════════════════════════════════════

def create_app() -> FastAPI:
    cfg = get_settings()

    application = FastAPI(
        title="Business Analysis Tool",
        description="Embedding + Contextual Graph based Knowledge Platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    application.include_router(sessions_router)
    application.include_router(documents_router)
    application.include_router(embeddings_router)
    application.include_router(graph_router)
    application.include_router(chat_router)

    # ── Inline auth routes (lightweight, no separate router file) ──

    _auth = AuthService()

    @application.post("/api/auth/register", response_model=TokenResponse, tags=["Auth"])
    async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
        repo = UserRepository(db)
        existing = await repo.get_by_email(body.email)
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

        user = User(
            email=body.email,
            hashed_password=_auth.hash_password(body.password),
            full_name=body.full_name,
        )
        await repo.add(user)
        await repo.commit()

        token = _auth.create_token(user.id, user.email)
        return TokenResponse(
            access_token=token, user_id=user.id, email=user.email,
        )

    @application.post("/api/auth/login", response_model=TokenResponse, tags=["Auth"])
    async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
        repo = UserRepository(db)
        user = await repo.get_by_email(body.email)
        if not user or not _auth.verify_password(body.password, user.hashed_password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

        token = _auth.create_token(user.id, user.email)
        return TokenResponse(
            access_token=token, user_id=user.id, email=user.email,
        )

    # ── Cost endpoint ──

    @application.get("/api/cost/usage", response_model=CostSummary, tags=["Cost"])
    async def cost_usage(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        tracker = CostTracker(db)
        return CostSummary(**(await tracker.get_summary()))

    # ── Health check ──

    @application.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok"}

    return application


app = create_app()
