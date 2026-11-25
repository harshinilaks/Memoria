import math

import pytest

from memoria.database.models import EMBEDDING_DIMENSIONS
from memoria.retrieval.embeddings import (
    FastEmbedProvider,
    HashingEmbeddingProvider,
    build_embedding_provider,
)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def test_hashing_is_deterministic_and_normalized() -> None:
    embedder = HashingEmbeddingProvider()
    first = embedder.embed_query("JWT auth in the api gateway")
    assert first == HashingEmbeddingProvider().embed_documents(["JWT auth in the api gateway"])[0]
    assert len(first) == EMBEDDING_DIMENSIONS
    assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0)


def test_hashing_similarity_follows_shared_words() -> None:
    embedder = HashingEmbeddingProvider()
    query = embedder.embed_query("jwt authentication")
    related = embedder.embed_query("the service uses JWT authentication")
    unrelated = embedder.embed_query("database migrations run with alembic")
    assert cosine(query, related) > cosine(query, unrelated)


def test_hashing_without_tokens_is_still_unit_length() -> None:
    vector = HashingEmbeddingProvider().embed_query("!!! ???")
    assert math.isclose(sum(v * v for v in vector), 1.0)


def test_build_hash_provider() -> None:
    assert isinstance(build_embedding_provider("hash", "ignored"), HashingEmbeddingProvider)


def test_build_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown embedding provider"):
        build_embedding_provider("nope", "x")


def test_build_rejects_dimension_mismatch() -> None:
    # bge-base produces 768-dim vectors; the schema stores 384.
    with pytest.raises(ValueError, match="migration is required"):
        build_embedding_provider("fastembed", "BAAI/bge-base-en-v1.5")


def test_fastembed_provider_is_lazy() -> None:
    provider = FastEmbedProvider("BAAI/bge-small-en-v1.5")
    assert provider.dimensions == EMBEDDING_DIMENSIONS
    assert provider._model is None


@pytest.mark.fastembed
def test_fastembed_ranks_by_meaning() -> None:
    embedder = FastEmbedProvider("BAAI/bge-small-en-v1.5")
    docs = embedder.embed_documents(
        ["Users log in with JSON Web Tokens", "The CI pipeline runs on GitHub Actions"]
    )
    query = embedder.embed_query("how does authentication work?")
    assert len(query) == EMBEDDING_DIMENSIONS
    assert cosine(query, docs[0]) > cosine(query, docs[1])
