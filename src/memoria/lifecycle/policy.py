from dataclasses import dataclass
from functools import lru_cache

from memoria.core.config import settings


@dataclass(frozen=True)
class LifecyclePolicy:
    """Thresholds and ranking weights. Similarity thresholds are tuned for
    `BAAI/bge-small-en-v1.5`; other models need different values."""

    dedup_threshold: float = 0.92
    conflict_threshold: float = 0.80
    similarity_weight: float = 0.70
    recency_weight: float = 0.15
    importance_weight: float = 0.15
    recency_half_life_days: float = 30.0
    reinforcement_boost: float = 0.05


@lru_cache
def get_lifecycle_policy() -> LifecyclePolicy:
    return LifecyclePolicy(
        dedup_threshold=settings.dedup_similarity_threshold,
        conflict_threshold=settings.conflict_similarity_threshold,
        similarity_weight=settings.ranking_similarity_weight,
        recency_weight=settings.ranking_recency_weight,
        importance_weight=settings.ranking_importance_weight,
        recency_half_life_days=settings.recency_half_life_days,
        reinforcement_boost=settings.reinforcement_importance_boost,
    )
