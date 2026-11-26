import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from memoria.api.schemas import MemoryCreate, MemorySupersede, MemoryUpdate
from memoria.core.exceptions import MemoryNotFoundError, MemoryStateError
from memoria.database.models import Memory, MemoryStatus, MemoryType
from memoria.lifecycle.analysis import Conflict, find_relations
from memoria.lifecycle.contradictions import ContradictionDetector, HeuristicContradictionDetector
from memoria.lifecycle.policy import LifecyclePolicy
from memoria.memory.repository import MemoryRepository
from memoria.retrieval.backfill import set_embedding
from memoria.retrieval.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

# Similar active memories checked for duplicates and conflicts on each write.
LIFECYCLE_CANDIDATES = 10


@dataclass
class CreateResult:
    memory: Memory
    deduplicated: bool = False
    conflicts: "list[Conflict]" = field(default_factory=list)


class MemoryService:
    """Memory lifecycle rules on top of the repository.

    Deletion policy: DELETE archives a memory (soft delete). Archived memories are
    hidden from get/update/delete and from list unless `status=archived` is requested.

    Content is embedded synchronously on create and whenever it changes, in the same
    transaction as the write, so a stored memory is always searchable.

    On create, similar active memories in the same repository are checked: a
    near-duplicate of the same type is reinforced instead of stored again, and possible
    contradictions are reported. Superseded memories are read-only history.
    """

    def __init__(
        self,
        db: Session,
        embedder: EmbeddingProvider,
        policy: LifecyclePolicy = LifecyclePolicy(),
        detector: ContradictionDetector = HeuristicContradictionDetector(),
    ):
        self.repository = MemoryRepository(db)
        self.embedder = embedder
        self.policy = policy
        self.detector = detector

    def create(self, namespace: str, data: MemoryCreate) -> CreateResult:
        vector = self._embed(data.content)
        candidates = self.repository.similar(
            namespace,
            vector,
            self.embedder.model_name,
            repository_id=data.repository_id,
            exact_repository=True,
            min_similarity=self.policy.conflict_threshold,
            limit=LIFECYCLE_CANDIDATES,
        )
        duplicates, conflicts = find_relations(
            data.content, data.memory_type, candidates, self.policy, self.detector
        )

        if data.deduplicate and duplicates:
            existing, similarity = duplicates[0]
            changes: dict = {"reinforcement_count": existing.reinforcement_count + 1}
            if data.importance_score is not None:
                changes["importance_score"] = max(existing.importance_score or 0.0, data.importance_score)
            memory = self.repository.update(existing, **changes)
            logger.info(
                "memory deduplicated",
                extra={"memory_id": memory.id, "namespace": namespace, "similarity": round(similarity, 4)},
            )
            return CreateResult(memory, deduplicated=True, conflicts=conflicts)

        fields = data.model_dump(exclude={"metadata", "deduplicate"})
        memory = Memory(namespace=namespace, metadata_=data.metadata, **fields)
        set_embedding(memory, self.embedder.model_name, vector)
        memory = self.repository.add(memory)
        logger.info(
            "memory created",
            extra={
                "memory_id": memory.id,
                "namespace": namespace,
                "memory_type": memory.memory_type.value,
                "conflicts": len(conflicts),
            },
        )
        return CreateResult(memory, conflicts=conflicts)

    def get(self, memory_id: UUID, namespace: str) -> Memory:
        memory = self._get_or_raise(memory_id, namespace)
        return self.repository.touch(memory)

    def list(
        self,
        namespace: str,
        repository_id: str | None = None,
        session_id: str | None = None,
        memory_type: MemoryType | None = None,
        status: MemoryStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Memory], int]:
        memories, total = self.repository.list(
            namespace=namespace,
            repository_id=repository_id,
            session_id=session_id,
            memory_type=memory_type,
            status=status,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return list(memories), total

    def update(self, memory_id: UUID, namespace: str, data: MemoryUpdate) -> Memory:
        memory = self._get_or_raise(memory_id, namespace)
        if memory.status == MemoryStatus.SUPERSEDED:
            raise MemoryStateError(
                f"Memory {memory.id} is superseded by {memory.superseded_by_id}; update the current version"
            )
        changes = data.model_dump(exclude_unset=True)
        if "metadata" in changes:
            changes["metadata_"] = changes.pop("metadata")
        if "content" in changes and changes["content"] != memory.content:
            set_embedding(memory, self.embedder.model_name, self._embed(changes["content"]))
        memory = self.repository.update(memory, **changes)
        logger.info(
            "memory updated",
            extra={"memory_id": memory.id, "namespace": namespace, "fields": sorted(changes)},
        )
        return memory

    def supersede(self, memory_id: UUID, namespace: str, data: MemorySupersede) -> tuple[Memory, Memory]:
        """Replace an active memory with a new one, keeping the old one as linked history."""
        old = self._get_or_raise(memory_id, namespace)
        if old.status != MemoryStatus.ACTIVE:
            raise MemoryStateError(f"Only active memories can be superseded; {old.id} is {old.status.value}")
        replacement = Memory(
            namespace=namespace,
            repository_id=old.repository_id,
            agent_id=data.agent_id,
            session_id=data.session_id,
            content=data.content,
            memory_type=data.memory_type or old.memory_type,
            source=data.source,
            importance_score=(
                data.importance_score if data.importance_score is not None else old.importance_score
            ),
            metadata_=data.metadata,
        )
        set_embedding(replacement, self.embedder.model_name, self._embed(data.content))
        old, replacement = self.repository.supersede(old, replacement)
        logger.info(
            "memory superseded",
            extra={"memory_id": old.id, "replacement_id": replacement.id, "namespace": namespace},
        )
        return old, replacement

    def history(self, memory_id: UUID, namespace: str) -> tuple[Memory, "list[Memory]", "list[Memory]"]:
        memory = self._get_or_raise(memory_id, namespace, include_archived=True)
        seen = {memory.id}

        newer: list[Memory] = []
        current = memory
        while current.superseded_by_id and current.superseded_by_id not in seen:
            nxt = self.repository.get_by_id(current.superseded_by_id, namespace, include_archived=True)
            if nxt is None:
                break
            newer.append(nxt)
            seen.add(nxt.id)
            current = nxt

        older: list[Memory] = []
        frontier = [memory.id]
        while frontier:
            found = [m for m in self.repository.predecessors(frontier, namespace) if m.id not in seen]
            seen.update(m.id for m in found)
            older.extend(found)
            frontier = [m.id for m in found]
        return memory, newer, older

    def archive(self, memory_id: UUID, namespace: str) -> Memory:
        memory = self.repository.archive(self._get_or_raise(memory_id, namespace))
        logger.info("memory archived", extra={"memory_id": memory.id, "namespace": namespace})
        return memory

    def _embed(self, content: str) -> "list[float]":  # `list` is shadowed by the method
        return self.embedder.embed_documents([content])[0]

    def _get_or_raise(self, memory_id: UUID | str, namespace: str, include_archived: bool = False) -> Memory:
        memory = self.repository.get_by_id(str(memory_id), namespace, include_archived=include_archived)
        if memory is None:
            raise MemoryNotFoundError(str(memory_id), namespace)
        return memory
