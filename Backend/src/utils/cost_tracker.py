"""
Cost tracker — logs every OpenAI API call and enforces monthly budgets.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models.db import CostLog


# ═══════════════════════════════════════════════════════
#  Pricing tables (USD per 1 K tokens as of 2025-Q4)
# ═══════════════════════════════════════════════════════

_EMBEDDING_PRICING: dict[str, float] = {
    "text-embedding-3-small": 0.00002,
    "text-embedding-3-large": 0.00013,
    "text-embedding-ada-002": 0.00010,
}

_CHAT_PRICING: dict[str, float] = {
    "gpt-4o":       0.0025,
    "gpt-4o-mini":  0.00015,
    "gpt-4-turbo":  0.01,
}


# ═══════════════════════════════════════════════════════
#  CostTracker
# ═══════════════════════════════════════════════════════

class CostTracker:
    """
    Tracks token usage and dollar cost per API call.

    Injected with an ``AsyncSession`` so it can persist ``CostLog`` rows.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── public API ──

    async def log_embedding(self, tokens: int, model: str) -> float:
        """Log an embedding call; returns the USD cost."""
        cost = self._estimate_cost(tokens, model, _EMBEDDING_PRICING)
        await self._persist("embedding", tokens, cost, model)
        return cost

    async def log_chat(self, tokens: int, model: str) -> float:
        """Log a chat completion call; returns the USD cost."""
        cost = self._estimate_cost(tokens, model, _CHAT_PRICING)
        await self._persist("chat", tokens, cost, model)
        return cost

    async def get_summary(self) -> dict:
        """Return a summary dict suitable for the CostSummary schema."""
        from ..models.repository import CostLogRepository

        cfg = get_settings()
        repo = CostLogRepository(self._db)

        emb_tokens, emb_cost = await repo.sum_by_category("embedding")
        chat_tokens, chat_cost = await repo.sum_by_category("chat")

        return {
            "total_embedding_tokens": emb_tokens,
            "total_chat_tokens": chat_tokens,
            "total_embedding_cost": round(emb_cost, 6),
            "total_chat_cost": round(chat_cost, 6),
            "embedding_budget_remaining": round(cfg.monthly_embedding_budget - emb_cost, 6),
            "chat_budget_remaining": round(cfg.monthly_chat_budget - chat_cost, 6),
        }

    # ── private ──

    @staticmethod
    def _estimate_cost(
        tokens: int,
        model: str,
        pricing_table: dict[str, float],
    ) -> float:
        rate = pricing_table.get(model, 0.0001)  # fallback
        return round((tokens / 1_000) * rate, 8)

    async def _persist(
        self,
        category: str,
        tokens: int,
        cost: float,
        model: str,
    ) -> None:
        log = CostLog(
            category=category,
            tokens=tokens,
            cost_usd=cost,
            model=model,
        )
        self._db.add(log)
        await self._db.flush()
