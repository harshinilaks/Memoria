from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str

    # Phase 1 development identity. Not a security boundary.
    dev_namespace: str = Field(default="development", min_length=1, max_length=255)

    # "hash" is a deterministic, non-semantic embedder for tests and offline development.
    embedding_provider: Literal["fastembed", "hash"] = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: str | None = None

    # Lifecycle thresholds (cosine similarity), tuned for BAAI/bge-small-en-v1.5.
    dedup_similarity_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    conflict_similarity_threshold: float = Field(default=0.80, ge=0.0, le=1.0)

    # Search ranking: weighted blend of similarity, recency and importance.
    ranking_similarity_weight: float = Field(default=0.70, ge=0.0)
    ranking_recency_weight: float = Field(default=0.15, ge=0.0)
    ranking_importance_weight: float = Field(default=0.15, ge=0.0)
    recency_half_life_days: float = Field(default=30.0, gt=0.0)
    reinforcement_importance_boost: float = Field(default=0.05, ge=0.0, le=1.0)

    log_level: str = "INFO"


settings = Settings()
