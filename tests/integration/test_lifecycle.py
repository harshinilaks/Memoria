from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from memoria.database.models import Memory

MEMORIES = "/api/v1/memories"


def post(client: TestClient, content: str, expected: int = 201, **overrides: Any) -> dict[str, Any]:
    payload = {
        "agent_id": "agent",
        "session_id": "s1",
        "repository_id": "repo",
        "content": content,
        "memory_type": "fact",
        **overrides,
    }
    response = client.post(MEMORIES, json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Memory))


def supersede(client: TestClient, memory_id: str, content: str, expected: int = 201, **extra: Any) -> dict:
    response = client.post(
        f"{MEMORIES}/{memory_id}/supersede",
        json={"agent_id": "agent", "session_id": "s2", "content": content, **extra},
    )
    assert response.status_code == expected, response.text
    return response.json()


class TestDeduplication:
    def test_exact_repeat_reinforces_existing(self, client: TestClient, db_session: Session) -> None:
        first = post(client, "CI runs the full test suite on GitHub Actions")
        assert first["deduplicated"] is False and first["reinforcement_count"] == 0
        again = post(client, "ci runs the full test suite on github actions!", expected=200, importance_score=0.8)
        assert again["deduplicated"] is True
        assert again["id"] == first["id"]
        assert again["reinforcement_count"] == 1
        assert again["importance_score"] == 0.8
        assert count(db_session) == 1

    def test_near_duplicate_is_merged(self, client: TestClient) -> None:
        first = post(client, "refund requests time out under load")
        assert post(client, "refund requests time out under heavy load", expected=200)["id"] == first["id"]

    def test_importance_never_decreases_on_reinforcement(self, client: TestClient) -> None:
        post(client, "cache uses redis", importance_score=0.9)
        assert post(client, "cache uses redis", expected=200, importance_score=0.2)["importance_score"] == 0.9

    def test_opt_out_stores_separately(self, client: TestClient, db_session: Session) -> None:
        post(client, "cache uses redis")
        post(client, "cache uses redis", deduplicate=False)
        assert count(db_session) == 2

    def test_scoped_by_repository_type_and_status(self, client: TestClient, db_session: Session) -> None:
        first = post(client, "cache uses redis")
        post(client, "cache uses redis", repository_id="other")
        post(client, "cache uses redis", repository_id=None)
        post(client, "cache uses redis", memory_type="hypothesis")
        client.delete(f"{MEMORIES}/{first['id']}")
        post(client, "cache uses redis")
        assert count(db_session) == 5

    def test_scoped_by_namespace(self, client: TestClient, db_session: Session, act_as) -> None:
        post(client, "cache uses redis")
        act_as("team-b")
        post(client, "cache uses redis")
        assert count(db_session) == 2


class TestConflicts:
    def test_reports_number_conflict_without_changing_anything(self, client: TestClient) -> None:
        old = post(client, "the api service listens on port 8000")
        new = post(client, "the api service listens on port 9000")
        assert new["deduplicated"] is False
        [conflict] = new["conflicts"]
        assert conflict["memory"]["id"] == old["id"]
        assert conflict["reasons"] == ["different_numbers"]
        assert 0.8 <= conflict["similarity"] < 1
        assert client.get(f"{MEMORIES}/{old['id']}").json()["status"] == "active"

    def test_reports_antonym_and_term_swap(self, client: TestClient) -> None:
        post(client, "response caching is enabled in the production cluster")
        new = post(client, "response caching is disabled in the production cluster")
        assert new["conflicts"][0]["reasons"] == ["antonym"]

        post(client, "the main project database engine is postgresql")
        new = post(client, "the main project database engine is mysql")
        assert new["conflicts"][0]["reasons"] == ["different_terms"]

    def test_contradiction_is_never_deduplicated(self, client: TestClient, db_session: Session) -> None:
        post(client, "the api service listens on port 8000")
        post(client, "the api service listens on port 9000")
        assert count(db_session) == 2

    def test_unrelated_memories_have_no_conflicts(self, client: TestClient) -> None:
        post(client, "the api service listens on port 8000")
        assert post(client, "frontend uses react with vite")["conflicts"] == []


