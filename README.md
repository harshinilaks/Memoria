# Memoria

Memoria is a persistent memory infrastructure service for AI agents. This Phase 1 implementation provides a FastAPI service backed by PostgreSQL, with SQLAlchemy models, Alembic migrations, and a repository/service layer for memory CRUD with namespace isolation.

## Architecture

| Layer | Module | Responsibility |
|---|---|---|
| API | `memoria.api` | Routes, request/response schemas, caller identity (`dependencies.get_namespace`) |
| Service | `memoria.memory.service` | Lifecycle rules (archive policy, access tracking), domain errors, logging |
| Repository | `memoria.memory.repository` | Namespace-scoped SQL queries |
| Data model | `memoria.database.models` | `Memory` entity, enums, indexes, constraints |
| Core | `memoria.core` | Settings, domain exceptions, JSON logging |

`retrieval/` and `integrations/` are placeholders for later phases.

### Design decisions

- **Synchronous SQLAlchemy.** Each request does a handful of indexed queries, so async adds complexity without a measurable benefit at this stage.
- **Namespace comes from the caller identity, not the request.** Every request acts as the configured development identity (`DEV_NAMESPACE`). Clients cannot pass a namespace; sending one in the body is rejected. **This is not a security boundary.** Real authentication and authorization must replace `get_namespace` before exposing the service to untrusted clients.
- **DELETE archives (soft delete).** Archived memories are kept for provenance but hidden: get, update and delete return 404, and list only returns them with `status=archived`.
- **`last_accessed_at`** is set when a memory is fetched by ID, without changing `updated_at`.
- **Hypotheses vs facts.** `memory_type` distinguishes verified `fact`s from agent-generated `hypothesis`es so consumers can avoid treating unverified information as authoritative.
- **Migrations only.** The app never creates tables; schema changes go through Alembic.

## Local development

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/) and Docker.

```bash
cp .env.example .env              # 1. configuration
docker compose up -d postgres     # 2. PostgreSQL 16
uv sync                           # 3. dependencies (creates .venv)
uv run alembic upgrade head       # 4. schema
uv run uvicorn memoria.main:app --reload --port 8000   # 5. API
```

Interactive API docs are at http://localhost:8000/docs. Logs are emitted as one JSON object per line.

## Example API calls

All requests are scoped to `DEV_NAMESPACE` (default `development`).

```bash
# Create (returns 201)
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
