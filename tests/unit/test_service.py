from typing import Any
from uuid import uuid4

import pytest

from memoria.api.schemas import MemoryCreate, MemoryUpdate
from memoria.core.exceptions import MemoryNotFoundError
from memoria.database.models import Memory, MemoryStatus
from memoria.lifecycle.contradictions import HeuristicContradictionDetector
from memoria.lifecycle.policy import LifecyclePolicy
from memoria.memory.service import MemoryService
from memoria.retrieval.embeddings import HashingEmbeddingProvider


class InMemoryRepository:
    """Minimal stand-in for MemoryRepository to test service rules without a database."""

    def __init__(self) -> None:
        self.rows: dict[str, Memory] = {}

    def add(self, memory: Memory) -> Memory:
        memory.id = str(uuid4())
        memory.status = MemoryStatus.ACTIVE
        self.rows[memory.id] = memory
        return memory

    def get_by_id(self, memory_id: str, namespace: str, include_archived: bool = False) -> Memory | None:
        memory = self.rows.get(memory_id)
        if memory and memory.namespace == namespace and (include_archived or memory.status != MemoryStatus.ARCHIVED):
            return memory
        return None

    def update(self, memory: Memory, **fields: Any) -> Memory:
        for key, value in fields.items():
            setattr(memory, key, value)
        return memory

    def archive(self, memory: Memory) -> Memory:
        return self.update(memory, status=MemoryStatus.ARCHIVED)

    def touch(self, memory: Memory) -> Memory:
        return memory

    def similar(self, *args: Any, **kwargs: Any) -> list[tuple[Memory, float]]:
        return []


@pytest.fixture()
def service() -> MemoryService:
    svc = MemoryService.__new__(MemoryService)
    svc.repository = InMemoryRepository()  # type: ignore[assignment]
    svc.embedder = HashingEmbeddingProvider()
    svc.policy = LifecyclePolicy()
    svc.detector = HeuristicContradictionDetector()
    return svc


def new_memory(service: MemoryService, namespace: str = "ns") -> Memory:
    data = MemoryCreate(
        agent_id="a", session_id="s", content="c", memory_type="fact", metadata={"k": 1}
    )
    return service.create(namespace, data).memory


def test_create_assigns_namespace_and_metadata(service: MemoryService) -> None:
    memory = new_memory(service, "team-a")
    assert memory.namespace == "team-a"
    assert memory.metadata_ == {"k": 1}


def test_update_maps_metadata_and_ignores_unset(service: MemoryService) -> None:
    memory = new_memory(service)
    updated = service.update(memory.id, "ns", MemoryUpdate(metadata={"k": 2}))
    assert updated.metadata_ == {"k": 2}
    assert updated.content == "c"


def test_missing_memory_raises(service: MemoryService) -> None:
    with pytest.raises(MemoryNotFoundError, match="not found in namespace 'ns'"):
        service.get(uuid4(), "ns")


def test_other_namespace_raises(service: MemoryService) -> None:
    memory = new_memory(service, "team-a")
    with pytest.raises(MemoryNotFoundError):
        service.get(memory.id, "team-b")


def test_archived_memory_is_hidden(service: MemoryService) -> None:
    memory = new_memory(service)
    assert service.archive(memory.id, "ns").status is MemoryStatus.ARCHIVED
    with pytest.raises(MemoryNotFoundError):
        service.archive(memory.id, "ns")


def test_create_stores_embedding_of_content(service: MemoryService) -> None:
    memory = new_memory(service)
    assert memory.embedding is not None
    assert memory.embedding.model == service.embedder.model_name
    assert memory.embedding.embedding == service.embedder.embed_documents(["c"])[0]


def test_content_update_reembeds(service: MemoryService) -> None:
    memory = new_memory(service)
    embedding = memory.embedding
    service.update(memory.id, "ns", MemoryUpdate(content="new content"))
    assert memory.embedding is embedding
    assert embedding.embedding == service.embedder.embed_documents(["new content"])[0]


def test_metadata_update_keeps_embedding(service: MemoryService) -> None:
    memory = new_memory(service)
    before = list(memory.embedding.embedding)
    service.update(memory.id, "ns", MemoryUpdate(metadata={"x": 2}))
    assert memory.embedding.embedding == before
