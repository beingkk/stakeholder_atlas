import json
import logging
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

config_dir = Path(__file__).parent.parent.parent
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Configuration
    PROJECT_NAME: str = "Stakeholder Atlas API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # CORS
    BACKEND_CORS_ORIGINS: str | list[str] = ["http://localhost:3000"]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from string or list input."""
        default_origins = ["http://localhost:3000"]

        if v is None:
            return default_origins

        if isinstance(v, str):
            if not v.strip():
                return default_origins

            if v.strip().startswith("["):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse BACKEND_CORS_ORIGINS as JSON")

            origins = [origin.strip() for origin in v.split(",") if origin.strip()]
            return origins or default_origins

        if isinstance(v, list):
            return v

        return default_origins

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True
    LOG_LEVEL: str = "INFO"

    # OpenAlex Configuration
    OPENALEX_EMAIL: str | None = None
    OPENALEX_API_KEY: str | None = None

    # OpenAI Configuration
    OPENAI_API_KEY: str | None = None
    WEB_SEARCH_MODEL: str = "gpt-5.4"
    VERIFICATION_MODEL: str = "gpt-5.4-mini"

    # Supabase Configuration
    SUPABASE_URL: str | None = None
    SUPABASE_KEY: str | None = None

    # Geography context — defines what "local" and "national" mean
    GEOGRAPHY_CONTEXT: str = "UK"

    # Search Defaults
    DEFAULT_MAX_RESULTS: int = 50
    MAX_SEARCH_RESULTS: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()


settings = get_settings()
