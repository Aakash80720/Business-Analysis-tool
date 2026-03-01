"""
Clustering service — Strategy pattern for K-Means vs Hierarchical.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Type

import numpy as np
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.metrics import silhouette_score


# ═══════════════════════════════════════════════════════
#  Result DTO
# ═══════════════════════════════════════════════════════

@dataclass
class ClusterAssignment:
    """One cluster with its member indices and centroid."""
    cluster_label: int
    member_indices: List[int]
    centroid: List[float]


# ═══════════════════════════════════════════════════════
#  Abstract strategy
# ═══════════════════════════════════════════════════════

class BaseClusterer(ABC):
    """Interface for clustering strategies."""

    @abstractmethod
    def fit(
        self,
        embeddings: np.ndarray,
        n_clusters: Optional[int] = None,
    ) -> List[ClusterAssignment]:
        """Assign rows of *embeddings* to clusters."""
        ...

    @staticmethod
    def _optimal_k(embeddings: np.ndarray, k_max: int = 15) -> int:
        """Pick k via silhouette score (auto-detect)."""
        n = len(embeddings)
        k_max = min(k_max, n - 1)
        if k_max < 2:
            return min(n, 2)

        best_k, best_score = 2, -1.0
        for k in range(2, k_max + 1):
            labels = KMeans(n_clusters=k, n_init="auto", random_state=42).fit_predict(embeddings)
            score = silhouette_score(embeddings, labels)
            if score > best_score:
                best_k, best_score = k, score
        return best_k

    @staticmethod
    def _build_assignments(
        embeddings: np.ndarray,
        labels: np.ndarray,
    ) -> List[ClusterAssignment]:
        assignments: List[ClusterAssignment] = []
        for lbl in sorted(set(labels)):
            mask = labels == lbl
            indices = list(np.where(mask)[0])
            centroid = embeddings[mask].mean(axis=0).tolist()
            assignments.append(ClusterAssignment(
                cluster_label=int(lbl),
                member_indices=indices,
                centroid=centroid,
            ))
        return assignments


# ═══════════════════════════════════════════════════════
#  Concrete strategies
# ═══════════════════════════════════════════════════════

class KMeansClusterer(BaseClusterer):
    """Flat partitioning via K-Means."""

    def fit(
        self,
        embeddings: np.ndarray,
        n_clusters: Optional[int] = None,
    ) -> List[ClusterAssignment]:
        k = n_clusters or self._optimal_k(embeddings)
        model = KMeans(n_clusters=k, n_init="auto", random_state=42)
        labels = model.fit_predict(embeddings)
        return self._build_assignments(embeddings, labels)


class HierarchicalClusterer(BaseClusterer):
    """Agglomerative (hierarchical) clustering."""

    def __init__(self, linkage: str = "ward") -> None:
        self._linkage = linkage

    def fit(
        self,
        embeddings: np.ndarray,
        n_clusters: Optional[int] = None,
    ) -> List[ClusterAssignment]:
        k = n_clusters or self._optimal_k(embeddings)
        model = AgglomerativeClustering(n_clusters=k, linkage=self._linkage)
        labels = model.fit_predict(embeddings)
        return self._build_assignments(embeddings, labels)


# ═══════════════════════════════════════════════════════
#  Factory
# ═══════════════════════════════════════════════════════

class ClustererFactory:
    """Resolves a method name to the right clustering strategy."""

    _registry: Dict[str, Type[BaseClusterer]] = {
        "kmeans": KMeansClusterer,
        "hierarchical": HierarchicalClusterer,
    }

    @classmethod
    def register(cls, name: str, clazz: Type[BaseClusterer]) -> None:
        cls._registry[name.lower()] = clazz

    @classmethod
    def create(cls, method: str = "kmeans", **kwargs) -> BaseClusterer:
        clazz = cls._registry.get(method.lower())
        if clazz is None:
            raise ValueError(f"Unknown clustering method: {method}")
        return clazz(**kwargs)
