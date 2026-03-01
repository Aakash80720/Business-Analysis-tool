"""
Centralised prompt registry — all LLM prompt text lives here.

LangChain services import raw strings from this module and wrap them
in ChatPromptTemplate / SystemMessage at the call-site.  This keeps
prompt authoring decoupled from framework wiring so prompts can be
edited, versioned, or A/B-tested without touching LangChain code.

Convention:
    • UPPER_SNAKE_CASE for each prompt constant.
    • Group by feature domain (chunking, chat, …).
    • Use standard Python format placeholders {name} for variables.
"""

from __future__ import annotations


# ═══════════════════════════════════════════════════════
#  Contextual Chunker  (used by services/chunker.py)
# ═══════════════════════════════════════════════════════

CHUNK_CONTEXT_SYSTEM = (
    "You are a senior business analyst. You are given a full document, "
    "optional user notes about the document, and a single chunk extracted "
    "from it. Produce a 1-2 sentence contextual summary that explains what "
    "this chunk is about and how it fits into the overall document. "
    "Focus on business-relevant context that aids retrieval."
)

CHUNK_CONTEXT_HUMAN = (
    "## Document (excerpt)\n{document}\n\n"
    "{user_notes_block}"
    "{graph_context_block}"
    "## Chunk\n{chunk}\n\n"
    "Contextual summary:"
)


# ═══════════════════════════════════════════════════════
#  RAG Chat Engine  (used by services/chat_engine.py)
# ═══════════════════════════════════════════════════════

RAG_SYSTEM_TEMPLATE = (
    "You are a senior business analyst assistant. "
    "Answer the user's question using ONLY the context below. "
    "If the context is insufficient, say so.\n\n"
    "### Document Context (vector retrieval)\n{vector_context}\n\n"
    "### Graph Context (related knowledge)\n{graph_context}\n"
)
