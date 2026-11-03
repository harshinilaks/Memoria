# Memoria

Memoria is a persistent memory infrastructure service for AI agents. This Phase 1 implementation provides a FastAPI service backed by PostgreSQL, with SQLAlchemy models, Alembic migrations, and a repository/service layer for CRUD operations.

## Architecture

- API layer: FastAPI endpoints for memory storage and retrieval
- Service layer: business logic for memory lifecycle and validation
- Repository layer: database access for memory CRUD operations
- Data model: core Memory entity with namespace, session, agent, and status tracking
- Persistence: PostgreSQL with SQLAlchemy 2.x and Alembic migrations

## Local development

### 1. Create environment file

Copy the example environment file:

```bash
cp .env.example .env
```

### 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

### 3. Install dependencies

```bash
python -m pip install -e '.[dev]'
```

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Start the API

```bash
uvicorn memoria.main:app --reload --host 0.0.0.0 --port 8000
```

## Example API calls

### Create a memory

```bash
curl -X POST http://localhost:8000/api/v1/memories \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-1",
    "namespace": "development",
    "session_id": "session-1",
    "content": "The auth service uses JWT tokens for session validation.",
    "memory_type": "fact",
    "source": "repo-analysis",
    "metadata": {"repository": "memoria"}
  }'
```

### List memories

```bash
curl "http://localhost:8000/api/v1/memories?namespace=development"
```

### Get one memory

```bash
curl "http://localhost:8000/api/v1/memories/<memory_id>?namespace=development"
```

### Update a memory

```bash
curl -X PATCH "http://localhost:8000/api/v1/memories/<memory_id>?namespace=development" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Updated fact: the auth service uses JWT tokens.",
    "metadata": {"updated": true}
  }'
```

### Delete a memory

```bash
curl -X DELETE "http://localhost:8000/api/v1/memories/<memory_id>?namespace=development"
```

### Health check

```bash
curl http://localhost:8000/health
```

## Notes

- Namespace scoping is intentionally simple in Phase 1 and uses a development namespace by default.
- This is not a security boundary; real authorization is required before exposing the service to untrusted clients.
- The project is intentionally limited to Phase 1 functionality: memory persistence, retrieval, update, deletion, and basic namespace isolation.

## Testing

```bash
pytest
```
