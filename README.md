# Memoria

Memoria is a persistent memory infrastructure service for AI agents. It provides a FastAPI service backed by PostgreSQL with namespace-isolated memory CRUD (Phase 1), semantic search over memories using local embeddings and pgvector (Phase 2), and lifecycle management: deduplication, contradiction detection, supersession, recency- and importance-aware ranking, and consolidation (Phase 3).

## Architecture

| Layer | Module | Responsibility |
|---|---|---|
| API | `memoria.api` | Routes, request/response schemas, caller identity (`dependencies.get_namespace`) |
| Service | `memoria.memory.service` | Lifecycle rules (archive policy, access tracking), domain errors, logging |
| Repository | `memoria.memory.repository` | Namespace-scoped SQL queries |
| Lifecycle | `memoria.lifecycle` | Contradiction detection, duplicate classification, ranking scores, consolidation |
| Retrieval | `memoria.retrieval` | `EmbeddingProvider` interface and providers, semantic search (`MemoryRetriever`), backfill |
| Data model | `memoria.database.models` | `Memory` and `MemoryEmbedding` entities, enums, indexes, constraints |
| Core | `memoria.core` | Settings, domain exceptions, JSON logging |

`integrations/` is a placeholder for later phases.

### Design decisions

- **Synchronous SQLAlchemy.** Each request does a handful of indexed queries, so async adds complexity without a measurable benefit at this stage.
- **Namespace comes from the caller identity, not the request.** Every request acts as the configured development identity (`DEV_NAMESPACE`). Clients cannot pass a namespace; sending one in the body is rejected. **This is not a security boundary.** Real authentication and authorization must replace `get_namespace` before exposing the service to untrusted clients.
- **DELETE archives (soft delete).** Archived memories are kept for provenance but hidden: get, update and delete return 404, and list only returns them with `status=archived`.
- **`last_accessed_at`** is set when a memory is fetched by ID, without changing `updated_at`.
- **Hypotheses vs facts.** `memory_type` distinguishes verified `fact`s from agent-generated `hypothesis`es so consumers can avoid treating unverified information as authoritative.
- **Migrations only.** The app never creates tables; schema changes go through Alembic.

### Semantic retrieval

- **Embedding provider.** The default is [fastembed](https://github.com/qdrant/fastembed) with `BAAI/bge-small-en-v1.5` (384 dimensions, ONNX on CPU, no PyTorch). The model is downloaded on first use (about 130 MB); set `EMBEDDING_CACHE_DIR` to keep it somewhere persistent. Providers implement `EmbeddingProvider` (`embed_documents`, `embed_query`), so others can be added without touching the database or API. `EMBEDDING_PROVIDER=hash` selects a deterministic word-hashing embedder used by the tests; it matches shared words, not meaning.
- **Storage.** Embeddings live in `memory_embeddings` (one row per memory, `vector(384)`, HNSW cosine index), separate from `memories`. Each row records the model that produced it; search only compares vectors from the configured model. A model with a different dimension needs a migration (startup fails with an explicit error otherwise).
- **When embedding happens.** Synchronously on create and when content changes, in the same transaction as the write, so a stored memory is always searchable. If embedding fails, the write fails.
- **Search.** `POST /api/v1/memories/search` finds memories in the caller's namespace by cosine similarity and re-ranks them (see [Ranking](#ranking)). It returns only `active` memories unless `status` is given, supports `repository_id`, `session_id`, `memory_type`, `top_k` (1–50, default 10) and `min_similarity`, and sets `last_accessed_at` on returned memories. pgvector iterative index scans are enabled so selective filters still return matches.
- **Backfill.** After switching models, or for memories written before Phase 2, run `uv run python -m memoria.retrieval.backfill` to embed every memory that is missing an embedding or has one from a different model.

### Memory lifecycle

Similarity thresholds below are cosine similarities tuned for `bge-small-en-v1.5`; other models need different values (see `.env.example`).

- **Deduplication.** On create, the 10 most similar active memories in the same namespace and repository (similarity ≥ 0.80) are checked. If one has the same `memory_type`, similarity ≥ 0.92 and no contradiction signal, the write is merged into it: the response is `200` with `deduplicated: true` and the existing memory, its `reinforcement_count` goes up by one, its `importance_score` becomes the higher of the two, and `updated_at` is refreshed. Pass `"deduplicate": false` to always store a new memory.
- **Contradiction detection.** Embeddings can't tell a paraphrase from a contradiction ("port 8000" vs "port 9000" scores 0.89; "Python 3.12" vs "3.11" scores 0.97), so similar memories are checked for lexical signals: a negation on one side only, different numbers, an antonym pair (enabled/disabled, sync/async, …), or, below the duplicate threshold, a swap of one or two terms ("PostgreSQL" vs "MySQL"). Matches are returned in the create response as `conflicts` with `similarity` and `reasons`. Nothing changes automatically; the agent decides which memory is right. The detector sits behind a `ContradictionDetector` interface so an LLM or NLI model can replace it.
- **Supersession.** `POST /api/v1/memories/{id}/supersede` replaces an active memory with corrected content (type and importance are inherited unless given). The old memory becomes `superseded`, points to the new one with `superseded_by_id`, drops out of default search and list, and becomes read-only (`PATCH` returns 409). `GET /api/v1/memories/{id}/history` returns the newer versions (oldest first) and everything it replaced (newest first).
- **Consolidation.** `POST /api/v1/memories/consolidate` finds near-duplicate active memories (same namespace, repository and type; similarity ≥ the threshold, 0.92 by default; no contradiction signal). The memory with the highest importance, then reinforcement, then recency becomes canonical; its direct duplicates are superseded by it, and it takes over their reinforcement count and highest explicit importance. It is a dry run unless `"dry_run": false`. It compares every pair in scope, so filter by `repository_id` for large namespaces.

### Ranking

Search fetches the nearest `max(40, 4 × top_k)` memories (up to 200) by similarity and sorts them by

`score = (0.70 × similarity + 0.15 × recency + 0.15 × importance) / (sum of weights)`

- **recency** = `0.5 ^ (days since updated_at / 30)`: 1.0 when just written or reinforced, 0.5 after 30 days.
- **importance** = `importance_score`, or a default by type when unset (fact and decision 0.6, observation 0.5, hypothesis 0.3), plus 0.05 per reinforcement, capped at 1.
- Each result includes `score`, `similarity`, `recency` and `importance`. Weights and the half-life are configurable.

## Local development

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/) and Docker.

