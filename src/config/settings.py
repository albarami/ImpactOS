"""ImpactOS application settings loaded from environment variables."""

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment."""

    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class LogLevel(StrEnum):
    """Supported log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables / .env file.

    All secrets and deployment-specific values live here. Never hardcode them.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database ---
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://impactos:changeme@localhost:5432/impactos",
        description="PostgreSQL async connection string.",
    )

    # --- Redis ---
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for job queues and caching.",
    )

    # --- AI / LLM API Keys ---
    ANTHROPIC_API_KEY: str = Field(
        default="",
        description="Anthropic API key for Claude models.",
    )
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API key.",
    )
    OPENROUTER_API_KEY: str = Field(
        default="",
        description="OpenRouter API key for model routing.",
    )

    # --- Object Storage ---
    OBJECT_STORAGE_PATH: str = Field(
        default="./uploads",
        description="Local path for dev, S3 URI for prod.",
    )

    # --- Logging ---
    LOG_LEVEL: LogLevel = Field(
        default=LogLevel.INFO,
        description="Application log level.",
    )

    # --- Environment ---
    ENVIRONMENT: Environment = Field(
        default=Environment.DEV,
        description="Deployment environment (dev/staging/prod).",
    )

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.ENVIRONMENT == Environment.PROD


def get_settings() -> Settings:
    """Factory function for dependency injection via FastAPI Depends."""
    return Settings()
