"""Embed memories that have no embedding or were embedded by a different model.

    uv run python -m memoria.retrieval.backfill
"""

import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from memoria.core.config import settings
from memoria.core.logging import configure_logging
from memoria.database.models import Memory, MemoryEmbedding
from memoria.database.session import SessionLocal
from memoria.retrieval.embeddings import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger("memoria.retrieval.backfill")


def backfill_embeddings(db: Session, embedder: EmbeddingProvider, batch_size: int = 64) -> int:
    embedded = 0
    while True:
        memories = (
            db.execute(
                select(Memory)
                .outerjoin(MemoryEmbedding)
                .where(
                    or_(
                        MemoryEmbedding.memory_id.is_(None),
                        MemoryEmbedding.model != embedder.model_name,
                    )
                )
                .order_by(Memory.id)
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        if not memories:
            return embedded
        vectors = embedder.embed_documents([memory.content for memory in memories])
        for memory, vector in zip(memories, vectors, strict=True):
            set_embedding(memory, embedder.model_name, vector)
        db.commit()
        embedded += len(memories)
        logger.info("embedded batch", extra={"count": len(memories), "total": embedded})


def set_embedding(memory: Memory, model_name: str, vector: list[float]) -> None:
    if memory.embedding is None:
        memory.embedding = MemoryEmbedding(model=model_name, embedding=vector)
    else:
        memory.embedding.model = model_name
        memory.embedding.embedding = vector


def main() -> None:
    configure_logging(settings.log_level)
    with SessionLocal() as db:
        total = backfill_embeddings(db, get_embedding_provider())
    logger.info("backfill complete", extra={"embedded": total})


if __name__ == "__main__":
    main()
