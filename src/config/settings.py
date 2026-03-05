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

    # --- LLM Provider Configuration ---
    LLM_DEFAULT_MODEL_ANTHROPIC: str = Field(
        default="claude-sonnet-4-20250514",
        description="Default Anthropic model ID.",
    )
    LLM_DEFAULT_MODEL_OPENAI: str = Field(
        default="gpt-4o",
        description="Default OpenAI model ID.",
    )
    LLM_DEFAULT_MODEL_OPENROUTER: str = Field(
        default="anthropic/claude-sonnet-4-20250514",
        description="Default OpenRouter model path.",
    )
    LLM_REQUEST_TIMEOUT_SECONDS: float = Field(
        default=60.0,
        description="Per-request timeout for LLM API calls.",
    )
    LLM_MAX_RETRIES: int = Field(
        default=3,
        description="Maximum retries per LLM provider call.",
    )
    LLM_BASE_DELAY_SECONDS: float = Field(
        default=1.0,
        description="Base delay for exponential backoff between retries.",
    )

    # --- Economist Copilot (Sprint 25) ---
    COPILOT_MODEL: str = Field(
        default="claude-sonnet-4-20250514",
        description="Model for economist copilot.",
    )
    COPILOT_MAX_TOKENS: int = Field(
        default=4096,
        description="Max response tokens for copilot.",
    )
    COPILOT_ENABLED: bool = Field(
        default=True,
        description="Enable economist copilot. Set false to disable.",
    )

    # --- Azure Document Intelligence ---
    AZURE_DI_ENDPOINT: str = Field(
        default="",
        description="Azure Document Intelligence endpoint URL.",
    )
    AZURE_DI_KEY: str = Field(
        default="",
        description="Azure Document Intelligence API key.",
    )

    # --- Extraction ---
    EXTRACTION_PROVIDER: str = Field(
        default="local",
        description="Default extraction provider (local or azure_di).",
    )

    # --- Celery ---
    CELERY_BROKER_URL: str = Field(
        default="",
        description="Celery broker URL. Empty = synchronous extraction (dev/test).",
    )

    # --- Object Storage ---
    OBJECT_STORAGE_PATH: str = Field(
        default="./uploads",
        description="Local path for dev, S3 URI for prod.",
    )

    # --- MinIO (S3-compatible) ---
    MINIO_ENDPOINT: str = Field(
        default="localhost:9000",
        description="MinIO server endpoint (host:port).",
    )
    MINIO_ACCESS_KEY: str = Field(
        default="impactos",
        description="MinIO access key.",
    )
    MINIO_SECRET_KEY: str = Field(
        default="impactos-secret",
        description="MinIO secret key.",
    )
    MINIO_BUCKET: str = Field(
        default="impactos-data",
        description="Default MinIO bucket name.",
    )
    MINIO_USE_SSL: bool = Field(
        default=False,
        description="Use SSL for MinIO connections.",
    )

    # --- Security ---
    SECRET_KEY: str = Field(
        default="dev-secret-change-in-production",
        description="Application secret key for signing tokens.",
    )
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000",
        description="Comma-separated CORS allowed origins.",
    )

    # --- External IdP (staging/prod) ---
    JWT_ISSUER: str = Field(
        default="",
        description="Expected JWT issuer claim (iss). Required in non-dev.",
    )
    JWT_AUDIENCE: str = Field(
        default="",
        description="Expected JWT audience claim (aud). Required in non-dev.",
    )
    JWKS_URL: str = Field(
        default="",
        description="JWKS endpoint URL for RS256 key retrieval. Required in non-dev.",
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


_DEV_ONLY_DEFAULTS = {
    "SECRET_KEY": "dev-secret-change-in-production",
    "OBJECT_STORAGE_PATH": "./uploads",
}

_PLACEHOLDER_DB_PATTERNS = ("changeme", "localhost")


def validate_settings_for_env(settings: Settings) -> list[str]:
    """Validate settings are appropriate for the target environment.

    Returns a list of error strings. Empty list means valid.
    Dev environment accepts all defaults. Staging/prod reject
    dev-only defaults and missing required config.
    """
    if settings.ENVIRONMENT == Environment.DEV:
        return []

    errors: list[str] = []

    if settings.SECRET_KEY == _DEV_ONLY_DEFAULTS["SECRET_KEY"]:
        errors.append(
            "SECRET_KEY uses dev default — set a real secret "
            "for non-dev environments",
        )

    if settings.OBJECT_STORAGE_PATH.startswith("./"):
        errors.append(
            "OBJECT_STORAGE_PATH is a relative local path — "
            "use an absolute or S3 path for non-dev",
        )

    db_url_lower = settings.DATABASE_URL.lower()
    for pattern in _PLACEHOLDER_DB_PATTERNS:
        if pattern in db_url_lower:
            errors.append(
                f"DATABASE_URL contains '{pattern}' — "
                f"use real credentials for non-dev",
            )
            break

    if not settings.JWT_ISSUER:
        errors.append("JWT_ISSUER is required for non-dev environments")
    if not settings.JWT_AUDIENCE:
        errors.append("JWT_AUDIENCE is required for non-dev environments")
    if not settings.JWKS_URL:
        errors.append("JWKS_URL is required for non-dev environments")

    return errors


def get_settings() -> Settings:
    """Factory function for dependency injection via FastAPI Depends."""
    return Settings()
