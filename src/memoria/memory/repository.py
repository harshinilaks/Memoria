from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from memoria.database.models import Memory, MemoryStatus, MemoryType


class MemoryRepository:
    """Database access for memories. Every query is scoped to a namespace."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, namespace: str, **fields: Any) -> Memory:
        memory = Memory(namespace=namespace, **fields)
        self.db.add(memory)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def get_by_id(
        self, memory_id: str, namespace: str, include_archived: bool = False
    ) -> Optional[Memory]:
        query = select(Memory).where(Memory.id == memory_id, Memory.namespace == namespace)
        if not include_archived:
            query = query.where(Memory.status != MemoryStatus.ARCHIVED)
        return self.db.execute(query).scalar_one_or_none()

    def list(
        self,
        namespace: str,
        repository_id: Optional[str] = None,
        session_id: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        status: Optional[MemoryStatus] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Memory], int]:
        """List memories. Archived memories are excluded unless requested via `status`."""
        query = select(Memory).where(Memory.namespace == namespace)
        if repository_id is not None:
            query = query.where(Memory.repository_id == repository_id)
        if session_id is not None:
            query = query.where(Memory.session_id == session_id)
        if memory_type is not None:
            query = query.where(Memory.memory_type == memory_type)
        if status is not None:
            query = query.where(Memory.status == status)
        else:
            query = query.where(Memory.status != MemoryStatus.ARCHIVED)

        total = self.db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
        memories = self.db.execute(
            query.order_by(Memory.created_at.desc(), Memory.id).offset(offset).limit(limit)
        ).scalars().all()
        return memories, total

    def update(self, memory: Memory, **fields: Any) -> Memory:
        for field, value in fields.items():
            setattr(memory, field, value)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def archive(self, memory: Memory) -> Memory:
        return self.update(memory, status=MemoryStatus.ARCHIVED)

    def touch(self, memory: Memory) -> Memory:
        """Record a retrieval without changing `updated_at`."""
        self.db.execute(
            update(Memory)
            .where(Memory.id == memory.id)
            .values(last_accessed_at=datetime.now(timezone.utc), updated_at=Memory.updated_at)
        )
        self.db.commit()
        self.db.refresh(memory)
        return memory
