from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from memoria.database.models import Memory, MemoryEmbedding, MemoryStatus, MemoryType


class MemoryRepository:
    """Database access for memories. Every query is scoped to a namespace."""

    def __init__(self, db: Session):
        self.db = db

    def add(self, memory: Memory) -> Memory:
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

    def similar(
        self,
        namespace: str,
        vector: list[float],
        model: str,
        *,
        status: MemoryStatus = MemoryStatus.ACTIVE,
        repository_id: Optional[str] = None,
        exact_repository: bool = False,
        session_id: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        min_similarity: Optional[float] = None,
        limit: int = 10,
    ) -> list[tuple[Memory, float]]:
        """Nearest memories by cosine similarity, most similar first.

        `exact_repository` matches `repository_id` exactly (including NULL); otherwise
        `repository_id=None` means any repository.
        """
        distance = MemoryEmbedding.embedding.cosine_distance(vector)
        query = (
            select(Memory, (1 - distance).label("similarity"))
            .join(MemoryEmbedding)
            .where(
                Memory.namespace == namespace,
                Memory.status == status,
                MemoryEmbedding.model == model,
            )
        )
        if exact_repository:
            query = query.where(Memory.repository_id.is_not_distinct_from(repository_id))
        elif repository_id is not None:
            query = query.where(Memory.repository_id == repository_id)
        if session_id is not None:
            query = query.where(Memory.session_id == session_id)
        if memory_type is not None:
            query = query.where(Memory.memory_type == memory_type)
        if min_similarity is not None:
            query = query.where(distance <= 1 - min_similarity)
        query = query.order_by(distance, Memory.id).limit(limit)

        # Without iterative scans, the HNSW index returns at most ef_search candidates
        # before filters apply, so selective filters could silently drop matches.
        self.db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        return [(memory, float(sim)) for memory, sim in self.db.execute(query).all()]

    def predecessors(self, memory_ids: Sequence[str], namespace: str) -> Sequence[Memory]:
        return self.db.execute(
            select(Memory)
            .where(Memory.superseded_by_id.in_(memory_ids), Memory.namespace == namespace)
            .order_by(Memory.created_at.desc(), Memory.id)
        ).scalars().all()

    def supersede(self, old: Memory, replacement: Memory) -> tuple[Memory, Memory]:
        self.db.add(replacement)
        self.db.flush()
        old.status = MemoryStatus.SUPERSEDED
        old.superseded_by_id = replacement.id
        self.db.commit()
        self.db.refresh(old)
        self.db.refresh(replacement)
        return old, replacement

    def touch_many(self, memory_ids: Sequence[str]) -> None:
        """Record a retrieval without changing `updated_at`. Caller commits."""
        if memory_ids:
            self.db.execute(
                update(Memory)
                .where(Memory.id.in_(memory_ids))
                .values(last_accessed_at=datetime.now(timezone.utc), updated_at=Memory.updated_at)
                .execution_options(synchronize_session=False)
            )

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
