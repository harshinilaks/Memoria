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

    print("Session 2: the hypothesis was confirmed, recording that in its metadata")
    client.patch(
        f"/api/v1/memories/{hypothesis_id}",
        json={"metadata": {"confirmed_in": "session-2"}, "importance_score": 0.9},
    ).raise_for_status()


if __name__ == "__main__":
    with httpx.Client(base_url=BASE_URL, timeout=10) as http:
        session_two(http, session_one(http))
