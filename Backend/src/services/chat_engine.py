"""
LangGraph RAG chat engine — GPT-4o grounded in session entity embeddings
with graph-enhanced retrieval from Neo4j.

Memory is managed **entirely by LangGraph's checkpointer** (MemorySaver).
Each *session* gets its own ``thread_id`` so conversation context is
persisted across calls and isolated between sessions for the same user.

Pipeline (LangGraph StateGraph with MemorySaver):

  embed_query → retrieve_vectors → expand_graph → build_prompt → call_llm

Uses:
  • LangGraph MemorySaver — session-scoped persistent conversation memory
  • add_messages reducer  — automatic message-list management
  • ChromaDB              — vector similarity retrieval
  • Neo4j                 — graph-context expansion (neighbour traversal)
  • OpenAI                — LLM completion
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Annotated, Dict, List, Sequence, TypedDict

from openai import AsyncOpenAI

from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, SystemMessage,
)
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from ..config import get_settings
from ..prompts import RAG_SYSTEM_TEMPLATE
from ..utils.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
#  Result DTO
# ═══════════════════════════════════════════════════════

@dataclass
class ChatResult:
    reply: str
    sources: List[Dict[str, Any]]
    tokens_used: int
    cost_usd: float


# ═══════════════════════════════════════════════════════
#  LangGraph State
# ═══════════════════════════════════════════════════════

class RAGState(TypedDict):
    """
    State flowing through the LangGraph RAG pipeline.

    ``messages`` uses the ``add_messages`` reducer so LangGraph
    automatically appends new messages and persists the full
    conversation via the checkpointer.
    """
    # ── Managed by LangGraph memory (add_messages reducer) ──
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # ── Per-invocation (transient, set fresh each call) ──
    user_message: str
    session_id: str
    query_embedding: List[float]
    top_entities: List[Dict[str, Any]]
    graph_context: List[Dict[str, Any]]
    system_prompt: str
    reply: str
    sources: List[Dict[str, Any]]
    tokens_used: int
    cost_usd: float


# ═══════════════════════════════════════════════════════
#  Module-level MemorySaver (singleton)
# ═══════════════════════════════════════════════════════

_memory = MemorySaver()


# ═══════════════════════════════════════════════════════
#  Chat Engine (LangGraph-powered with session memory)
# ═══════════════════════════════════════════════════════

class ChatEngine:
    """
    Orchestrates RAG via a LangGraph state machine with **built-in
    session memory** (MemorySaver).

    Conversation history is no longer passed manually — LangGraph
    persists and replays it automatically using ``thread_id = session_id``.

    Vector retrieval is done via ChromaDB (not from SQL).

    Pipeline:
      embed_query → retrieve_vectors → expand_graph → build_prompt → call_llm
    """

    TOP_K = 8
    SYSTEM_TEMPLATE = RAG_SYSTEM_TEMPLATE
    MAX_HISTORY_MESSAGES = 40

    def __init__(self, cost_tracker: CostTracker) -> None:
        cfg = get_settings()
        self._client = AsyncOpenAI(api_key=cfg.openai_api_key)
        self._chat_model = cfg.openai_model
        self._embed_model = cfg.openai_embedding_model
        self._cost_tracker = cost_tracker
        self._graph_service = None
        self._compiled_graph = self._build_rag_graph()

    def _get_graph_service(self):
        if self._graph_service is None:
            try:
                from .neo4j_manager import KnowledgeGraphService
                self._graph_service = KnowledgeGraphService()
            except Exception:
                self._graph_service = None
        return self._graph_service

    # ── Public API ──

    async def answer(
        self,
        user_message: str,
        session_id: str,
    ) -> ChatResult:
        """
        Run the full RAG pipeline via LangGraph.

        ``session_id`` is used as the LangGraph ``thread_id`` AND
        to scope ChromaDB vector retrieval.
        """
        initial_state: dict = {
            "user_message": user_message,
            "session_id": session_id,
            "messages": [HumanMessage(content=user_message)],
            "query_embedding": [],
            "top_entities": [],
            "graph_context": [],
            "system_prompt": "",
            "reply": "",
            "sources": [],
            "tokens_used": 0,
            "cost_usd": 0.0,
        }

        config = {"configurable": {"thread_id": session_id}}

        final_state = await self._compiled_graph.ainvoke(
            initial_state, config=config,
        )

        return ChatResult(
            reply=final_state["reply"],
            sources=final_state["sources"],
            tokens_used=final_state["tokens_used"],
            cost_usd=final_state["cost_usd"],
        )

    async def get_memory_history(
        self, session_id: str,
    ) -> List[Dict[str, str]]:
        config = {"configurable": {"thread_id": session_id}}
        try:
            snapshot = await self._compiled_graph.aget_state(config)
            messages: Sequence[BaseMessage] = snapshot.values.get("messages", [])
            return [
                {
                    "role": "user" if isinstance(m, HumanMessage) else "assistant",
                    "content": m.content,
                }
                for m in messages
                if isinstance(m, (HumanMessage, AIMessage))
            ]
        except Exception:
            return []

    # ── Graph builder ──

    def _build_rag_graph(self):
        workflow = StateGraph(RAGState)

        workflow.add_node("embed_query", self._node_embed_query)
        workflow.add_node("retrieve_vectors", self._node_retrieve_vectors)
        workflow.add_node("expand_graph", self._node_expand_graph)
        workflow.add_node("build_prompt", self._node_build_prompt)
        workflow.add_node("call_llm", self._node_call_llm)

        workflow.set_entry_point("embed_query")
        workflow.add_edge("embed_query", "retrieve_vectors")
        workflow.add_edge("retrieve_vectors", "expand_graph")
        workflow.add_edge("expand_graph", "build_prompt")
        workflow.add_edge("build_prompt", "call_llm")
        workflow.add_edge("call_llm", END)

        return workflow.compile(checkpointer=_memory)

    # ── Pipeline nodes ──

    async def _node_embed_query(self, state: RAGState) -> dict:
        resp = await self._client.embeddings.create(
            input=[state["user_message"]],
            model=self._embed_model,
        )
        return {"query_embedding": resp.data[0].embedding}

    async def _node_retrieve_vectors(self, state: RAGState) -> dict:
        """Step 2: Retrieve top-K entities from ChromaDB by cosine similarity."""
        from .chroma_store import get_chroma_store

        query_emb = state["query_embedding"]
        if not query_emb:
            return {"top_entities": []}

        store = get_chroma_store()
        results = store.query(
            query_embedding=query_emb,
            n_results=self.TOP_K,
            session_id=state["session_id"],
        )
        return {"top_entities": results}

    async def _node_expand_graph(self, state: RAGState) -> dict:
        graph_svc = self._get_graph_service()
        top_entities = state["top_entities"]

        if not graph_svc or not top_entities:
            return {"graph_context": []}

        try:
            from .neo4j_manager import neo4j_manager
            if neo4j_manager._driver is None:
                return {"graph_context": []}

            seed_ids = [e["id"] for e in top_entities]
            neighbours = await graph_svc.get_chunk_neighbours(seed_ids, depth=2)
            top_ids = {e["id"] for e in top_entities}
            unique_neighbours = [n for n in neighbours if n["id"] not in top_ids]
            return {"graph_context": unique_neighbours[:10]}
        except Exception:
            return {"graph_context": []}

    async def _node_build_prompt(self, state: RAGState) -> dict:
        # Vector context
        vector_parts = []
        for e in state["top_entities"]:
            meta = e.get("metadata", {})
            etype = meta.get("entity_type", "")
            prefix = f"[{etype}] " if etype else ""
            vector_parts.append(f"[Source: {e['id'][:8]}] {prefix}{e['content']}")
        vector_context = "\n---\n".join(vector_parts) if vector_parts else "(no documents)"

        # Graph context
        graph_parts = []
        for n in state["graph_context"]:
            ctx = n.get("context", "")
            prefix = f"[Context: {ctx}] " if ctx else ""
            graph_parts.append(
                f"[Related, {n['hops']} hops away] {prefix}{n['content'][:300]}"
            )
        graph_context = "\n---\n".join(graph_parts) if graph_parts else "(no graph context)"

        system_prompt = self.SYSTEM_TEMPLATE.format(
            vector_context=vector_context,
            graph_context=graph_context,
        )
        return {"system_prompt": system_prompt}

    async def _node_call_llm(self, state: RAGState) -> dict:
        all_messages: Sequence[BaseMessage] = state.get("messages", [])
        trimmed = all_messages[-self.MAX_HISTORY_MESSAGES:]

        openai_messages: list[dict] = [
            {"role": "system", "content": state["system_prompt"]},
        ]
        for m in trimmed:
            if isinstance(m, HumanMessage):
                openai_messages.append({"role": "user", "content": m.content})
            elif isinstance(m, AIMessage):
                openai_messages.append({"role": "assistant", "content": m.content})
            elif isinstance(m, SystemMessage):
                openai_messages.append({"role": "system", "content": m.content})

        response = await self._client.chat.completions.create(
            model=self._chat_model,
            messages=openai_messages,
            temperature=0.3,
        )

        reply = response.choices[0].message.content or ""
        tokens_used = response.usage.total_tokens if response.usage else 0
        cost = await self._cost_tracker.log_chat(tokens_used, self._chat_model)

        sources = [
            {"entity_id": e["id"], "content_preview": e["content"][:200]}
            for e in state["top_entities"]
        ]

        return {
            "messages": [AIMessage(content=reply)],
            "reply": reply,
            "sources": sources,
            "tokens_used": tokens_used,
            "cost_usd": cost,
        }
