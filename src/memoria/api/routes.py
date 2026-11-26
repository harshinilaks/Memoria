from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from memoria.api.dependencies import get_namespace
from memoria.api.schemas import (
    ConflictResponse,
    ConsolidateRequest,
    ConsolidateResponse,
    ConsolidationCluster,
    MemoryCreate,
    MemoryCreateResponse,
    MemoryHistoryResponse,
    MemoryListResponse,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
    MemorySupersede,
    MemoryUpdate,
    SupersedeResponse,
)
from memoria.database.models import MemoryStatus, MemoryType
from memoria.database.session import get_db
from memoria.lifecycle.consolidation import Consolidator
from memoria.lifecycle.contradictions import HeuristicContradictionDetector
from memoria.lifecycle.policy import LifecyclePolicy, get_lifecycle_policy
from memoria.memory.service import MemoryService
from memoria.retrieval.embeddings import EmbeddingProvider, get_embedding_provider
from memoria.retrieval.retriever import MemoryRetriever, SearchFilters

router = APIRouter(prefix="/memories", tags=["memories"])


def get_memory_service(
    db: Session = Depends(get_db),
    embedder: EmbeddingProvider = Depends(get_embedding_provider),
    policy: LifecyclePolicy = Depends(get_lifecycle_policy),
) -> MemoryService:
    return MemoryService(db, embedder, policy, HeuristicContradictionDetector())


def get_memory_retriever(
    db: Session = Depends(get_db),
    embedder: EmbeddingProvider = Depends(get_embedding_provider),
    policy: LifecyclePolicy = Depends(get_lifecycle_policy),
) -> MemoryRetriever:
    return MemoryRetriever(db, embedder, policy)


def get_consolidator(
    db: Session = Depends(get_db),
    embedder: EmbeddingProvider = Depends(get_embedding_provider),
    policy: LifecyclePolicy = Depends(get_lifecycle_policy),
) -> Consolidator:
    return Consolidator(db, embedder.model_name, policy, HeuristicContradictionDetector())


@router.post(
    "",
    response_model=MemoryCreateResponse,
    status_code=201,
    responses={200: {"model": MemoryCreateResponse, "description": "Merged into an existing duplicate"}},
)
def create_memory(
    data: MemoryCreate,
    response: Response,
    namespace: str = Depends(get_namespace),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryCreateResponse:
    """Store a memory. A near-duplicate of an active memory with the same type and
    repository is merged into it instead (200, `deduplicated: true`). Possible
    contradictions with existing memories are listed in `conflicts`."""
    result = service.create(namespace, data)
    if result.deduplicated:
        response.status_code = 200
    return MemoryCreateResponse(
        **MemoryResponse.model_validate(result.memory).model_dump(),
        deduplicated=result.deduplicated,
        conflicts=[
            ConflictResponse(
                memory=MemoryResponse.model_validate(c.memory),
                similarity=c.similarity,
                reasons=[r.value for r in c.reasons],
            )
            for c in result.conflicts
        ],
    )


@router.post("/consolidate", response_model=ConsolidateResponse)
def consolidate_memories(
    request: ConsolidateRequest,
    namespace: str = Depends(get_namespace),
    consolidator: Consolidator = Depends(get_consolidator),
) -> ConsolidateResponse:
    """Merge near-duplicate active memories. Defaults to a dry run that only reports
    the clusters; pass `dry_run: false` to supersede duplicates by their canonical memory."""
    clusters = consolidator.consolidate(
        namespace,
        repository_id=request.repository_id,
        session_id=request.session_id,
        memory_type=request.memory_type,
        threshold=request.similarity_threshold,
        dry_run=request.dry_run,
    )
    return ConsolidateResponse(
        dry_run=request.dry_run,
        clusters=[
            ConsolidationCluster(
                canonical=MemoryResponse.model_validate(c.canonical),
                merged=[MemoryResponse.model_validate(m) for m in c.merged],
            )
            for c in clusters
        ],
    )


@router.post("/search", response_model=MemorySearchResponse)
def search_memories(
    request: MemorySearchRequest,
    namespace: str = Depends(get_namespace),
    retriever: MemoryRetriever = Depends(get_memory_retriever),
) -> MemorySearchResponse:
    """Rank memories by relevance to `query`: semantic similarity blended with recency and
    importance. Only active memories by default."""
    results = retriever.search(
        namespace,
        request.query,
        top_k=request.top_k,
        min_similarity=request.min_similarity,
        filters=SearchFilters(
            repository_id=request.repository_id,
            session_id=request.session_id,
            memory_type=request.memory_type,
            status=request.status,
        ),
    )
    return MemorySearchResponse(
        results=[
            MemorySearchResult(
                memory=MemoryResponse.model_validate(memory),
                score=breakdown.score,
                similarity=breakdown.similarity,
                recency=breakdown.recency,
                importance=breakdown.importance,
            )
            for memory, breakdown in results
        ],
        model=retriever.embedder.model_name,
    )


@router.post("/{memory_id}/supersede", response_model=SupersedeResponse, status_code=201)
def supersede_memory(
    memory_id: UUID,
    data: MemorySupersede,
    namespace: str = Depends(get_namespace),
    service: MemoryService = Depends(get_memory_service),
) -> SupersedeResponse:
    """Replace an active memory with corrected content. The old memory becomes
    `superseded`, links to its replacement, and drops out of default search and list."""
    old, replacement = service.supersede(memory_id, namespace, data)
    return SupersedeResponse(
        superseded=MemoryResponse.model_validate(old),
        replacement=MemoryResponse.model_validate(replacement),
    )


@router.get("/{memory_id}/history", response_model=MemoryHistoryResponse)
def memory_history(
    memory_id: UUID,
    namespace: str = Depends(get_namespace),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryHistoryResponse:
    """The supersession chain around a memory, including archived and superseded versions."""
    memory, newer, older = service.history(memory_id, namespace)
    return MemoryHistoryResponse(
        memory=MemoryResponse.model_validate(memory),
        newer=[MemoryResponse.model_validate(m) for m in newer],
        older=[MemoryResponse.model_validate(m) for m in older],
    )


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
