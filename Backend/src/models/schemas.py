"""
Pydantic request / response schemas — pure data contracts (no business logic).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════
#  Auth
# ═══════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    full_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


# ═══════════════════════════════════════════════════════
#  Organisation
# ═══════════════════════════════════════════════════════

class OrganisationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class OrganisationOut(BaseModel):
    id: str
    name: str
    created_at: datetime


# ═══════════════════════════════════════════════════════
#  Session
# ═══════════════════════════════════════════════════════

class SessionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=512)
    visibility: str = "private"   # private | team | org


class SessionOut(BaseModel):
    id: str
    name: str
    visibility: str
    owner_id: str
    org_id: Optional[str] = None
    document_count: int = 0
    entity_count: int = 0
    created_at: datetime
    updated_at: datetime


class SessionListOut(BaseModel):
    sessions: List[SessionOut]


# ═══════════════════════════════════════════════════════
#  Document
# ═══════════════════════════════════════════════════════

class DocumentOut(BaseModel):
    id: str
    session_id: str
    filename: str
    file_type: str
    page_count: int
    entity_count: int = 0
    uploaded_at: datetime


class DocumentListOut(BaseModel):
    documents: List[DocumentOut]


# ═══════════════════════════════════════════════════════
#  Entity (replaces Chunk)
# ═══════════════════════════════════════════════════════

class EntityOut(BaseModel):
    id: str
    session_id: str
    document_id: str
    entity_type: str         # Goal|KPI|OKR|Risk|Action|Owner|Custom
    content: str
    token_count: int
    cluster_id: Optional[int] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime


# ═══════════════════════════════════════════════════════
#  Embedding
# ═══════════════════════════════════════════════════════

class EmbeddingRequest(BaseModel):
    session_id: str


class EmbeddingResult(BaseModel):
    session_id: str
    entities_embedded: int
    tokens_used: int
    cost_usd: float


# ═══════════════════════════════════════════════════════
#  Graph
# ═══════════════════════════════════════════════════════

class GraphNode(BaseModel):
    id: str
    label: str
    type: str                         # entity | cluster
    entity_type: Optional[str] = None  # Goal|KPI|OKR|…
    cluster_id: Optional[int] = None
    metadata: Dict[str, Any] = {}
    x: Optional[float] = None
    y: Optional[float] = None


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float = 1.0
    edge_type: str = "similarity"      # similarity|achieved_by|measured_by|threatens|supports|bridge


class GraphResponse(BaseModel):
    session_id: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class BridgeResponse(BaseModel):
    bridges: List[GraphEdge]
    session_ids: List[str]


# ═══════════════════════════════════════════════════════
#  Chat
# ═══════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    session_id: str
    message: str
    include_bridges: bool = False


class ChatMessageOut(BaseModel):
    role: str
    content: str
    tokens_used: int = 0
    cost_usd: float = 0.0
    created_at: Optional[datetime] = None


class ChatResponse(BaseModel):
    reply: str
    sources: List[Dict[str, Any]] = []
    tokens_used: int = 0
    cost_usd: float = 0.0


# ═══════════════════════════════════════════════════════
#  Cost
# ═══════════════════════════════════════════════════════

class CostSummary(BaseModel):
    total_embedding_tokens: int = 0
    total_chat_tokens: int = 0
    total_embedding_cost: float = 0.0
    total_chat_cost: float = 0.0
    embedding_budget_remaining: float = 0.0
    chat_budget_remaining: float = 0.0
