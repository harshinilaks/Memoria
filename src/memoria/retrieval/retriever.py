import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from memoria.database.models import Memory, MemoryStatus, MemoryType
from memoria.lifecycle.policy import LifecyclePolicy
from memoria.lifecycle.scoring import ScoreBreakdown, score
from memoria.memory.repository import MemoryRepository
from memoria.retrieval.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchFilters:
    repository_id: str | None = None
    session_id: str | None = None
    memory_type: MemoryType | None = None
    status: MemoryStatus = MemoryStatus.ACTIVE


# Nearest neighbours fetched before re-ranking, so a recent or important memory can
# outrank a slightly more similar one.
CANDIDATE_MULTIPLIER = 4
MIN_CANDIDATES = 40
MAX_CANDIDATES = 200


class MemoryRetriever:
    """Semantic search over memories in one namespace.

    Fetches nearest neighbours by cosine similarity, then re-ranks them by a weighted blend
    of similarity, recency (exponential decay since last change) and importance.
    """

    def __init__(self, db: Session, embedder: EmbeddingProvider, policy: LifecyclePolicy = LifecyclePolicy()):
        self.db = db
        self.repository = MemoryRepository(db)
        self.embedder = embedder
        self.policy = policy

    def search(
        self,
        namespace: str,
        query: str,
        top_k: int = 10,
        min_similarity: float | None = None,
        filters: SearchFilters = SearchFilters(),
    ) -> list[tuple[Memory, ScoreBreakdown]]:
        candidates = self.repository.similar(
            namespace,
            self.embedder.embed_query(query),
            self.embedder.model_name,
            status=filters.status,
            repository_id=filters.repository_id,
            session_id=filters.session_id,
            memory_type=filters.memory_type,
            min_similarity=min_similarity,
            limit=min(MAX_CANDIDATES, max(MIN_CANDIDATES, top_k * CANDIDATE_MULTIPLIER)),
        )
        now = datetime.now(timezone.utc)
        ranked = sorted(
            ((memory, score(memory, similarity, now, self.policy)) for memory, similarity in candidates),
            key=lambda item: (-item[1].score, item[0].id),
        )[:top_k]

        self.repository.touch_many([memory.id for memory, _ in ranked])
        self.db.commit()
        for memory, _ in ranked:
            self.db.refresh(memory)

        logger.info(
            "memories searched",
            extra={"namespace": namespace, "top_k": top_k, "candidates": len(candidates), "results": len(ranked)},
        )
        return ranked
