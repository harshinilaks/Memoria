import logging
from uuid import UUID

from sqlalchemy.orm import Session

from memoria.api.schemas import MemoryCreate, MemoryUpdate
from memoria.core.exceptions import MemoryNotFoundError
from memoria.database.models import Memory, MemoryStatus, MemoryType
from memoria.memory.repository import MemoryRepository
from memoria.retrieval.backfill import set_embedding
from memoria.retrieval.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)


class MemoryService:
    """Memory lifecycle rules on top of the repository.

    Deletion policy: DELETE archives a memory (soft delete). Archived memories are
    hidden from get/update/delete and from list unless `status=archived` is requested.

    Content is embedded synchronously on create and whenever it changes, in the same
    transaction as the write, so a stored memory is always searchable.
    """

    def __init__(self, db: Session, embedder: EmbeddingProvider):
        self.repository = MemoryRepository(db)
        self.embedder = embedder

    def create(self, namespace: str, data: MemoryCreate) -> Memory:
        fields = data.model_dump(exclude={"metadata"})
        memory = Memory(namespace=namespace, metadata_=data.metadata, **fields)
        set_embedding(memory, self.embedder.model_name, self._embed(data.content))
        memory = self.repository.add(memory)
        logger.info(
            "memory created",
            extra={"memory_id": memory.id, "namespace": namespace, "memory_type": memory.memory_type.value},
        )
        return memory

    def get(self, memory_id: UUID, namespace: str) -> Memory:
        memory = self._get_or_raise(memory_id, namespace)
        return self.repository.touch(memory)

    def list(
        self,
        namespace: str,
        repository_id: str | None = None,
        session_id: str | None = None,
        memory_type: MemoryType | None = None,
        status: MemoryStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Memory], int]:
        memories, total = self.repository.list(
            namespace=namespace,
            repository_id=repository_id,
            session_id=session_id,
            memory_type=memory_type,
            status=status,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return list(memories), total

    def update(self, memory_id: UUID, namespace: str, data: MemoryUpdate) -> Memory:
        memory = self._get_or_raise(memory_id, namespace)
        changes = data.model_dump(exclude_unset=True)
        if "metadata" in changes:
            changes["metadata_"] = changes.pop("metadata")
        if "content" in changes and changes["content"] != memory.content:
            set_embedding(memory, self.embedder.model_name, self._embed(changes["content"]))
        memory = self.repository.update(memory, **changes)
        logger.info(
            "memory updated",
            extra={"memory_id": memory.id, "namespace": namespace, "fields": sorted(changes)},
        )
        return memory

    def archive(self, memory_id: UUID, namespace: str) -> Memory:
        memory = self.repository.archive(self._get_or_raise(memory_id, namespace))
        logger.info("memory archived", extra={"memory_id": memory.id, "namespace": namespace})
        return memory

    def _embed(self, content: str) -> "list[float]":  # `list` is shadowed by the method
        return self.embedder.embed_documents([content])[0]

    def _get_or_raise(self, memory_id: UUID, namespace: str) -> Memory:
        memory = self.repository.get_by_id(str(memory_id), namespace)
        if memory is None:
            raise MemoryNotFoundError(str(memory_id), namespace)
        return memory
