from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Any, Optional
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# Must match the embedding provider's output size; changing it requires a migration.
EMBEDDING_DIMENSIONS = 384


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    repository_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    memory_type: Mapped[MemoryType] = mapped_column(Enum(MemoryType), nullable=False, index=True)
    source: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    importance_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    status: Mapped[MemoryStatus] = mapped_column(
        Enum(MemoryStatus), nullable=False, default=MemoryStatus.ACTIVE, index=True
    )
    superseded_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("memories.id"), nullable=True, index=True
    )
    # Times the same knowledge was stored again and merged into this memory.
    reinforcement_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    # `metadata` is reserved on declarative classes, so the attribute is `metadata_`
    # while the column keeps the name `metadata`.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    superseded_by: Mapped[Optional["Memory"]] = relationship(
        "Memory", remote_side=[id], backref="supersedes"
    )
    embedding: Mapped[Optional["MemoryEmbedding"]] = relationship(
        back_populates="memory", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        CheckConstraint("id != superseded_by_id", name="check_no_self_supersession"),
        Index("idx_namespace_status", "namespace", "status"),
        Index("idx_repository_session", "repository_id", "session_id"),
        Index("idx_agent_session", "agent_id", "session_id"),
    )


class MemoryEmbedding(Base):
    """Embedding of a memory's content. One row per memory; `model` records which
    provider produced it so rows from a previous model can be re-embedded."""

    __tablename__ = "memory_embeddings"

    memory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    memory: Mapped[Memory] = relationship(back_populates="embedding")

    __table_args__ = (
        Index(
            "idx_memory_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
