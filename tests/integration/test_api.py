from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

MISSING_ID = "00000000-0000-0000-0000-000000000000"


def make_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": "agent-1",
        "session_id": "session-1",
        "repository_id": "memoria",
        "content": "The auth service uses JWT tokens for session validation.",
        "memory_type": "fact",
        "source": "repo-analysis",
        "metadata": {"file": "auth.py"},
    }
    payload.update(overrides)
    return payload


def create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/api/v1/memories", json=make_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


class TestCreateAndGet:
    def test_create_returns_persisted_memory(self, client: TestClient) -> None:
        data = create(client)
        assert UUID(data["id"])
        assert data["namespace"] == "development"
        assert data["status"] == "active"
        assert data["metadata"] == {"file": "auth.py"}
        assert data["last_accessed_at"] is None

        fetched = client.get(f"/api/v1/memories/{data['id']}").json()
        assert fetched["content"] == data["content"]
        assert fetched["memory_type"] == "fact"

    def test_get_records_access_without_changing_updated_at(self, client: TestClient) -> None:
        data = create(client)
        fetched = client.get(f"/api/v1/memories/{data['id']}").json()
        assert fetched["last_accessed_at"] is not None
        assert fetched["updated_at"] == data["updated_at"]

    def test_namespace_comes_from_identity_not_client(self, client: TestClient) -> None:
        response = client.post("/api/v1/memories", json=make_payload(namespace="someone-else"))
        assert response.status_code == 422


class TestValidation:
    def test_empty_required_fields(self, client: TestClient) -> None:
        response = client.post("/api/v1/memories", json=make_payload(agent_id="", content=""))
        assert response.status_code == 422
        fields = {error["loc"][-1] for error in response.json()["detail"]}
        assert fields == {"agent_id", "content"}

    def test_unknown_memory_type(self, client: TestClient) -> None:
        response = client.post("/api/v1/memories", json=make_payload(memory_type="rumor"))
        assert response.status_code == 422

    def test_importance_out_of_range(self, client: TestClient) -> None:
        response = client.post("/api/v1/memories", json=make_payload(importance_score=1.5))
        assert response.status_code == 422

    def test_invalid_uuid(self, client: TestClient) -> None:
        assert client.get("/api/v1/memories/not-a-uuid").status_code == 422

    def test_update_rejects_null_content(self, client: TestClient) -> None:
        memory_id = create(client)["id"]
        response = client.patch(f"/api/v1/memories/{memory_id}", json={"content": None})
        assert response.status_code == 422

    def test_update_rejects_immutable_fields(self, client: TestClient) -> None:
        memory_id = create(client)["id"]
        response = client.patch(f"/api/v1/memories/{memory_id}", json={"agent_id": "other"})
        assert response.status_code == 422


class TestMissingRecords:
    def test_get_missing(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/memories/{MISSING_ID}")
        assert response.status_code == 404
        assert MISSING_ID in response.json()["detail"]

    def test_update_missing(self, client: TestClient) -> None:
        response = client.patch(f"/api/v1/memories/{MISSING_ID}", json={"content": "x"})
        assert response.status_code == 404

    def test_delete_missing(self, client: TestClient) -> None:
        assert client.delete(f"/api/v1/memories/{MISSING_ID}").status_code == 404


class TestList:
    def test_filters(self, client: TestClient) -> None:
        create(client, session_id="s1", memory_type="fact")
        create(client, session_id="s1", memory_type="hypothesis")
        create(client, session_id="s2", repository_id="other-repo", memory_type="fact")

        def total(**params: str) -> int:
            response = client.get("/api/v1/memories", params=params)
            assert response.status_code == 200, response.text
            return response.json()["total"]

        assert total() == 3
        assert total(session_id="s1") == 2
        assert total(memory_type="hypothesis") == 1
        assert total(repository_id="other-repo") == 1
        assert total(session_id="s1", memory_type="fact") == 1

    def test_pagination_is_newest_first(self, client: TestClient) -> None:
        ids = [create(client, content=f"memory {i}")["id"] for i in range(5)]

        first = client.get("/api/v1/memories", params={"page": 1, "page_size": 2}).json()
        last = client.get("/api/v1/memories", params={"page": 3, "page_size": 2}).json()

        assert first["total"] == 5
        assert [m["id"] for m in first["memories"]] == [ids[4], ids[3]]
        assert [m["id"] for m in last["memories"]] == [ids[0]]

    def test_invalid_page_size(self, client: TestClient) -> None:
        assert client.get("/api/v1/memories", params={"page_size": 101}).status_code == 422


class TestUpdate:
    def test_updates_permitted_fields_and_timestamp(self, client: TestClient) -> None:
        data = create(client)
        response = client.patch(
            f"/api/v1/memories/{data['id']}",
            json={"content": "Updated fact.", "importance_score": 0.8, "metadata": {"v": 2}},
        )
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated["content"] == "Updated fact."
        assert updated["importance_score"] == 0.8
        assert updated["metadata"] == {"v": 2}
        assert updated["updated_at"] > data["updated_at"]
        assert updated["created_at"] == data["created_at"]

    def test_partial_update_keeps_other_fields(self, client: TestClient) -> None:
        data = create(client, importance_score=0.3)
        updated = client.patch(
            f"/api/v1/memories/{data['id']}", json={"importance_score": 0.9}
        ).json()
        assert updated["content"] == data["content"]
        assert updated["metadata"] == data["metadata"]


class TestArchive:
    def test_delete_archives_and_hides_memory(self, client: TestClient) -> None:
        memory_id = create(client)["id"]

        response = client.delete(f"/api/v1/memories/{memory_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "archived"

        assert client.get(f"/api/v1/memories/{memory_id}").status_code == 404
        assert client.patch(f"/api/v1/memories/{memory_id}", json={"content": "x"}).status_code == 404
        assert client.delete(f"/api/v1/memories/{memory_id}").status_code == 404
        assert client.get("/api/v1/memories").json()["total"] == 0

        archived = client.get("/api/v1/memories", params={"status": "archived"}).json()
        assert [m["id"] for m in archived["memories"]] == [memory_id]


class TestNamespaceIsolation:
    def test_other_namespace_cannot_access(
        self, client: TestClient, act_as: Callable[[str], None]
    ) -> None:
        act_as("team-a")
        memory_id = create(client, content="Belongs to team A.")["id"]

        act_as("team-b")
        assert client.get(f"/api/v1/memories/{memory_id}").status_code == 404
        assert client.patch(f"/api/v1/memories/{memory_id}", json={"content": "x"}).status_code == 404
        assert client.delete(f"/api/v1/memories/{memory_id}").status_code == 404
        assert client.get("/api/v1/memories").json()["total"] == 0

        act_as("team-a")
        memory = client.get(f"/api/v1/memories/{memory_id}").json()
        assert memory["content"] == "Belongs to team A."
        assert memory["status"] == "active"

    def test_namespace_query_param_is_ignored(
        self, client: TestClient, act_as: Callable[[str], None]
    ) -> None:
        act_as("team-a")
        memory_id = create(client)["id"]
        act_as("team-b")
        response = client.get(f"/api/v1/memories/{memory_id}", params={"namespace": "team-a"})
        assert response.status_code == 404


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0", "database": "ok"}


def test_ids_are_unique(client: TestClient) -> None:
    ids = {create(client, session_id=str(uuid4()))["id"] for _ in range(3)}
    assert len(ids) == 3
