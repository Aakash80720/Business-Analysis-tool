"""
ChromaDB local-persistent vector store.

Manages a single Chroma collection ("entities") with session-based metadata
filtering.  Embeddings are stored here instead of in the SQL database.

Provides:
  • add_entities   — upsert entity vectors + metadata
  • query          — similarity search with optional session filter
  • get_embeddings — retrieve raw embeddings by IDs
  • delete         — remove entities (by ID or by session)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import chromadb
from chromadb.config import Settings as ChromaSettings

from ..config import get_settings

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════

_COLLECTION_NAME = "entities"


# ═══════════════════════════════════════════════════════
#  ChromaStore — singleton vector manager
# ═══════════════════════════════════════════════════════

class ChromaStore:
    """
    Thin wrapper around a persistent ChromaDB collection.

    Each entity is stored with:
      - id:        entity PK (same as SQL Entity.id)
      - embedding: float vector from OpenAI
      - document:  entity content text (enables Chroma full-text)
      - metadata:  {session_id, document_id, entity_type, cluster_id}
    """

    def __init__(self) -> None:
        cfg = get_settings()
        persist_dir = cfg.chroma_persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB ready — persist_dir=%s, collection=%s, count=%d",
            persist_dir, _COLLECTION_NAME, self._collection.count(),
        )

    # ── Write ──

    def add_entities(
        self,
        ids: Sequence[str],
        embeddings: Sequence[List[float]],
        documents: Sequence[str],
        metadatas: Sequence[Dict[str, Any]],
    ) -> int:
        """
        Upsert entity vectors into ChromaDB.

        Parameters
        ----------
        ids        : entity primary keys
        embeddings : matching float vectors
        documents  : entity content text
        metadatas  : dicts with session_id, document_id, entity_type, …

        Returns
        -------
        Number of entities upserted.
        """
        if not ids:
            return 0

        # ChromaDB metadata values must be str | int | float | bool
        clean_meta = []
        for m in metadatas:
            clean = {}
            for k, v in m.items():
                if v is None:
                    clean[k] = ""
                elif isinstance(v, (str, int, float, bool)):
                    clean[k] = v
                else:
                    clean[k] = str(v)
            clean_meta.append(clean)

        self._collection.upsert(
            ids=list(ids),
            embeddings=list(embeddings),
            documents=list(documents),
            metadatas=clean_meta,
        )
        return len(ids)

    # ── Read / Query ──

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 10,
        session_id: Optional[str] = None,
        session_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Similarity search.

        Returns list of dicts:
          {id, content, embedding, distance, metadata}
        sorted by relevance (smallest distance first).
        """
        where: Optional[dict] = None
        if session_ids and len(session_ids) > 1:
            where = {"session_id": {"$in": session_ids}}
        elif session_id:
            where = {"session_id": session_id}
        elif session_ids and len(session_ids) == 1:
            where = {"session_id": session_ids[0]}

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "embeddings", "distances"],
        )

        items: List[Dict[str, Any]] = []
        if not results["ids"] or not results["ids"][0]:
            return items

        for i, eid in enumerate(results["ids"][0]):
            items.append({
                "id": eid,
                "content": (results["documents"][0][i] if results["documents"] else ""),
                "embedding": (results["embeddings"][0][i] if results["embeddings"] else []),
                "distance": (results["distances"][0][i] if results["distances"] else 0.0),
                "metadata": (results["metadatas"][0][i] if results["metadatas"] else {}),
            })
        return items

    def get_by_ids(
        self,
        ids: Sequence[str],
    ) -> List[Dict[str, Any]]:
        """Retrieve entities by their IDs (with embeddings)."""
        if not ids:
            return []
        results = self._collection.get(
            ids=list(ids),
            include=["documents", "metadatas", "embeddings"],
        )
        items: List[Dict[str, Any]] = []
        for i, eid in enumerate(results["ids"]):
            items.append({
                "id": eid,
                "content": results["documents"][i] if results["documents"] else "",
                "embedding": results["embeddings"][i] if results["embeddings"] else [],
                "metadata": results["metadatas"][i] if results["metadatas"] else {},
            })
        return items

    def get_by_session(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Retrieve all entities for a session (with embeddings)."""
        results = self._collection.get(
            where={"session_id": session_id},
            include=["documents", "metadatas", "embeddings"],
        )
        items: List[Dict[str, Any]] = []
        for i, eid in enumerate(results["ids"]):
            items.append({
                "id": eid,
                "content": results["documents"][i] if results["documents"] else "",
                "embedding": results["embeddings"][i] if results["embeddings"] else [],
                "metadata": results["metadatas"][i] if results["metadatas"] else {},
            })
        return items

    def get_all_with_embeddings(
        self,
        session_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve all entities (optionally filtered by session_ids), with embeddings."""
        where: Optional[dict] = None
        if session_ids and len(session_ids) > 1:
            where = {"session_id": {"$in": session_ids}}
        elif session_ids and len(session_ids) == 1:
            where = {"session_id": session_ids[0]}

        kwargs: dict = {"include": ["documents", "metadatas", "embeddings"]}
        if where:
            kwargs["where"] = where
        results = self._collection.get(**kwargs)

        items: List[Dict[str, Any]] = []
        for i, eid in enumerate(results["ids"]):
            items.append({
                "id": eid,
                "content": results["documents"][i] if results["documents"] else "",
                "embedding": results["embeddings"][i] if results["embeddings"] else [],
                "metadata": results["metadatas"][i] if results["metadatas"] else {},
            })
        return items

    # ── Delete ──

    def delete_by_ids(self, ids: Sequence[str]) -> None:
        """Delete specific entities by ID."""
        if ids:
            self._collection.delete(ids=list(ids))

    def delete_by_session(self, session_id: str) -> None:
        """Delete all entities belonging to a session."""
        self._collection.delete(where={"session_id": session_id})

    # ── Stats ──

    @property
    def count(self) -> int:
        return self._collection.count()


# ═══════════════════════════════════════════════════════
#  Module-level singleton
# ═══════════════════════════════════════════════════════

_store: Optional[ChromaStore] = None


def get_chroma_store() -> ChromaStore:
    """Lazy singleton accessor for the ChromaDB store."""
    global _store
    if _store is None:
        _store = ChromaStore()
    return _store
