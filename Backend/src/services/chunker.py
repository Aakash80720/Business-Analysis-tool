"""
Advanced text chunker — LangChain + LangGraph powered semantic & contextual
chunking with Neo4j knowledge-graph-aware context enrichment.

Pipeline (orchestrated by LangGraph):

  ┌─────────────┐   ┌──────────────────┐   ┌──────────────────┐
  │  preprocess  │──▶│  semantic_split  │──▶│  recursive_guard │
  └─────────────┘   └──────────────────┘   └──────────────────┘
                                                     │
                 ┌───────────────────────────────────┘
                 ▼
        ┌─────────────────┐   ┌───────────────────┐   ┌──────────┐
        │  enrich_context  │──▶│  neo4j_graph_ctx  │──▶│  finish  │
        └─────────────────┘   └───────────────────┘   └──────────┘

Uses:
  • LangChain SemanticChunker  — splits on embedding-distance breakpoints
  • LangChain RecursiveCharacterTextSplitter — token-aware fallback
  • LangGraph StateGraph       — orchestrates the multi-step chunking flow
  • OpenAI LLM                 — contextual summary per chunk (Contextual Retrieval)
  • Neo4j                      — pulls related knowledge-graph context from
                                 user notes / prior documents to enrich chunks

Single Responsibility: splitting text into semantically coherent, contextually
enriched chunks ready for embedding.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypedDict

import tiktoken
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, END

from ..config import get_settings
from ..prompts import CHUNK_CONTEXT_SYSTEM, CHUNK_CONTEXT_HUMAN

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
#  Value objects
# ═══════════════════════════════════════════════════════

@dataclass(frozen=True)
class ChunkResult:
    """Immutable value object representing a single chunk."""
    content: str                     # final text (may include prepended context)
    token_count: int
    index: int
    context: str = ""               # LLM-generated contextual summary
    strategy: str = "semantic"      # which splitter produced it
    graph_context: str = ""         # related knowledge from Neo4j


class ChunkStrategy:
    SEMANTIC   = "semantic"
    RECURSIVE  = "recursive"
    CONTEXTUAL = "contextual"


# ═══════════════════════════════════════════════════════
#  Token counting helpers
# ═══════════════════════════════════════════════════════

def _get_encoder(model: str | None = None) -> tiktoken.Encoding:
    model = model or get_settings().openai_embedding_model
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str, encoder: tiktoken.Encoding) -> int:
    return len(encoder.encode(text))


# ═══════════════════════════════════════════════════════
#  LangGraph State — flows through every pipeline node
# ═══════════════════════════════════════════════════════

class ChunkPipelineState(TypedDict):
    """Typed state flowing through the LangGraph chunking pipeline."""
    raw_text: str                          # original document text
    cleaned_text: str                      # after preprocessing
    user_notes: str                        # user-supplied notes / context
    session_id: str                        # for Neo4j lookups
    contextual: bool                       # whether to run contextual pass
    semantic_chunks: List[Dict[str, Any]]  # after semantic split
    final_chunks: List[Dict[str, Any]]     # after recursive guard
    enriched_chunks: List[Dict[str, Any]]  # after LLM context enrichment
    graph_enriched_chunks: List[Dict[str, Any]]  # after Neo4j enrichment
    results: List[ChunkResult]             # final output


# ═══════════════════════════════════════════════════════
#  LangChain Splitter wrappers
# ═══════════════════════════════════════════════════════

class _SemanticSplitter:
    """Wraps LangChain's SemanticChunker with project defaults."""

    def __init__(
        self,
        breakpoint_threshold_type: str = "percentile",
        breakpoint_threshold_amount: float = 85.0,
    ) -> None:
        cfg = get_settings()
        self._embeddings = OpenAIEmbeddings(
            model=cfg.openai_embedding_model,
            openai_api_key=cfg.openai_api_key,
        )
        self._splitter = SemanticChunker(
            embeddings=self._embeddings,
            breakpoint_threshold_type=breakpoint_threshold_type,
            breakpoint_threshold_amount=breakpoint_threshold_amount,
        )

    def split(self, text: str) -> List[str]:
        docs = self._splitter.create_documents([text])
        return [d.page_content.strip() for d in docs if d.page_content.strip()]