```bash
cp .env.example .env              # 1. configuration
docker compose up -d postgres     # 2. PostgreSQL 16 with pgvector
uv sync                           # 3. dependencies (creates .venv)
uv run alembic upgrade head       # 4. schema
uv run uvicorn memoria.main:app --reload --port 8000   # 5. API
```

Interactive API docs are at http://localhost:8000/docs. Logs are emitted as one JSON object per line.

## Example API calls

All requests are scoped to `DEV_NAMESPACE` (default `development`).

```bash
# Create (201; 200 with "deduplicated": true if merged into an existing memory; "conflicts" lists possible contradictions)
curl -X POST http://localhost:8000/api/v1/memories \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-1",
    "session_id": "session-1",
    "repository_id": "memoria",
    "content": "The auth service uses JWT tokens for session validation.",
    "memory_type": "fact",
    "source": "repo-analysis",
    "metadata": {"file": "auth.py"}
  }'

# List (filters: repository_id, session_id, memory_type, status; pagination: page, page_size)
curl "http://localhost:8000/api/v1/memories?repository_id=memoria&memory_type=fact&page=1&page_size=20"

# Get one
curl http://localhost:8000/api/v1/memories/<memory_id>

# Update (content, importance_score, metadata)
curl -X PATCH http://localhost:8000/api/v1/memories/<memory_id> \
  -H "Content-Type: application/json" \
  -d '{"content": "Updated fact: the auth service uses JWT tokens.", "importance_score": 0.8}'

# Archive
curl -X DELETE http://localhost:8000/api/v1/memories/<memory_id>

# List archived memories
curl "http://localhost:8000/api/v1/memories?status=archived"

# Supersede with corrected content (old memory becomes "superseded")
curl -X POST http://localhost:8000/api/v1/memories/<memory_id>/supersede \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "agent-1", "session_id": "session-2", "content": "The auth service uses opaque session tokens."}'

# Version history
curl http://localhost:8000/api/v1/memories/<memory_id>/history

# Consolidate near-duplicates (dry run by default)
curl -X POST http://localhost:8000/api/v1/memories/consolidate \
  -H "Content-Type: application/json" \
  -d '{"repository_id": "memoria", "dry_run": true}'

# Semantic search (filters: repository_id, session_id, memory_type, status; top_k; min_similarity)
curl -X POST http://localhost:8000/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d '{"query": "how do users log in?", "repository_id": "memoria", "top_k": 5}'

# Health (includes a database check; returns 503 if the database is unreachable)
curl http://localhost:8000/health
```

A two-session coding-agent walkthrough is in `examples/multi_session_walkthrough.py`:

```bash
uv run python examples/multi_session_walkthrough.py
```

## Testing

```bash
uv run pytest
```

- `tests/unit` needs no database.
- `tests/integration` runs against real PostgreSQL using `TEST_DATABASE_URL` (see `.env.example`). The database is created if missing, migrated from scratch, and truncated between tests. These tests are skipped if `TEST_DATABASE_URL` is not set.

```bash
export TEST_DATABASE_URL=postgresql+psycopg://memoria:memoria_password@localhost:5432/memoria_test
uv run pytest
```

- Integration tests use the deterministic `hash` embedder. One test (marker `fastembed`) downloads and runs the real model; it is excluded by default:

```bash
uv run pytest -m fastembed
```
