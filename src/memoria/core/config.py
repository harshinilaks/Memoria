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

    log_level: str = "INFO"


settings = Settings()
