from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from memoria.api.dependencies import get_namespace
from memoria.api.schemas import MemoryCreate, MemoryListResponse, MemoryResponse, MemoryUpdate
from memoria.database.models import MemoryStatus, MemoryType
from memoria.database.session import get_db
from memoria.memory.service import MemoryService

router = APIRouter(prefix="/memories", tags=["memories"])


def get_memory_service(db: Session = Depends(get_db)) -> MemoryService:
    return MemoryService(db)


@router.post("", response_model=MemoryResponse, status_code=201)
def create_memory(
    data: MemoryCreate,
    namespace: str = Depends(get_namespace),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    return MemoryResponse.model_validate(service.create(namespace, data))


@router.get("/{memory_id}", response_model=MemoryResponse)
def get_memory(
    memory_id: UUID,
    namespace: str = Depends(get_namespace),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    return MemoryResponse.model_validate(service.get(memory_id, namespace))


@router.get("", response_model=MemoryListResponse)
def list_memories(
    repository_id: str | None = None,
    session_id: str | None = None,
    memory_type: MemoryType | None = None,
    status: MemoryStatus | None = Query(
        default=None, description="Archived memories are only returned when status=archived."
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    namespace: str = Depends(get_namespace),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryListResponse:
    memories, total = service.list(
        namespace=namespace,
        repository_id=repository_id,
        session_id=session_id,
        memory_type=memory_type,
        status=status,
        page=page,
        page_size=page_size,
    )
    return MemoryListResponse(
        memories=[MemoryResponse.model_validate(memory) for memory in memories],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: UUID,
    data: MemoryUpdate,
    namespace: str = Depends(get_namespace),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    return MemoryResponse.model_validate(service.update(memory_id, namespace, data))


@router.delete("/{memory_id}", response_model=MemoryResponse)
def delete_memory(
    memory_id: UUID,
    namespace: str = Depends(get_namespace),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    """Archive a memory (soft delete). The archived record is returned."""
    return MemoryResponse.model_validate(service.archive(memory_id, namespace))
