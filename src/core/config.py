"""Application configuration with environment variable validation."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the project root (3 levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase
    supabase_url: str = Field(..., validation_alias="SUPABASE_URL")
    supabase_key: str = Field(..., validation_alias="SUPABASE_KEY")

    # OpenAI
    openai_api_key: str = Field(..., validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")
    openai_max_tokens: int = Field(default=512, validation_alias="OPENAI_MAX_TOKENS")

    # DSPy model (for query parsing)
    dspy_model: str = Field(default="openai/gpt-4o", validation_alias="DSPY_MODEL")

    # API settings
    api_admin_key: str = Field(default="", validation_alias="API_ADMIN_KEY")
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000"],
        validation_alias="ALLOWED_ORIGINS",
    )

    # Rate limiting
    rate_limit_requests: int = Field(default=30, validation_alias="RATE_LIMIT_REQUESTS")
    rate_limit_period: int = Field(default=60, validation_alias="RATE_LIMIT_PERIOD")

    @property
    def cors_origins(self) -> list[str]:
        """Parse ALLOWED_ORIGINS from comma-separated string or return list."""
        if isinstance(self.allowed_origins, str):
            return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        return self.allowed_origins


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()  # type: ignore[call-arg]


# Validate settings on import in production
def validate_settings() -> None:
    """Validate that all required settings are present."""
    settings = get_settings()
    errors = []

    if not settings.supabase_url:
        errors.append("SUPABASE_URL is required")
    if not settings.supabase_key:
        errors.append("SUPABASE_KEY is required")
    if not settings.openai_api_key:
        errors.append("OPENAI_API_KEY is required")

    if errors:
        raise ValueError(f"Configuration errors: {'; '.join(errors)}")
