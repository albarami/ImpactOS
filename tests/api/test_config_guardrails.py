"""Tests for S12-1: Non-dev config guardrails (fail-closed).

Covers: startup validation rejects non-dev boot with dev defaults
for SECRET_KEY, OBJECT_STORAGE_PATH, DATABASE_URL placeholder creds,
and missing JWT/JWKS config. Dev profile continues working.
"""


from src.config.settings import Settings, validate_settings_for_env


class TestNonDevRejectsDevDefaults:
    """Non-dev environments must reject dev-only default values."""

    def test_staging_rejects_default_secret_key(self) -> None:
        errors = validate_settings_for_env(Settings(
            ENVIRONMENT="staging",
            SECRET_KEY="dev-secret-change-in-production",
            JWT_ISSUER="x", JWT_AUDIENCE="y", JWKS_URL="z",
            DATABASE_URL="postgresql+asyncpg://real:real@db:5432/real",
            OBJECT_STORAGE_PATH="/mnt/storage",
        ))
        assert any("SECRET_KEY" in e for e in errors)

    def test_prod_rejects_default_secret_key(self) -> None:
        errors = validate_settings_for_env(Settings(
            ENVIRONMENT="prod",
            SECRET_KEY="dev-secret-change-in-production",
            JWT_ISSUER="x", JWT_AUDIENCE="y", JWKS_URL="z",
            DATABASE_URL="postgresql+asyncpg://real:real@db:5432/real",
            OBJECT_STORAGE_PATH="/mnt/storage",
        ))
        assert any("SECRET_KEY" in e for e in errors)

    def test_staging_rejects_local_object_storage(self) -> None:
        errors = validate_settings_for_env(Settings(
            ENVIRONMENT="staging",
            SECRET_KEY="real-secret-key-here",
            JWT_ISSUER="x", JWT_AUDIENCE="y", JWKS_URL="z",
            DATABASE_URL="postgresql+asyncpg://real:real@db:5432/real",
            OBJECT_STORAGE_PATH="./uploads",
        ))
        assert any("OBJECT_STORAGE" in e for e in errors)

    def test_staging_rejects_placeholder_db_creds(self) -> None:
        errors = validate_settings_for_env(Settings(
            ENVIRONMENT="staging",
            SECRET_KEY="real-secret",
            JWT_ISSUER="x", JWT_AUDIENCE="y", JWKS_URL="z",
            DATABASE_URL="postgresql+asyncpg://impactos:changeme@localhost:5432/impactos",
            OBJECT_STORAGE_PATH="/mnt/s3",
        ))
        assert any("DATABASE_URL" in e for e in errors)

    def test_staging_rejects_missing_jwt_config(self) -> None:
        errors = validate_settings_for_env(Settings(
            ENVIRONMENT="staging",
            SECRET_KEY="real-secret",
            JWT_ISSUER="", JWT_AUDIENCE="", JWKS_URL="",
            DATABASE_URL="postgresql+asyncpg://real:real@db:5432/real",
            OBJECT_STORAGE_PATH="/mnt/s3",
        ))
        assert any("JWT_ISSUER" in e for e in errors)
        assert any("JWT_AUDIENCE" in e for e in errors)
        assert any("JWKS_URL" in e for e in errors)


class TestDevProfileWorks:
    """Dev environment accepts all dev defaults without error."""

    def test_dev_accepts_all_defaults(self) -> None:
        errors = validate_settings_for_env(Settings(ENVIRONMENT="dev"))
        assert errors == []

    def test_dev_with_default_secret_key_ok(self) -> None:
        errors = validate_settings_for_env(Settings(
            ENVIRONMENT="dev",
            SECRET_KEY="dev-secret-change-in-production",
        ))
        assert errors == []


class TestValidNonDevConfig:
    """Properly configured non-dev settings pass validation."""

    def test_staging_with_real_config_passes(self) -> None:
        errors = validate_settings_for_env(Settings(
            ENVIRONMENT="staging",
            SECRET_KEY="a-real-production-secret-key-32chars",
            JWT_ISSUER="https://idp.example.com",
            JWT_AUDIENCE="impactos-api",
            JWKS_URL="https://idp.example.com/.well-known/jwks.json",
            DATABASE_URL="postgresql+asyncpg://user:pass@db-host:5432/impactos",
            OBJECT_STORAGE_PATH="s3://impactos-bucket",
        ))
        assert errors == []
