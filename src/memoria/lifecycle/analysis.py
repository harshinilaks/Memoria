from dataclasses import dataclass
from enum import Enum

from memoria.database.models import Memory, MemoryType
from memoria.lifecycle.contradictions import ConflictReason, ContradictionDetector
from memoria.lifecycle.policy import LifecyclePolicy


class Relation(str, Enum):
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    RELATED = "related"


@dataclass(frozen=True)
class Classification:
    relation: Relation
    reasons: tuple[ConflictReason, ...] = ()


def classify(
    content: str,
    memory_type: MemoryType,
    existing: Memory,
    similarity: float,
    dedup_threshold: float,
    detector: ContradictionDetector,
) -> Classification:
    """How a new statement relates to a similar existing memory.

    Contradiction signals win over similarity: "Python 3.12 is required" vs "Python 3.11
    is required" scores 0.97 but must not be merged.
    """
    near_duplicate = similarity >= dedup_threshold
    reasons = detector.reasons(content, existing.content, check_terms=not near_duplicate)
    if reasons:
        return Classification(Relation.CONFLICT, tuple(reasons))
    if near_duplicate and memory_type == existing.memory_type:
        return Classification(Relation.DUPLICATE)
    return Classification(Relation.RELATED)


@dataclass
class Conflict:
    memory: Memory
    similarity: float
    reasons: tuple[ConflictReason, ...]


def find_relations(
    content: str,
    memory_type: MemoryType,
    candidates: list[tuple[Memory, float]],
    policy: LifecyclePolicy,
    detector: ContradictionDetector,
) -> tuple[list[tuple[Memory, float]], list[Conflict]]:
    duplicates: list[tuple[Memory, float]] = []
    conflicts: list[Conflict] = []
    for memory, similarity in candidates:
        result = classify(content, memory_type, memory, similarity, policy.dedup_threshold, detector)
        if result.relation is Relation.DUPLICATE:
            duplicates.append((memory, similarity))
        elif result.relation is Relation.CONFLICT:
            conflicts.append(Conflict(memory, similarity, result.reasons))
    return duplicates, conflicts
