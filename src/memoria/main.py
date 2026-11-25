import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from memoria.api.routes import router as memories_router
from memoria.api.schemas import HealthResponse
from memoria.core.config import settings
from memoria.core.exceptions import MemoryNotFoundError
from memoria.core.logging import configure_logging
from memoria.database.session import get_db

VERSION = "0.1.0"

configure_logging(settings.log_level)
logger = logging.getLogger("memoria.api")

app = FastAPI(
    title="Memoria",
    version=VERSION,
    description="Persistent memory infrastructure for AI agents.",
)
app.include_router(memories_router, prefix="/api/v1")


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        },
    )
    return response


@app.exception_handler(MemoryNotFoundError)
async def memory_not_found_handler(request: Request, exc: MemoryNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/health", response_model=HealthResponse)
def health(response: Response, db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("database health check failed")
        response.status_code = 503
        return HealthResponse(status="degraded", version=VERSION, database="unavailable")
    return HealthResponse(status="ok", version=VERSION, database="ok")
