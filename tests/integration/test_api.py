from uuid import UUID


def test_create_and_fetch_memory(client):
    payload = {
        "agent_id": "agent-1",
        "namespace": "development",
        "session_id": "session-1",
        "content": "The auth service uses JWT tokens for session validation.",
        "memory_type": "fact",
        "source": "repo-analysis",
        "metadata": {"repository": "memoria"},
    }

    response = client.post("/api/v1/memories", json=payload)
    assert response.status_code == 200, response.text

    data = response.json()
    assert data["agent_id"] == "agent-1"
    assert data["namespace"] == "development"
    assert data["memory_type"] == "fact"
    assert data["status"] == "active"
    assert UUID(data["id"])

    memory_id = data["id"]
    fetch_response = client.get(f"/api/v1/memories/{memory_id}", params={"namespace": "development"})
    assert fetch_response.status_code == 200, fetch_response.text
    assert fetch_response.json()["content"] == payload["content"]

    list_response = client.get("/api/v1/memories", params={"namespace": "development"})
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["total"] == 1


def test_namespace_isolation(client):
    payload = {
        "agent_id": "agent-2",
        "namespace": "team-a",
        "session_id": "session-2",
        "content": "This memory belongs to team A.",
        "memory_type": "observation",
    }

    create_response = client.post("/api/v1/memories", json=payload)
    assert create_response.status_code == 200, create_response.text
    memory_id = create_response.json()["id"]

    fetch_response = client.get(f"/api/v1/memories/{memory_id}", params={"namespace": "team-b"})
    assert fetch_response.status_code == 404

    list_response = client.get("/api/v1/memories", params={"namespace": "team-b"})
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_update_and_delete_memory(client):
    payload = {
        "agent_id": "agent-3",
        "namespace": "development",
        "session_id": "session-3",
        "content": "Initial fact.",
        "memory_type": "fact",
    }

    create_response = client.post("/api/v1/memories", json=payload)
    memory_id = create_response.json()["id"]

    update_response = client.patch(
        f"/api/v1/memories/{memory_id}",
        params={"namespace": "development"},
        json={"content": "Updated fact.", "metadata": {"updated": True}},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["content"] == "Updated fact."

    delete_response = client.delete(f"/api/v1/memories/{memory_id}", params={"namespace": "development"})
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["status"] == "archived"


def test_validation_errors(client):
    invalid_payload = {
        "agent_id": "",
        "namespace": "development",
        "session_id": "session-4",
        "content": "",
        "memory_type": "fact",
    }

    response = client.post("/api/v1/memories", json=invalid_payload)
    assert response.status_code == 422


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
