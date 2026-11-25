import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from memoria.database.models import Memory, MemoryEmbedding, MemoryStatus, MemoryType
from memoria.retrieval.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchFilters:
    repository_id: str | None = None
    session_id: str | None = None
    memory_type: MemoryType | None = None
    status: MemoryStatus = MemoryStatus.ACTIVE


class MemoryRetriever:
    """Semantic search over memories in one namespace, ranked by cosine similarity."""

    def __init__(self, db: Session, embedder: EmbeddingProvider):
        self.db = db
        self.embedder = embedder

    def search(
        self,
        namespace: str,
        query: str,
        top_k: int = 10,
        min_score: float | None = None,
        filters: SearchFilters = SearchFilters(),
    ) -> list[tuple[Memory, float]]:
        query_vector = self.embedder.embed_query(query)
        distance = MemoryEmbedding.embedding.cosine_distance(query_vector)

        stmt = (
            select(Memory, (1 - distance).label("score"))
            .join(MemoryEmbedding)
            .where(
                Memory.namespace == namespace,
                Memory.status == filters.status,
                MemoryEmbedding.model == self.embedder.model_name,
            )
        )
        if filters.repository_id is not None:
            stmt = stmt.where(Memory.repository_id == filters.repository_id)
        if filters.session_id is not None:
            stmt = stmt.where(Memory.session_id == filters.session_id)
        if filters.memory_type is not None:
            stmt = stmt.where(Memory.memory_type == filters.memory_type)
        if min_score is not None:
            stmt = stmt.where(distance <= 1 - min_score)
        stmt = stmt.order_by(distance, Memory.id).limit(top_k)

        # Without iterative scans, the HNSW index returns at most ef_search candidates
        # before filters apply, so selective filters could silently drop matches.
        self.db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        rows = self.db.execute(stmt).all()

        if rows:
            self.db.execute(
                update(Memory)
                .where(Memory.id.in_([memory.id for memory, _ in rows]))
                .values(last_accessed_at=datetime.now(timezone.utc), updated_at=Memory.updated_at)
                .execution_options(synchronize_session=False)
            )
        self.db.commit()
        for memory, _ in rows:
            self.db.refresh(memory)

        logger.info(
            "memories searched",
            extra={"namespace": namespace, "top_k": top_k, "results": len(rows)},
        )
        return [(memory, float(score)) for memory, score in rows]
