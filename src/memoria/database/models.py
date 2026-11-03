from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MemoryType(str, PyEnum):
    FACT = "fact"
    DECISION = "decision"
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"


class MemoryStatus(str, PyEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    repository_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    memory_type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType), nullable=False, index=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    importance_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    status: Mapped[MemoryStatus] = mapped_column(
        Enum(MemoryStatus), nullable=False, default=MemoryStatus.ACTIVE, index=True
    )
    superseded_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("memories.id"), nullable=True
    )
    metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    superseded_by: Mapped[Optional["Memory"]] = relationship(
        "Memory", remote_side=[id], backref="supersedes"
    )

    __table_args__ = (
        CheckConstraint(
            "id != superseded_by_id", name="check_no_self_supersession"
        ),
        Index("idx_namespace_status", "namespace", "status"),
        Index("idx_repository_session", "repository_id", "session_id"),
        Index("idx_agent_session", "agent_id", "session_id"),
    )
