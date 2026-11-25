from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from memoria.database.models import Memory, MemoryEmbedding
from memoria.retrieval.backfill import backfill_embeddings
from memoria.retrieval.embeddings import HashingEmbeddingProvider

SEARCH = "/api/v1/memories/search"


def create(client: TestClient, content: str, **overrides: Any) -> dict[str, Any]:
    payload = {
        "agent_id": "agent",
        "session_id": "s1",
        "repository_id": "repo",
        "content": content,
        "memory_type": "fact",
        **overrides,
    }
    response = client.post("/api/v1/memories", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def search(client: TestClient, query: str, **params: Any) -> list[dict[str, Any]]:
    response = client.post(SEARCH, json={"query": query, **params})
    assert response.status_code == 200, response.text
    return response.json()["results"]


def test_create_stores_embedding(client: TestClient, db_session: Session) -> None:
    memory = create(client, "auth uses JWT tokens")
    row = db_session.get(MemoryEmbedding, memory["id"])
    assert row is not None
    assert row.model == HashingEmbeddingProvider.model_name
    assert len(row.embedding) == 384


def test_search_ranks_most_similar_first(client: TestClient) -> None:
    jwt = create(client, "The API authenticates requests with JWT bearer tokens")
    create(client, "Database migrations are managed with Alembic")
    create(client, "Frontend uses React with Vite")

    response = client.post(SEARCH, json={"query": "how are requests authenticated with JWT"})
    body = response.json()
    assert body["model"] == HashingEmbeddingProvider.model_name
    results = body["results"]
    assert results[0]["memory"]["id"] == jwt["id"]
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert 0 < scores[0] <= 1


def test_top_k_and_min_score(client: TestClient) -> None:
    for i in range(5):
        create(client, f"deploy step {i} uses docker")
    create(client, "completely unrelated cooking recipe")

    assert len(search(client, "docker deploy", top_k=3)) == 3
    filtered = search(client, "docker deploy", min_score=0.3)
    assert len(filtered) == 5
    assert all(r["score"] >= 0.3 for r in filtered)


def test_filters(client: TestClient) -> None:
    create(client, "cache uses redis", repository_id="a", session_id="x", memory_type="fact")
    create(client, "cache uses redis", repository_id="b", session_id="y", memory_type="hypothesis")

    assert [r["memory"]["repository_id"] for r in search(client, "redis", repository_id="b")] == [
        "b"
    ]
    assert [r["memory"]["session_id"] for r in search(client, "redis", session_id="x")] == ["x"]
    assert [
        r["memory"]["memory_type"] for r in search(client, "redis", memory_type="hypothesis")
    ] == ["hypothesis"]


def test_selective_filter_finds_match_beyond_index_candidates(client: TestClient) -> None:
    # More rows than hnsw.ef_search (40): the only match for the filter must still be found.
    for i in range(60):
        create(client, f"logging configuration note {i}", repository_id="noise")
    target = create(client, "logging configuration note", repository_id="target")
    results = search(client, "logging configuration", repository_id="target")
    assert [r["memory"]["id"] for r in results] == [target["id"]]


def test_archived_excluded_by_default(client: TestClient) -> None:
    kept = create(client, "service listens on port 8000")
    gone = create(client, "service listens on port 9000")
    client.delete(f"/api/v1/memories/{gone['id']}")

    assert [r["memory"]["id"] for r in search(client, "service port")] == [kept["id"]]
    archived = search(client, "service port", status="archived")
    assert [r["memory"]["id"] for r in archived] == [gone["id"]]


def test_namespace_isolation(client: TestClient, act_as: Callable[[str], None]) -> None:
    create(client, "secret project codename falcon")
    act_as("other-team")
    assert search(client, "project codename falcon") == []


def test_content_update_reembeds(client: TestClient) -> None:
    memory = create(client, "tests run with unittest")
    client.patch(f"/api/v1/memories/{memory['id']}", json={"content": "tests run with pytest"})
    assert [r["memory"]["id"] for r in search(client, "pytest")] == [memory["id"]]
    assert search(client, "unittest", min_score=0.5) == []


def test_search_updates_last_accessed(client: TestClient) -> None:
    memory = create(client, "ruff is the linter")
    assert memory["last_accessed_at"] is None
    result = search(client, "linter")[0]["memory"]
    assert result["last_accessed_at"] is not None
    assert result["updated_at"] == memory["updated_at"]


def test_search_validation(client: TestClient) -> None:
    assert client.post(SEARCH, json={"query": ""}).status_code == 422
    assert client.post(SEARCH, json={"query": "x", "top_k": 0}).status_code == 422
    assert client.post(SEARCH, json={"query": "x", "top_k": 51}).status_code == 422
    assert client.post(SEARCH, json={"query": "x", "namespace": "other"}).status_code == 422


def test_backfill_embeds_missing_and_stale(client: TestClient, db_session: Session) -> None:
    first = create(client, "one")
    second = create(client, "two")
    db_session.execute(text("DELETE FROM memory_embeddings WHERE memory_id = :id"), {"id": first["id"]})
    db_session.execute(
        text("UPDATE memory_embeddings SET model = 'old-model' WHERE memory_id = :id"),
        {"id": second["id"]},
    )
    db_session.commit()
    db_session.expire_all()

    assert backfill_embeddings(db_session, HashingEmbeddingProvider(), batch_size=1) == 2
    assert backfill_embeddings(db_session, HashingEmbeddingProvider()) == 0
    models = {
        m.id: m.embedding.model for m in db_session.query(Memory).all() if m.embedding is not None
    }
    assert models == {first["id"]: "hashing-bow-v1", second["id"]: "hashing-bow-v1"}
