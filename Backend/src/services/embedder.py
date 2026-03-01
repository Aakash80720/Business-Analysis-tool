"""
OpenAI embedding service — wraps the API with batching, cost tracking,
and ChromaDB persistence.

Embeddings are stored in ChromaDB (not in SQL).
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from langchain_openai import OpenAIEmbeddings

from ..config import get_settings
from ..utils.cost_tracker import CostTracker
from .chroma_store import get_chroma_store


# ═══════════════════════════════════════════════════════
#  Embedder
# ═══════════════════════════════════════════════════════

class EmbeddingService:
    """
    Encapsulates OpenAI embedding calls and ChromaDB storage.

    * Batches texts to respect API limits.
    * Delegates cost logging to ``CostTracker``.
    * Persists resulting vectors in ChromaDB.
    """

    BATCH_SIZE = 256

    def __init__(
        self,
        cost_tracker: CostTracker,
        model: str | None = None,
    ) -> None:
        cfg = get_settings()
        self._model = model or cfg.openai_embedding_model
        self._client = OpenAIEmbeddings(
            model=self._model,
            openai_api_key=cfg.openai_api_key,
        )
        self._cost_tracker = cost_tracker

    async def embed_many(self, texts: Sequence[str]) -> Tuple[List[List[float]], int]:
        """
        Embed a batch of texts via OpenAI.

        Returns
        -------
        (embeddings, total_tokens)  — list of float vectors and approximate token count.
        """
        all_embeddings: List[List[float]] = []
        total_tokens = 0

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = list(texts[i : i + self.BATCH_SIZE])
            response = await self._client.aembed_documents(batch)
            all_embeddings.extend(response)
            # Approximate token count (4 chars ≈ 1 token)
            total_tokens += sum(len(t) // 4 for t in batch)

        return all_embeddings, total_tokens

    async def embed_single(self, text: str) -> List[float]:
        embeddings, _ = await self.embed_many([text])
        return embeddings[0]

    async def embed_and_store(
        self,
        entities: Sequence[Dict[str, Any]],
    ) -> Tuple[int, int]:
        """
        Embed entity contents and store vectors in ChromaDB.

        Parameters
        ----------
        entities : list of dicts with keys
            id, content, session_id, document_id, entity_type

        Returns
        -------
        (entities_embedded, total_tokens)
        """
        if not entities:
            return 0, 0

        texts = [e["content"] for e in entities]
        embeddings, total_tokens = await self.embed_many(texts)

        store = get_chroma_store()
        store.add_entities(
            ids=[e["id"] for e in entities],
            embeddings=embeddings,
            documents=texts,
            metadatas=[
                {
                    "session_id": e.get("session_id", ""),
                    "document_id": e.get("document_id", ""),
                    "entity_type": e.get("entity_type", "Custom"),
                }
                for e in entities
            ],
        )

        return len(entities), total_tokens
