from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from memoria.database.models import MemoryType
from memoria.lifecycle.analysis import Relation, classify
from memoria.lifecycle.consolidation import plan_clusters
from memoria.lifecycle.contradictions import ConflictReason, HeuristicContradictionDetector
from memoria.lifecycle.policy import LifecyclePolicy
from memoria.lifecycle.scoring import effective_importance, recency, score

NOW = datetime(2026, 11, 26, tzinfo=timezone.utc)
detector = HeuristicContradictionDetector()


def memory(id: str = "m", content: str = "", importance: float | None = None, reinforced: int = 0,
           memory_type: MemoryType = MemoryType.FACT, age_days: float = 0) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        content=content,
        importance_score=importance,
        reinforcement_count=reinforced,
        memory_type=memory_type,
        updated_at=NOW - timedelta(days=age_days),
    )


@pytest.mark.parametrize(
    ("a", "b", "reason"),
    [
        ("The API uses JWT authentication.", "The API does not use JWT authentication.", ConflictReason.NEGATION),
        ("The API uses JWT.", "The API doesn't use JWT.", ConflictReason.NEGATION),
        ("The service listens on port 8000.", "The service listens on port 9000.", ConflictReason.DIFFERENT_NUMBERS),
        ("Python 3.12 is required.", "Python 3.11 is required.", ConflictReason.DIFFERENT_NUMBERS),
        ("Caching is enabled in production.", "Caching is disabled in production.", ConflictReason.ANTONYM),
        ("The project uses PostgreSQL.", "The project uses MySQL.", ConflictReason.DIFFERENT_TERMS),
        ("The API uses JWT authentication.", "The API uses session cookies for authentication.",
         ConflictReason.DIFFERENT_TERMS),
    ],
)
def test_detects_contradictions(a: str, b: str, reason: ConflictReason) -> None:
    assert reason in detector.reasons(a, b)
    assert reason in detector.reasons(b, a)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("The API uses JWT authentication.", "Authentication in the API is done with JWTs."),
        ("Tests run with pytest.", "We run the test suite using pytest."),
        ("The API does not use cookies.", "Cookies are not used by the API."),
        ("Refunds time out because the ledger call is synchronous.",
         "POST /refunds may time out since it calls the ledger synchronously."),
    ],
)
def test_paraphrases_are_not_contradictions(a: str, b: str) -> None:
    assert detector.reasons(a, b) == []


def test_term_swap_check_is_optional() -> None:
    a, b = "The project uses PostgreSQL.", "The project uses MySQL."
    assert detector.reasons(a, b, check_terms=False) == []


def test_classify_prefers_conflict_over_similarity() -> None:
    existing = memory(content="Python 3.11 is required.")
    result = classify("Python 3.12 is required.", MemoryType.FACT, existing, 0.97, 0.92, detector)
    assert result.relation is Relation.CONFLICT


def test_classify_duplicate_requires_same_type_and_threshold() -> None:
    existing = memory(content="Tests run with pytest.")
    text = "Tests are run with pytest."
    assert classify(text, MemoryType.FACT, existing, 0.95, 0.92, detector).relation is Relation.DUPLICATE
    assert classify(text, MemoryType.HYPOTHESIS, existing, 0.95, 0.92, detector).relation is Relation.RELATED
    assert classify(text, MemoryType.FACT, existing, 0.90, 0.92, detector).relation is Relation.RELATED


def test_recency_halves_every_half_life() -> None:
    assert recency(NOW, NOW, 30) == 1.0
    assert recency(NOW - timedelta(days=30), NOW, 30) == pytest.approx(0.5)
    assert recency(NOW - timedelta(days=90), NOW, 30) == pytest.approx(0.125)
    assert recency(NOW + timedelta(days=1), NOW, 30) == 1.0


def test_effective_importance_defaults_by_type_and_reinforcement() -> None:
    policy = LifecyclePolicy(reinforcement_boost=0.1)
    assert effective_importance(memory(memory_type=MemoryType.HYPOTHESIS), policy) == 0.3
    assert effective_importance(memory(importance=0.5, reinforced=2), policy) == pytest.approx(0.7)
    assert effective_importance(memory(importance=0.95, reinforced=3), policy) == 1.0


def test_score_blends_weights() -> None:
    policy = LifecyclePolicy(similarity_weight=2, recency_weight=1, importance_weight=1, recency_half_life_days=10)
    result = score(memory(importance=1.0, age_days=10), 0.5, NOW, policy)
    assert result.score == pytest.approx((2 * 0.5 + 0.5 + 1.0) / 4)
    assert (result.similarity, result.recency, result.importance) == (0.5, pytest.approx(0.5), 1.0)


def test_recent_important_memory_can_outrank_slightly_more_similar_one() -> None:
    policy = LifecyclePolicy()
    stale = score(memory(memory_type=MemoryType.HYPOTHESIS, age_days=365), 0.80, NOW, policy)
    fresh = score(memory(importance=0.9), 0.76, NOW, policy)
    assert fresh.score > stale.score


def test_plan_clusters_picks_highest_priority_canonical() -> None:
    a, b, c = memory("a", importance=0.2), memory("b", importance=0.9), memory("c")
    clusters = plan_clusters([(a, b), (b, c)], LifecyclePolicy())
    assert len(clusters) == 1
    assert clusters[0].canonical.id == "b"
    assert [m.id for m in clusters[0].merged] == ["a", "c"]


def test_plan_clusters_does_not_chain_through_members() -> None:
    a, b, c = memory("a", importance=0.9), memory("b", importance=0.5), memory("c", importance=0.1)
    clusters = plan_clusters([(a, b), (b, c)], LifecyclePolicy())
    assert [(cl.canonical.id, [m.id for m in cl.merged]) for cl in clusters] == [("a", ["b"])]
