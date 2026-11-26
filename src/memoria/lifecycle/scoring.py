from dataclasses import dataclass
from datetime import datetime

from memoria.database.models import Memory, MemoryType
from memoria.lifecycle.policy import LifecyclePolicy

# Used when a memory has no explicit importance_score. Unverified hypotheses rank lower.
DEFAULT_IMPORTANCE = {
    MemoryType.FACT: 0.6,
    MemoryType.DECISION: 0.6,
    MemoryType.OBSERVATION: 0.5,
    MemoryType.HYPOTHESIS: 0.3,
}


@dataclass(frozen=True)
class ScoreBreakdown:
    score: float
    similarity: float
    recency: float
    importance: float


def effective_importance(memory: Memory, policy: LifecyclePolicy) -> float:
    base = (
        memory.importance_score
        if memory.importance_score is not None
        else DEFAULT_IMPORTANCE[memory.memory_type]
    )
    return min(1.0, base + policy.reinforcement_boost * (memory.reinforcement_count or 0))


def recency(updated_at: datetime, now: datetime, half_life_days: float) -> float:
    """1.0 for a memory changed or re-confirmed just now, halving every `half_life_days`."""
    age_days = max(0.0, (now - updated_at).total_seconds() / 86400)
    return 0.5 ** (age_days / half_life_days)


def score(memory: Memory, similarity: float, now: datetime, policy: LifecyclePolicy) -> ScoreBreakdown:
    rec = recency(memory.updated_at, now, policy.recency_half_life_days)
    imp = effective_importance(memory, policy)
    total_weight = policy.similarity_weight + policy.recency_weight + policy.importance_weight
    blended = (
        policy.similarity_weight * similarity
        + policy.recency_weight * rec
        + policy.importance_weight * imp
    ) / total_weight
    return ScoreBreakdown(score=blended, similarity=similarity, recency=rec, importance=imp)