class TestSupersession:
    def test_supersede_links_and_hides_old(self, client: TestClient) -> None:
        old = post(client, "the api service listens on port 8000", importance_score=0.7)
        body = supersede(client, old["id"], "the api service listens on port 9000")
        superseded, replacement = body["superseded"], body["replacement"]
        assert superseded["status"] == "superseded"
        assert superseded["superseded_by_id"] == replacement["id"]
        assert replacement["status"] == "active"
        assert replacement["repository_id"] == "repo"
        assert replacement["memory_type"] == "fact"
        assert replacement["importance_score"] == 0.7

        results = client.post(f"{MEMORIES}/search", json={"query": "api port"}).json()["results"]
        assert [r["memory"]["id"] for r in results] == [replacement["id"]]
        listed = client.get(MEMORIES, params={"status": "superseded"}).json()["memories"]
        assert [m["id"] for m in listed] == [old["id"]]

    def test_only_active_memories_can_be_superseded(self, client: TestClient) -> None:
        old = post(client, "deploys run on fridays")
        supersede(client, old["id"], "deploys run on mondays")
        assert supersede(client, old["id"], "deploys run on tuesdays", expected=409)
        archived = post(client, "cache uses redis")
        client.delete(f"{MEMORIES}/{archived['id']}")
        supersede(client, archived["id"], "cache uses memcached", expected=404)

    def test_superseded_memory_is_read_only(self, client: TestClient) -> None:
        old = post(client, "deploys run on fridays")
        supersede(client, old["id"], "deploys run on mondays")
        response = client.patch(f"{MEMORIES}/{old['id']}", json={"content": "x"})
        assert response.status_code == 409
        assert client.get(f"{MEMORIES}/{old['id']}").status_code == 200

    def test_supersede_can_change_type(self, client: TestClient) -> None:
        guess = post(client, "refunds fail because of a timeout", memory_type="hypothesis")
        body = supersede(client, guess["id"], "refunds fail because the ledger call times out", memory_type="fact")
        assert body["replacement"]["memory_type"] == "fact"

    def test_history_walks_both_directions(self, client: TestClient) -> None:
        v1 = post(client, "the api service listens on port 8000")
        v2 = supersede(client, v1["id"], "the api service listens on port 9000")["replacement"]
        v3 = supersede(client, v2["id"], "the api service listens on port 9100")["replacement"]

        middle = client.get(f"{MEMORIES}/{v2['id']}/history").json()
        assert [m["id"] for m in middle["newer"]] == [v3["id"]]
        assert [m["id"] for m in middle["older"]] == [v1["id"]]

        latest = client.get(f"{MEMORIES}/{v3['id']}/history").json()
        assert latest["newer"] == []
        assert [m["id"] for m in latest["older"]] == [v2["id"], v1["id"]]

    def test_supersede_is_namespace_scoped(self, client: TestClient, act_as) -> None:
        old = post(client, "deploys run on fridays")
        act_as("team-b")
        supersede(client, old["id"], "deploys run on mondays", expected=404)
        assert client.get(f"{MEMORIES}/{old['id']}/history").status_code == 404


