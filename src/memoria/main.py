from fastapi import FastAPI

from memoria.api.routes import router as api_router

app = FastAPI(
    title="Memoria",
    version="0.1.0",
    description="Persistent memory infrastructure for AI agents.",
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}
