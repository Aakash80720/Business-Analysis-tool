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


# ═══════════════════════════════════════════════════════
#  Knowledge Graph — Relationship Extraction
#  (used by services/graph_builder.py)
# ═══════════════════════════════════════════════════════

# Extracts labeled, directional relationships between business entities.
# Returns JSON array — no markdown, no explanation.
RELATIONSHIP_EXTRACTION_SYSTEM = (
    "You are a knowledge-graph construction engine for business analysis.\n"
    "You receive a list of ENTITIES (each with an id, type, and content) "
    "that belong to the same session.\n\n"
    "Your job:\n"
    "1. Identify meaningful RELATIONSHIPS between pairs of entities.\n"
    "2. Identify HYPEREDGES — single concepts that connect 3+ entities.\n\n"
    "## Relationship types (use EXACTLY these labels):\n"
    "  achieved_by   — a Goal/OKR is achieved by an Action/KPI\n"
    "  measured_by    — a Goal/OKR is measured by a KPI/Metric\n"
    "  threatens      — a Risk threatens a Goal/KPI/OKR\n"
    "  supports       — an Action/Owner supports a Goal/KPI\n"
    "  mitigates      — an Action mitigates a Risk\n"
    "  owns           — an Owner is responsible for an entity\n"
    "  depends_on     — entity A depends on entity B\n"
    "  contradicts    — two entities are in tension or conflict\n"
    "  related_to     — catch-all for other meaningful links\n\n"
    "## Output format — STRICT JSON, no markdown fences:\n"
    "{\n"
    '  "edges": [\n'
    '    {"source": "<id>", "target": "<id>", '
    '"relationship": "<type>", "confidence": 0.0-1.0, '
    '"explanation": "short reason"}\n'
    "  ],\n"
    '  "hyperedges": [\n'
    '    {"label": "short label", "relationship": "<type>", '
    '"member_ids": ["<id>", "<id>", ...], '
    '"confidence": 0.0-1.0, "explanation": "short reason"}\n'
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "• Only create edges where a real business relationship exists.\n"
    "• A hyperedge groups 3+ entities sharing ONE contextual concept "
    "(e.g. 'All Q3 revenue goals measured by these KPIs').\n"
    "• confidence reflects how certain you are (0.5 = plausible, 0.9 = very clear).\n"
    "• Do NOT invent entities. Use only the provided ids.\n"
    "• Return ONLY the JSON object. No preamble."
)

RELATIONSHIP_EXTRACTION_HUMAN = (
    "## Entities\n{entities_block}\n\n"
    "Extract all relationships and hyperedges. Return JSON only."
)