class TestRanking:
    def search(self, client: TestClient, query: str, **params: Any) -> list[dict[str, Any]]:
        response = client.post(f"{MEMORIES}/search", json={"query": query, **params})
        assert response.status_code == 200, response.text
        return response.json()["results"]

    def test_importance_breaks_similarity_ties(self, client: TestClient) -> None:
        low = post(client, "cache uses redis", importance_score=0.1, deduplicate=False)
        high = post(client, "cache uses redis", importance_score=0.9, deduplicate=False)
        results = self.search(client, "cache uses redis")
        assert [r["memory"]["id"] for r in results] == [high["id"], low["id"]]
        assert results[0]["similarity"] == results[1]["similarity"]
        assert results[0]["importance"] == 0.9

    def test_recent_memories_rank_higher(self, client: TestClient, db_session: Session) -> None:
        old = post(client, "cache uses redis", deduplicate=False)
        new = post(client, "cache uses redis", deduplicate=False)
        db_session.execute(
            update(Memory)
            .where(Memory.id == old["id"])
            .values(updated_at=datetime.now(timezone.utc) - timedelta(days=60))
        )
        db_session.commit()
        results = self.search(client, "cache uses redis")
        assert [r["memory"]["id"] for r in results] == [new["id"], old["id"]]
        assert results[1]["recency"] < 0.3 < 0.99 < results[0]["recency"]

    def test_hypotheses_rank_below_facts_by_default(self, client: TestClient) -> None:
        guess = post(client, "cache uses redis", memory_type="hypothesis")
        fact = post(client, "cache uses redis")
        results = self.search(client, "cache uses redis")
        assert [r["memory"]["id"] for r in results] == [fact["id"], guess["id"]]

    def test_reinforcement_boosts_importance(self, client: TestClient) -> None:
        post(client, "cache uses redis")
        post(client, "cache uses redis", expected=200)
        [result] = self.search(client, "cache uses redis")
        assert result["importance"] == 0.65

    def test_min_score_was_renamed(self, client: TestClient) -> None:
        response = client.post(f"{MEMORIES}/search", json={"query": "x", "min_score": 0.5})
        assert response.status_code == 422


class TestConsolidation:
    def consolidate(self, client: TestClient, **body: Any) -> dict[str, Any]:
        response = client.post(f"{MEMORIES}/consolidate", json=body)
        assert response.status_code == 200, response.text
        return response.json()

    def seed(self, client: TestClient) -> tuple[dict, dict, dict]:
        a = post(client, "refund requests time out under load", deduplicate=False, importance_score=0.4)
        b = post(client, "refund requests time out under heavy load", deduplicate=False, importance_score=0.8)
        c = post(client, "Refund requests time out under load.", deduplicate=False)
        return a, b, c

    def test_dry_run_reports_without_changes(self, client: TestClient, db_session: Session) -> None:
        a, b, c = self.seed(client)
        body = self.consolidate(client)
        assert body["dry_run"] is True
        [cluster] = body["clusters"]
        assert cluster["canonical"]["id"] == b["id"]
        assert {m["id"] for m in cluster["merged"]} == {a["id"], c["id"]}
        assert client.get(f"{MEMORIES}/{a['id']}").json()["status"] == "active"

    def test_apply_supersedes_duplicates(self, client: TestClient) -> None:
        a, b, c = self.seed(client)
        post(client, "frontend uses react with vite", deduplicate=False)
        [cluster] = self.consolidate(client, dry_run=False)["clusters"]
        canonical = cluster["canonical"]
        assert canonical["id"] == b["id"]
        assert canonical["reinforcement_count"] == 2
        assert canonical["importance_score"] == 0.8
        for merged in cluster["merged"]:
            assert merged["status"] == "superseded"
            assert merged["superseded_by_id"] == b["id"]
        history = client.get(f"{MEMORIES}/{b['id']}/history").json()
        assert {m["id"] for m in history["older"]} == {a["id"], c["id"]}
        assert self.consolidate(client)["clusters"] == []

    def test_contradictions_and_scopes_are_not_merged(self, client: TestClient) -> None:
        post(client, "the api service listens on port 8000")
        post(client, "the api service listens on port 9000")
        post(client, "cache uses redis")
        post(client, "cache uses redis", repository_id="other")
        post(client, "cache uses redis", memory_type="decision")
        assert self.consolidate(client, similarity_threshold=0.8)["clusters"] == []

    def test_filters_limit_scope(self, client: TestClient) -> None:
        self.seed(client)
        assert self.consolidate(client, repository_id="other")["clusters"] == []
        assert len(self.consolidate(client, repository_id="repo")["clusters"]) == 1

    def test_namespace_scoped(self, client: TestClient, act_as) -> None:
        self.seed(client)
        act_as("team-b")
        assert self.consolidate(client)["clusters"] == []
