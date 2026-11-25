from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from memoria.database.models import MemoryStatus, MemoryType


class MemoryCreate(BaseModel):
    """Request body for creating a memory. The namespace comes from the caller identity."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, max_length=10000)
    memory_type: MemoryType
    agent_id: str = Field(..., min_length=1, max_length=255)
    session_id: str = Field(..., min_length=1, max_length=255)
    repository_id: Optional[str] = Field(None, min_length=1, max_length=255)
    source: Optional[str] = Field(None, max_length=500)
    importance_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdate(BaseModel):
    """Fields a client may change. Omitted fields are left untouched."""

    model_config = ConfigDict(extra="forbid")

    content: Optional[str] = Field(None, min_length=1, max_length=10000)
    importance_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    metadata: Optional[dict[str, Any]] = None

    @field_validator("content", "metadata")
    @classmethod
    def reject_explicit_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("may be omitted but not set to null")
        return value


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: str
    namespace: str
    repository_id: Optional[str]
    session_id: str
    content: str
    memory_type: MemoryType
    source: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_accessed_at: Optional[datetime]
    importance_score: Optional[float]
    status: MemoryStatus
    superseded_by_id: Optional[UUID]
    metadata: dict[str, Any] = Field(validation_alias=AliasChoices("metadata_", "metadata"))


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
