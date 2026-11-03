from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from memoria.database.models import MemoryType, MemoryStatus


class MemoryBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    memory_type: MemoryType
    agent_id: str = Field(..., min_length=1, max_length=255)
    namespace: str = Field(..., min_length=1, max_length=255)
    session_id: str = Field(..., min_length=1, max_length=255)
    repository_id: Optional[str] = Field(None, max_length=255)
    source: Optional[str] = Field(None, max_length=500)
    importance_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)


class MemoryCreate(MemoryBase):
    pass


class MemoryUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1, max_length=10000)
    importance_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    metadata: Optional[dict] = None


class MemoryResponse(BaseModel):
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
    metadata: dict

    class Config:
        from_attributes = True


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    status: str
    version: str
