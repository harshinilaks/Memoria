from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from memoria.api.schemas import MemoryCreate, MemoryUpdate
from memoria.database.models import Memory, MemoryStatus


class MemoryRepository:
    """Repository for Memory database operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, memory_data: MemoryCreate) -> Memory:
        """Create a new memory."""
        db_memory = Memory(**memory_data.model_dump())
        self.db.add(db_memory)
        self.db.commit()
        self.db.refresh(db_memory)
        return db_memory

    def get_by_id(self, memory_id: UUID | str, namespace: str) -> Optional[Memory]:
        """Get a memory by ID within a namespace."""
        memory_uuid = str(memory_id)
        return self.db.execute(
            select(Memory).where(
                and_(Memory.id == memory_uuid, Memory.namespace == namespace)
            )
        ).scalar_one_or_none()

    def list(
        self,
        namespace: str,
        repository_id: Optional[str] = None,
        session_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[Memory], int]:
        """List memories with filters."""
        query = select(Memory).where(Memory.namespace == namespace)

        if repository_id:
            query = query.where(Memory.repository_id == repository_id)
        if session_id:
            query = query.where(Memory.session_id == session_id)
        if memory_type:
            query = query.where(Memory.memory_type == memory_type)
        if status:
            query = query.where(Memory.status == status)

        total = self.db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0

        query = query.offset(offset).limit(limit)
        memories = self.db.execute(query).scalars().all()

        return list(memories), total

    def update(
        self, memory_id: UUID | str, namespace: str, update_data: MemoryUpdate
    ) -> Optional[Memory]:
        """Update a memory."""
        memory = self.get_by_id(memory_id, namespace)
        if not memory:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(memory, field, value)

        memory.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def delete(self, memory_id: UUID | str, namespace: str) -> Optional[Memory]:
        """Delete a memory by marking it archived."""
        memory = self.get_by_id(memory_id, namespace)
        if not memory:
            return None

        memory.status = MemoryStatus.ARCHIVED
        memory.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def update_last_accessed(self, memory_id: UUID | str, namespace: str) -> None:
        """Update the last_accessed timestamp for a memory."""
        memory = self.get_by_id(memory_id, namespace)
        if memory:
            memory.last_accessed_at = datetime.now(timezone.utc)
            self.db.commit()
