import pytest
from pydantic import ValidationError

from memoria.api.schemas import MemoryCreate, MemoryResponse, MemoryUpdate
from memoria.database.models import MemoryType

VALID = {
    "agent_id": "agent-1",
    "session_id": "session-1",
    "content": "A fact.",
    "memory_type": "fact",
}


def test_create_defaults() -> None:
    memory = MemoryCreate(**VALID)
    assert memory.memory_type is MemoryType.FACT
    assert memory.metadata == {}
    assert memory.repository_id is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"content": ""},
        {"agent_id": ""},
        {"session_id": ""},
        {"memory_type": "rumor"},
        {"importance_score": -0.1},
        {"importance_score": 1.1},
        {"content": "x" * 10001},
        {"namespace": "other"},
    ],
)
def test_create_rejects_invalid_input(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MemoryCreate(**{**VALID, **overrides})


def test_create_requires_fields() -> None:
    with pytest.raises(ValidationError) as exc:
        MemoryCreate()  # type: ignore[call-arg]
    missing = {error["loc"][0] for error in exc.value.errors()}
    assert missing == {"agent_id", "session_id", "content", "memory_type"}


def test_update_tracks_only_set_fields() -> None:
    assert MemoryUpdate(importance_score=None).model_dump(exclude_unset=True) == {
        "importance_score": None
    }


@pytest.mark.parametrize("field", ["content", "metadata"])
def test_update_rejects_null_for_non_nullable_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        MemoryUpdate(**{field: None})


def test_response_reads_metadata_attribute() -> None:
    class Row:
        id = "6f1c1d7e-8a4e-4c55-9b7d-2f6f5b1e0c11"
        agent_id = "a"
        namespace = "development"
        repository_id = None
        session_id = "s"
        content = "c"
        memory_type = MemoryType.FACT
        source = None
        created_at = updated_at = "2026-01-01T00:00:00Z"
        last_accessed_at = None
        importance_score = None
        status = "active"
        superseded_by_id = None
        metadata_ = {"k": "v"}

    assert MemoryResponse.model_validate(Row()).model_dump()["metadata"] == {"k": "v"}
