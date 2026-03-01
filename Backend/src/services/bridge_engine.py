"""
Bridge engine — discovers cross-session similarity (SessionBridge records).

Uses ChromaDB embeddings to compare entities across different sessions.
Produces strength_tier and prepares data for optional AI explanation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from ..models.schemas import GraphEdge


def _strength_tier(score: float) -> str:
    if score >= 0.90:
        return "strong"
    if score >= 0.80:
        return "moderate"
    return "weak"


class BridgeEngine:
    """
    Computes cosine similarity between entities from *different* sessions
    (using embeddings from ChromaDB) and returns bridge edges / records
    that exceed the threshold.
    """

    def __init__(self, similarity_threshold: float = 0.78) -> None:
        self._threshold = similarity_threshold

    def find_bridges(
        self,
        all_entities: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Parameters
        ----------
        all_entities : list of dicts with keys
            id, session_id, embedding, content (from ChromaDB)

        Returns
        -------
        (bridge_records, involved_session_ids)

        Each bridge_record dict:
          entity_a_id, entity_b_id, session_a_id, session_b_id,
          similarity_score, strength_tier
        """
        # Separate by session
        session_map: Dict[str, List[Dict[str, Any]]] = {}
        for ent in all_entities:
            sid = ent.get("metadata", {}).get("session_id") or ent.get("session_id", "")
            if not sid or not ent.get("embedding"):
                continue
            session_map.setdefault(sid, []).append(ent)

        session_ids = list(session_map.keys())
        if len(session_ids) < 2:
            return [], session_ids

        bridges: List[Dict[str, Any]] = []
        involved: set[str] = set()

        for i, sid_a in enumerate(session_ids):
            for sid_b in session_ids[i + 1:]:
                group_a = session_map[sid_a]
                group_b = session_map[sid_b]

                emb_a = np.array([e["embedding"] for e in group_a])
                emb_b = np.array([e["embedding"] for e in group_b])
                sim = cosine_similarity(emb_a, emb_b)

                for ai in range(len(group_a)):
                    for bi in range(len(group_b)):
                        score = float(sim[ai, bi])
                        if score >= self._threshold:
                            bridges.append({
                                "entity_a_id": group_a[ai]["id"],
                                "entity_b_id": group_b[bi]["id"],
                                "session_a_id": sid_a,
                                "session_b_id": sid_b,
                                "similarity_score": round(score, 4),
                                "strength_tier": _strength_tier(score),
                            })
                            involved.update([sid_a, sid_b])

        return bridges, sorted(involved)

    def bridges_to_graph_edges(
        self,
        bridge_records: List[Dict[str, Any]],
    ) -> List[GraphEdge]:
        """Convert bridge records to GraphEdge schemas for the API."""
        return [
            GraphEdge(
                source=b["entity_a_id"],
                target=b["entity_b_id"],
                weight=b["similarity_score"],
                edge_type="bridge",
            )
            for b in bridge_records
        ]
