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

    log_level: str = "INFO"


settings = Settings()
