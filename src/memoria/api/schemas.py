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
    deduplicate: bool = Field(
        True,
        description="Merge into an existing near-duplicate active memory instead of storing a new one.",
    )


class MemorySupersede(BaseModel):
    """Replacement for an active memory. Omitted type and importance are inherited."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, max_length=10000)
    agent_id: str = Field(..., min_length=1, max_length=255)
    session_id: str = Field(..., min_length=1, max_length=255)
    memory_type: Optional[MemoryType] = None
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
    reinforcement_count: int
    metadata: dict[str, Any] = Field(validation_alias=AliasChoices("metadata_", "metadata"))


class ConflictResponse(BaseModel):
    memory: MemoryResponse
    similarity: float
    reasons: list[str]


class MemoryCreateResponse(MemoryResponse):
    """The stored memory. If `deduplicated`, this is the existing memory it was merged into."""

    deduplicated: bool = False
    conflicts: list[ConflictResponse] = Field(
        default_factory=list,
        description="Similar active memories that may contradict this one. Nothing is changed "
        "automatically; supersede or archive the wrong one.",
    )


class SupersedeResponse(BaseModel):
    superseded: MemoryResponse
    replacement: MemoryResponse


class MemoryHistoryResponse(BaseModel):
    memory: MemoryResponse
    newer: list[MemoryResponse] = Field(description="Replacements, oldest first, ending at the current version.")
    older: list[MemoryResponse] = Field(description="Memories this one replaced, newest first.")


class ConsolidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_id: Optional[str] = None
    session_id: Optional[str] = None
    memory_type: Optional[MemoryType] = None
    similarity_threshold: Optional[float] = Field(
        None, ge=0.5, le=1.0, description="Defaults to the configured deduplication threshold."
    )
    dry_run: bool = True


class ConsolidationCluster(BaseModel):
    canonical: MemoryResponse
    merged: list[MemoryResponse]


class ConsolidateResponse(BaseModel):
    dry_run: bool
    clusters: list[ConsolidationCluster]


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(10, ge=1, le=50)
    min_similarity: Optional[float] = Field(
        None, ge=-1.0, le=1.0, description="Minimum cosine similarity to include a result."
    )
    repository_id: Optional[str] = None
    session_id: Optional[str] = None
    memory_type: Optional[MemoryType] = None
    status: MemoryStatus = MemoryStatus.ACTIVE


class MemorySearchResult(BaseModel):
    memory: MemoryResponse
    score: float = Field(description="Weighted blend of similarity, recency and importance; results are sorted by it.")
    similarity: float
    recency: float
    importance: float


class MemorySearchResponse(BaseModel):
    results: list[MemorySearchResult]
    model: str