class _RecursiveSplitter:
    """Wraps LangChain's RecursiveCharacterTextSplitter (token-aware)."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64) -> None:
        enc = _get_encoder()
        self._splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=enc.name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""],
        )

    def split(self, text: str) -> List[str]:
        docs = self._splitter.create_documents([text])
        return [d.page_content.strip() for d in docs if d.page_content.strip()]


# ═══════════════════════════════════════════════════════
#  LangChain context-enrichment chain
# ═══════════════════════════════════════════════════════

_CONTEXT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", CHUNK_CONTEXT_SYSTEM),
    ("human", CHUNK_CONTEXT_HUMAN),
])


def _build_context_chain():
    """Return a LangChain runnable: prompt → LLM → string."""
    cfg = get_settings()
    llm = ChatOpenAI(
        model=cfg.openai_model,
        api_key=cfg.openai_api_key,
        temperature=0.0,
        max_tokens=200,
    )
    return _CONTEXT_PROMPT | llm | StrOutputParser()


# ═══════════════════════════════════════════════════════
#  LangGraph pipeline nodes
# ═══════════════════════════════════════════════════════

async def _node_preprocess(state: ChunkPipelineState) -> dict:
    """
    Step 1 — Clean raw text: normalise whitespace, strip control chars.
    """
    text = state["raw_text"]
    # Collapse 3+ newlines → 2, strip null bytes
    text = re.sub(r"\x00", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return {"cleaned_text": text}


async def _node_semantic_split(state: ChunkPipelineState) -> dict:
    """
    Step 2 — Semantic split using embedding-distance breakpoints.
    Falls back to recursive split if text is too short or semantic
    splitter produces only one chunk.
    """
    text = state["cleaned_text"]
    encoder = _get_encoder()
    token_count = _count_tokens(text, encoder)

    # Semantic splitting needs enough text to detect topic shifts
    MIN_TOKENS_FOR_SEMANTIC = 200
    chunks: List[Dict[str, Any]] = []

    if token_count >= MIN_TOKENS_FOR_SEMANTIC:
        try:
            splitter = _SemanticSplitter()
            parts = splitter.split(text)
            if len(parts) > 1:
                for idx, part in enumerate(parts):
                    chunks.append({
                        "content": part,
                        "token_count": _count_tokens(part, encoder),
                        "index": idx,
                        "strategy": ChunkStrategy.SEMANTIC,
                    })
                return {"semantic_chunks": chunks}
        except Exception as exc:
            logger.warning("Semantic split failed, falling back: %s", exc)

    # Fallback: recursive
    splitter = _RecursiveSplitter()
    parts = splitter.split(text)
    for idx, part in enumerate(parts):
        chunks.append({
            "content": part,
            "token_count": _count_tokens(part, encoder),
            "index": idx,
            "strategy": ChunkStrategy.RECURSIVE,
        })
    return {"semantic_chunks": chunks}


async def _node_recursive_guard(state: ChunkPipelineState) -> dict:
    """
    Step 3 — Post-split guard: any chunk exceeding 1024 tokens is
    re-split with the recursive splitter to enforce size limits.
    """
    encoder = _get_encoder()
    MAX_CHUNK_TOKENS = 1024
    guarded: List[Dict[str, Any]] = []
    idx = 0

    resplitter = _RecursiveSplitter(chunk_size=512, chunk_overlap=64)

    for ch in state["semantic_chunks"]:
        if ch["token_count"] > MAX_CHUNK_TOKENS:
            sub_parts = resplitter.split(ch["content"])
            for sub in sub_parts:
                guarded.append({
                    "content": sub,
                    "token_count": _count_tokens(sub, encoder),
                    "index": idx,
                    "strategy": ChunkStrategy.RECURSIVE,
                })
                idx += 1
        else:
            guarded.append({**ch, "index": idx})
            idx += 1

    return {"final_chunks": guarded}


async def _node_enrich_context(state: ChunkPipelineState) -> dict:
    """
    Step 4 — Contextual Retrieval: call LLM for each chunk to produce
    a contextual summary that situates it within the document + user notes.
    Skipped if `contextual` is False.
    """
    if not state.get("contextual"):
        # Pass through unchanged
        return {"enriched_chunks": state["final_chunks"]}

    chain = _build_context_chain()
    doc_preview = state["cleaned_text"][:8000]
    user_notes = state.get("user_notes", "")
    user_notes_block = (
        f"## User Notes\n{user_notes}\n\n" if user_notes else ""
    )

    enriched: List[Dict[str, Any]] = []

    # Process in small batches to avoid rate limits
    BATCH_SIZE = 5
    chunks = state["final_chunks"]

    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[batch_start : batch_start + BATCH_SIZE]
        tasks = [
            chain.ainvoke({
                "document": doc_preview,
                "chunk": ch["content"],
                "user_notes_block": user_notes_block,
                "graph_context_block": "",  # filled in next step
            })
            for ch in batch
        ]
        contexts = await asyncio.gather(*tasks, return_exceptions=True)

        for ch, ctx in zip(batch, contexts):
            if isinstance(ctx, Exception):
                logger.warning("Context enrichment failed for chunk %s: %s", ch["index"], ctx)
                ctx_str = ""
            else:
                ctx_str = str(ctx).strip()

            enriched_content = f"{ctx_str}\n\n{ch['content']}" if ctx_str else ch["content"]
            enriched.append({
                **ch,
                "content": enriched_content,
                "context": ctx_str,
                "token_count": _count_tokens(
                    enriched_content, _get_encoder(),
                ),
                "strategy": ChunkStrategy.CONTEXTUAL,
            })

    return {"enriched_chunks": enriched}


async def _node_neo4j_graph_context(state: ChunkPipelineState) -> dict:
    """
    Step 5 — Neo4j Knowledge Graph enrichment: for each chunk, query
    the graph for related nodes from prior documents / user notes stored
    in the same session. This pulls in cross-document context.

    If Neo4j is unavailable, this step is a no-op.
    """
    enriched = state.get("enriched_chunks", state["final_chunks"])
    session_id = state.get("session_id", "")

    if not session_id:
        return {"graph_enriched_chunks": enriched}

    try:
        from .neo4j_manager import neo4j_manager, KnowledgeGraphService
        if neo4j_manager._driver is None:
            return {"graph_enriched_chunks": enriched}

        kg = KnowledgeGraphService()

        # 1. Fetch all user notes for this session (overall document context)
        try:
            session_notes = await kg.get_user_notes_for_session(session_id)
            notes_context = "\n".join(
                f"[Note for {n['document']}] {n['content']}"
                for n in session_notes if n["content"]
            )
        except Exception:
            notes_context = ""

        # 2. Full-text search each chunk's content against the existing graph
        #    to find related prior knowledge
        graph_enriched: List[Dict[str, Any]] = []
        encoder = _get_encoder()

        for ch in enriched:
            # Extract key phrases (first 200 chars) for graph search
            search_text = ch["content"][:200]
            try:
                related_chunks = await _query_graph_context(kg, session_id, search_text)
            except Exception:
                related_chunks = ""

            # Also search user notes for related context
            try:
                related_notes = await kg.search_notes_fulltext(
                    search_text[:100], session_id, limit=3,
                )
                notes_str = "\n".join(f"[User Note] {n}" for n in related_notes if n)
            except Exception:
                notes_str = ""

            # Combine all graph context sources
            all_related_parts = [p for p in [related_chunks, notes_str, notes_context] if p]
            related = "\n---\n".join(all_related_parts) if all_related_parts else ""

            if related:
                graph_content = f"{ch['content']}\n\n[Related Knowledge]\n{related}"
                graph_enriched.append({
                    **ch,
                    "content": graph_content,
                    "graph_context": related,
                    "token_count": _count_tokens(graph_content, encoder),
                })
            else:
                graph_enriched.append({**ch, "graph_context": ""})

        return {"graph_enriched_chunks": graph_enriched}

    except Exception as exc:
        logger.warning("Neo4j graph context step skipped: %s", exc)
        return {"graph_enriched_chunks": enriched}


async def _query_graph_context(
    kg: Any,
    session_id: str,
    search_text: str,
) -> str:
    """
    Query Neo4j full-text index for chunks related to `search_text`
    within the same session. Returns a combined string of related content.
    """
    from .neo4j_manager import neo4j_manager

    async with neo4j_manager.driver.session() as s:
        # Use full-text search index on chunk content
        result = await s.run(
            "CALL db.index.fulltext.queryNodes('chunkContentIndex', $query) "
            "YIELD node, score "
            "WHERE node.session_id = $sid AND score > 0.5 "
            "RETURN node.content AS content, node.context AS context, score "
            "ORDER BY score DESC "
            "LIMIT 3",
            query=search_text[:100],
            sid=session_id,
        )
        parts: List[str] = []
        async for record in result:
            ctx = record["context"] or ""
            content = (record["content"] or "")[:300]
            prefix = f"[{ctx}] " if ctx else ""
            parts.append(f"{prefix}{content}")

    return "\n---\n".join(parts) if parts else ""


async def _node_finish(state: ChunkPipelineState) -> dict:
    """
    Step 6 — Convert enriched dicts into immutable ChunkResult objects.
    """
    source = state.get("graph_enriched_chunks") or state.get("enriched_chunks") or state["final_chunks"]
    encoder = _get_encoder()
    results: List[ChunkResult] = []

    for ch in source:
        results.append(ChunkResult(
            content=ch["content"],
            token_count=ch.get("token_count", _count_tokens(ch["content"], encoder)),
            index=ch["index"],
            context=ch.get("context", ""),
            strategy=ch.get("strategy", ChunkStrategy.SEMANTIC),
            graph_context=ch.get("graph_context", ""),
        ))

    return {"results": results}


# ═══════════════════════════════════════════════════════
#  LangGraph pipeline builder
# ═══════════════════════════════════════════════════════

def _build_chunk_pipeline() -> StateGraph:
    """
    Construct the LangGraph state machine for the chunking pipeline:

      preprocess → semantic_split → recursive_guard → enrich_context
          → neo4j_graph_ctx → finish
    """
    workflow = StateGraph(ChunkPipelineState)

    workflow.add_node("preprocess", _node_preprocess)
    workflow.add_node("semantic_split", _node_semantic_split)
    workflow.add_node("recursive_guard", _node_recursive_guard)
    workflow.add_node("enrich_context", _node_enrich_context)
    workflow.add_node("neo4j_graph_ctx", _node_neo4j_graph_context)
    workflow.add_node("finish", _node_finish)

    workflow.set_entry_point("preprocess")
    workflow.add_edge("preprocess", "semantic_split")
    workflow.add_edge("semantic_split", "recursive_guard")
    workflow.add_edge("recursive_guard", "enrich_context")
    workflow.add_edge("enrich_context", "neo4j_graph_ctx")
    workflow.add_edge("neo4j_graph_ctx", "finish")
    workflow.add_edge("finish", END)

    return workflow


# ═══════════════════════════════════════════════════════
#  Public API — TextChunker facade
# ═══════════════════════════════════════════════════════

class TextChunker:
    """
    Main entry point for all chunking operations.

    Wraps the full LangGraph pipeline and exposes both sync
    (basic split) and async (contextual + graph-enriched) modes.

    Parameters
    ----------
    max_tokens : int
        Maximum tokens per chunk (enforced by recursive guard).
    overlap_tokens : int
        Token overlap for recursive splitting.
    breakpoint_threshold : float
        Percentile threshold for semantic breakpoints (0-100).
    """

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 64,
        breakpoint_threshold: float = 85.0,
    ) -> None:
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens
        self._breakpoint_threshold = breakpoint_threshold
        self._encoder = _get_encoder()

    # ── Sync: basic semantic / recursive split (no LLM, no graph) ──

    def chunk(self, text: str) -> List[ChunkResult]:
        """
        Synchronous split — semantic-first with recursive fallback.
        No LLM context enrichment, no Neo4j.
        """
        token_count = _count_tokens(text, self._encoder)

        if token_count >= 200:
            try:
                splitter = _SemanticSplitter(
                    breakpoint_threshold_amount=self._breakpoint_threshold,
                )
                parts = splitter.split(text)
                if len(parts) > 1:
                    return self._to_results(parts, ChunkStrategy.SEMANTIC)
            except Exception as exc:
                logger.warning("Semantic split failed: %s", exc)

        # Fallback
        splitter = _RecursiveSplitter(
            chunk_size=self._max_tokens,
            chunk_overlap=self._overlap_tokens,
        )
        parts = splitter.split(text)
        return self._to_results(parts, ChunkStrategy.RECURSIVE)

    # ── Async: full LangGraph pipeline (contextual + graph) ──

    async def chunk_with_context(
        self,
        text: str,
        user_notes: str = "",
        session_id: str = "",
    ) -> List[ChunkResult]:
        """
        Full async pipeline: semantic split → recursive guard →
        LLM contextual enrichment → Neo4j graph context.

        Parameters
        ----------
        text : document text
        user_notes : user-provided notes / context for the document
        session_id : session ID for Neo4j graph lookups
        """
        pipeline = _build_chunk_pipeline().compile()

        initial_state: ChunkPipelineState = {
            "raw_text": text,
            "cleaned_text": "",
            "user_notes": user_notes,
            "session_id": session_id,
            "contextual": True,
            "semantic_chunks": [],
            "final_chunks": [],
            "enriched_chunks": [],
            "graph_enriched_chunks": [],
            "results": [],
        }

        final_state = await pipeline.ainvoke(initial_state)
        return final_state["results"]

    # ── Helper ──

    def _to_results(self, parts: List[str], strategy: str) -> List[ChunkResult]:
        results: List[ChunkResult] = []
        idx = 0
        for part in parts:
            part = part.strip()
            if not part:
                continue
            tok_count = _count_tokens(part, self._encoder)
            # Enforce max token limit via recursive re-split
            if tok_count > self._max_tokens * 2:
                sub_splitter = _RecursiveSplitter(
                    chunk_size=self._max_tokens,
                    chunk_overlap=self._overlap_tokens,
                )
                for sub in sub_splitter.split(part):
                    sub = sub.strip()
                    if sub:
                        results.append(ChunkResult(
                            content=sub,
                            token_count=_count_tokens(sub, self._encoder),
                            index=idx,
                            strategy=ChunkStrategy.RECURSIVE,
                        ))
                        idx += 1
            else:
                results.append(ChunkResult(
                    content=part,
                    token_count=tok_count,
                    index=idx,
                    strategy=strategy,
                ))
                idx += 1
        return results


# ═══════════════════════════════════════════════════════
#  Convenience: standalone semantic & recursive chunkers
#  (kept for backward compat / direct use)
# ═══════════════════════════════════════════════════════

LangChainSemanticChunker = _SemanticSplitter
LangChainRecursiveChunker = _RecursiveSplitter
