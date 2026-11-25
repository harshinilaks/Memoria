import hashlib
import math
import re
import threading
from collections.abc import Sequence
from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

from memoria.core.config import settings
from memoria.database.models import EMBEDDING_DIMENSIONS

if TYPE_CHECKING:
    from fastembed import TextEmbedding


class EmbeddingProvider(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedProvider:
    """Local ONNX embeddings via fastembed. The model is downloaded and loaded on first use."""

    def __init__(self, model_name: str, cache_dir: str | None = None):
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.dimensions = TextEmbedding.get_embedding_size(model_name)
        self._cache_dir = cache_dir
        self._model: "TextEmbedding | None" = None
        self._lock = threading.Lock()

    def _load(self) -> "TextEmbedding":
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(self.model_name, cache_dir=self._cache_dir)
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._load().embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        # query_embed applies the model's query instruction prefix where it has one.
        return next(iter(self._load().query_embed(text))).tolist()


class HashingEmbeddingProvider:
    """Deterministic bag-of-words feature hashing.

    Similarity reflects shared words, not meaning. Used for tests and offline development.
    """

    model_name = "hashing-bow-v1"

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS):
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            digest = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            vector[digest % self.dimensions] += 1.0 if digest >> 63 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            # No tokens: return a fixed unit vector so cosine distance stays defined.
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def build_embedding_provider(
    provider: str, model_name: str, cache_dir: str | None = None
) -> EmbeddingProvider:
    embedder: EmbeddingProvider
    if provider == "fastembed":
        embedder = FastEmbedProvider(model_name, cache_dir)
    elif provider == "hash":
        embedder = HashingEmbeddingProvider()
    else:
        raise ValueError(f"Unknown embedding provider '{provider}'")
    if embedder.dimensions != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Embedding model '{embedder.model_name}' produces {embedder.dimensions}-dimensional "
            f"vectors but the database stores {EMBEDDING_DIMENSIONS}; a migration is required."
        )
    return embedder


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """FastAPI dependency returning the configured provider (one instance per process)."""
    return build_embedding_provider(
        settings.embedding_provider, settings.embedding_model, settings.embedding_cache_dir
    )
