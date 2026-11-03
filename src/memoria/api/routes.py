from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from memoria.api.schemas import (
    HealthResponse,
    MemoryCreate,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdate,
)
from memoria.core.config import settings
from memoria.database.session import get_db
from memoria.memory.service import MemoryService

router = APIRouter(tags=["memories"])


def get_namespace(namespace: str | None = Query(default=None)) -> str:
    return namespace or settings.dev_namespace


@router.post("/memories", response_model=MemoryResponse)
def create_memory(
    memory_data: MemoryCreate,
    db: Session = Depends(get_db),
) -> MemoryResponse:
    service = MemoryService(db)
    memory = service.create(memory_data)
    return MemoryResponse.model_validate(memory)


@router.get("/memories/{memory_id}", response_model=MemoryResponse)
def get_memory(
    memory_id: UUID,
    namespace: str = Depends(get_namespace),
    db: Session = Depends(get_db),
) -> MemoryResponse:
    service = MemoryService(db)
    memory = service.get_by_id(memory_id, namespace)
    if memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory with id {memory_id} not found in namespace '{namespace}'",
        )
    return MemoryResponse.model_validate(memory)


@router.get("/memories", response_model=MemoryListResponse)
def list_memories(
    namespace: str = Depends(get_namespace),
    repository_id: str | None = None,
    session_id: str | None = None,
    memory_type: Literal["fact", "decision", "observation", "hypothesis"] | None = None,
    status: Literal["active", "superseded", "archived"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MemoryListResponse:
    offset = (page - 1) * page_size
    service = MemoryService(db)
    memories, total = service.list(
        namespace=namespace,
        repository_id=repository_id,
        session_id=session_id,
        memory_type=memory_type,
        status=status,
        offset=offset,
        limit=page_size,
    )
    return MemoryListResponse(
        memories=[MemoryResponse.model_validate(memory) for memory in memories],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/memories/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: UUID,
    update_data: MemoryUpdate,
    namespace: str = Depends(get_namespace),
    db: Session = Depends(get_db),
) -> MemoryResponse:
    service = MemoryService(db)
    memory = service.update(memory_id, namespace, update_data)
    if memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory with id {memory_id} not found in namespace '{namespace}'",
        )
    return MemoryResponse.model_validate(memory)


@router.delete("/memories/{memory_id}", response_model=MemoryResponse)
def delete_memory(
    memory_id: UUID,
    namespace: str = Depends(get_namespace),
    db: Session = Depends(get_db),
) -> MemoryResponse:
    service = MemoryService(db)
    memory = service.delete(memory_id, namespace)
    if memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory with id {memory_id} not found in namespace '{namespace}'",
        )
    return MemoryResponse.model_validate(memory)


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")
