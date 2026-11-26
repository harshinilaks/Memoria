"""Simulates a coding agent that learns something in one session and recalls it in the next.

Run against a local API (see README):

    uv run python examples/multi_session_walkthrough.py
"""

import os

import httpx

BASE_URL = os.environ.get("MEMORIA_URL", "http://localhost:8000")
REPOSITORY = "acme/payments-service"


def session_one(client: httpx.Client) -> str:
    print("Session 1: investigating the repository")
    fact = client.post(
        "/api/v1/memories",
        json={
            "agent_id": "coding-agent",
            "session_id": "session-1",
            "repository_id": REPOSITORY,
            "content": "Authentication uses JWTs validated in auth/middleware.py.",
            "memory_type": "fact",
            "source": "read_file:auth/middleware.py",
        },
    )
    fact.raise_for_status()
    hypothesis = client.post(
        "/api/v1/memories",
        json={
            "agent_id": "coding-agent",
            "session_id": "session-1",
            "repository_id": REPOSITORY,
            "content": "POST /refunds may time out because it calls the ledger synchronously.",
            "memory_type": "hypothesis",
            "source": "test_run:test_refunds.py",
        },
    )
    hypothesis.raise_for_status()
    print(f"  stored fact {fact.json()['id']}")
    print(f"  stored hypothesis {hypothesis.json()['id']}")
    return hypothesis.json()["id"]


def session_two(client: httpx.Client, hypothesis_id: str) -> None:
    print("Session 2: fresh context, recalling what is known about the repository")
    response = client.get("/api/v1/memories", params={"repository_id": REPOSITORY})
    response.raise_for_status()
    for memory in response.json()["memories"]:
        print(f"  [{memory['memory_type']}] {memory['content']}")

    print("Session 2: asking a question in different words (semantic search)")
    response = client.post(
        "/api/v1/memories/search",
        json={"query": "why might refunds fail?", "repository_id": REPOSITORY, "top_k": 1},
    )
    response.raise_for_status()
    for result in response.json()["results"]:
        memory = result["memory"]
        print(f"  {result['score']:.2f} [{memory['memory_type']}] {memory['content']}")

    print("Session 2: the hypothesis was confirmed, superseding it with a fact")
    response = client.post(
        f"/api/v1/memories/{hypothesis_id}/supersede",
        json={
            "agent_id": "example-agent",
            "session_id": "session-2",
            "content": "Refunds fail because the ledger call times out after 5 seconds.",
            "memory_type": "fact",
            "importance_score": 0.9,
        },
    )
    response.raise_for_status()
    replacement = response.json()["replacement"]
    print(f"  {hypothesis_id} is now superseded by {replacement['id']}")


if __name__ == "__main__":
    with httpx.Client(base_url=BASE_URL, timeout=10) as http:
        session_two(http, session_one(http))
