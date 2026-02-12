"""Application configuration with environment variable validation."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    supabase_url: str = Field(..., validation_alias="SUPABASE_URL")
    supabase_key: str = Field(..., validation_alias="SUPABASE_KEY")

    # NHTSA
    nhtsa_base_url: str = Field(
        default="https://vpic.nhtsa.dot.gov/api",
        validation_alias="NHTSA_BASE_URL",
    )

    # DSPy / LLM
    dspy_lm_model: str = Field(
        default="openai/gpt-4o",
        validation_alias="DSPY_MODEL",
    )
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")

    # CORS
    allowed_origins: list[str] = Field(
        default=["*"],
        validation_alias="ALLOWED_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        if isinstance(self.allowed_origins, str):
            return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        return self.allowed_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
