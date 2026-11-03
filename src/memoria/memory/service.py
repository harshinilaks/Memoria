from uuid import UUID

from sqlalchemy.orm import Session

from memoria.api.schemas import MemoryCreate, MemoryUpdate
from memoria.memory.repository import MemoryRepository


class MemoryService:
    def __init__(self, db: Session):
        self.repository = MemoryRepository(db)

    def create(self, memory_data: MemoryCreate):
        return self.repository.create(memory_data)

    def get_by_id(self, memory_id: UUID, namespace: str):
        return self.repository.get_by_id(memory_id, namespace)

    def list(
        self,
        namespace: str,
        repository_id: str | None = None,
        session_id: str | None = None,
        memory_type: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ):
        return self.repository.list(
            namespace=namespace,
            repository_id=repository_id,
            session_id=session_id,
            memory_type=memory_type,
            status=status,
            offset=offset,
            limit=limit,
        )

    def update(self, memory_id: UUID, namespace: str, update_data: MemoryUpdate):
        return self.repository.update(memory_id, namespace, update_data)

    def delete(self, memory_id: UUID, namespace: str):
        return self.repository.delete(memory_id, namespace)
