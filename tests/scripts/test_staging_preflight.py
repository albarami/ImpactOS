"""Tests for staging preflight helpers.

Tests verify:
- PreflightReport/CheckResult dataclasses work correctly
- Secret redaction functions mask sensitive values
- Config validation check correctly maps errors to FAIL
- Dev environment is detected and reported
- has_failures() correctly identifies FAIL status
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.staging_preflight import (
    CheckResult,
    PreflightReport,
    check_alembic,
    check_config_validation,
    check_environment,
    check_no_secrets_in_report,
    redact_api_key,
    redact_database_url,
    redact_secret_key,
)
from src.config.settings import Environment, Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides: object) -> Settings:
    """Build a Settings object with sensible test defaults and overrides."""
    defaults = {
        "ENVIRONMENT": Environment.DEV,
        "DATABASE_URL": "postgresql+asyncpg://user:secret@host/db",
        "SECRET_KEY": "dev-secret-change-in-production",
        "OBJECT_STORAGE_PATH": "./uploads",
        "REDIS_URL": "redis://localhost:6379/0",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
        "OPENROUTER_API_KEY": "",
        "JWT_ISSUER": "",
        "JWT_AUDIENCE": "",
        "JWKS_URL": "",
    }
    defaults.update(overrides)
    # Use model_construct to bypass env-var loading
    return Settings.model_construct(**defaults)


# ---------------------------------------------------------------------------
# Test: CheckResult fields
# ---------------------------------------------------------------------------


class TestCheckResult:
    """CheckResult dataclass has the expected fields."""

    def test_check_result_fields(self) -> None:
        cr = CheckResult(name="test", status="PASS", detail="ok")
        assert cr.name == "test"
        assert cr.status == "PASS"
        assert cr.detail == "ok"


# ---------------------------------------------------------------------------
# Test: PreflightReport.has_failures
# ---------------------------------------------------------------------------


class TestPreflightReport:
    """PreflightReport correctly reports failures."""

    def test_preflight_report_no_failures(self) -> None:
        """All PASS -> has_failures() is False."""
        report = PreflightReport(
            overall="PASS",
            checks=[
                CheckResult(name="a", status="PASS", detail="ok"),
                CheckResult(name="b", status="PASS", detail="ok"),
            ],
        )
        assert report.has_failures() is False

    def test_preflight_report_with_failure(self) -> None:
        """One FAIL -> has_failures() is True."""
        report = PreflightReport(
            overall="FAIL",
            checks=[
                CheckResult(name="a", status="PASS", detail="ok"),
                CheckResult(name="b", status="FAIL", detail="broken"),
            ],
        )
        assert report.has_failures() is True

    def test_preflight_report_skip_not_failure(self) -> None:
        """SKIP -> has_failures() is False."""
        report = PreflightReport(
            overall="PASS",
            checks=[
                CheckResult(name="a", status="PASS", detail="ok"),
                CheckResult(name="b", status="SKIP", detail="skipped"),
            ],
        )
        assert report.has_failures() is False


# ---------------------------------------------------------------------------
# Test: Secret redaction
# ---------------------------------------------------------------------------


class TestRedactDatabaseUrl:
    """redact_database_url masks the password in connection strings."""

    def test_redact_database_url_masks_password(self) -> None:
        url = "postgresql+asyncpg://user:secret@host/db"
        result = redact_database_url(url)
        assert "secret" not in result
        assert "***" in result
        # User and host should be preserved
        assert "user" in result
        assert "host/db" in result

    def test_redact_database_url_no_password(self) -> None:
        """URL without password passes through unchanged."""
        url = "postgresql+asyncpg://host/db"
        result = redact_database_url(url)
        assert result == url


class TestRedactSecretKey:
    """redact_secret_key shows first 4 chars + '***'."""

    def test_redact_secret_key(self) -> None:
        result = redact_secret_key("my-super-secret-key-12345")
        assert result == "my-s***"
        # Full key must not appear
        assert "my-super-secret-key-12345" not in result

    def test_redact_secret_key_empty(self) -> None:
        result = redact_secret_key("")
        assert result == "not set"


class TestRedactApiKey:
    """redact_api_key returns 'set' or 'not set'."""

    def test_redact_api_key_present(self) -> None:
        result = redact_api_key("sk-abc123xyz")
        assert result == "set"

    def test_redact_api_key_absent(self) -> None:
        result = redact_api_key("")
        assert result == "not set"


# ---------------------------------------------------------------------------
# Test: Config/environment checks
# ---------------------------------------------------------------------------


class TestCheckEnvironment:
    """check_environment correctly identifies DEV vs non-dev."""

    def test_config_check_dev_environment_fails(self) -> None:
        """DEV environment -> FAIL status (must block deployment)."""
        settings = _make_settings(ENVIRONMENT=Environment.DEV)
        result = check_environment(settings)
        assert result.status == "FAIL"
        assert "dev" in result.detail.lower()

    def test_config_check_staging_passes(self) -> None:
        """STAGING environment -> PASS status."""
        settings = _make_settings(ENVIRONMENT=Environment.STAGING)
        result = check_environment(settings)
        assert result.status == "PASS"
        assert "staging" in result.detail.lower()

    def test_config_check_prod_passes(self) -> None:
        """PROD environment -> PASS status."""
        settings = _make_settings(ENVIRONMENT=Environment.PROD)
        result = check_environment(settings)
        assert result.status == "PASS"
        assert "prod" in result.detail.lower()


class TestCheckConfigValidation:
    """check_config_validation maps validate_settings_for_env errors to FAIL."""

    def test_config_check_staging_valid_passes(self) -> None:
        """Valid staging config -> PASS."""
        settings = _make_settings(
            ENVIRONMENT=Environment.STAGING,
            SECRET_KEY="production-secret-key-long-and-random",
            DATABASE_URL="postgresql+asyncpg://real_user:real_pass@prod-host.rds.amazonaws.com/impactos",
            OBJECT_STORAGE_PATH="s3://impactos-staging-data",
            JWT_ISSUER="https://auth.example.com",
            JWT_AUDIENCE="impactos-api",
            JWKS_URL="https://auth.example.com/.well-known/jwks.json",
        )
        result = check_config_validation(settings)
        assert result.status == "PASS"
        assert "passed" in result.detail.lower()

    def test_config_check_staging_invalid_fails(self) -> None:
        """Invalid staging config (dev defaults) -> FAIL with detail."""
        settings = _make_settings(
            ENVIRONMENT=Environment.STAGING,
            # Deliberately use dev defaults that should be rejected
            SECRET_KEY="dev-secret-change-in-production",
            DATABASE_URL="postgresql+asyncpg://impactos:changeme@localhost:5432/impactos",
            OBJECT_STORAGE_PATH="./uploads",
            JWT_ISSUER="",
            JWT_AUDIENCE="",
            JWKS_URL="",
        )
        result = check_config_validation(settings)
        assert result.status == "FAIL"
        assert result.detail  # should contain error descriptions

    def test_config_check_dev_always_passes(self) -> None:
        """DEV environment always passes config validation (accepts defaults)."""
        settings = _make_settings(ENVIRONMENT=Environment.DEV)
        result = check_config_validation(settings)
        assert result.status == "PASS"


# ---------------------------------------------------------------------------
# Test: Alembic check (mocked subprocess)
# ---------------------------------------------------------------------------


class TestCheckAlembic:
    """check_alembic parses named revision IDs from alembic output."""

    def test_alembic_at_head_passes(self) -> None:
        """DB at head revision -> PASS."""
        settings = _make_settings()
        with patch("scripts.staging_preflight._run_alembic_command") as mock_run:
            mock_run.side_effect = [
                (0, "020_chat_sessions_messages (head)"),  # current
                (0, "020_chat_sessions_messages (head)"),  # heads
                (0, "No new upgrade operations detected"),  # check
            ]
            result = check_alembic(settings)
        assert result.status == "PASS"

    def test_alembic_not_at_head_fails(self) -> None:
        """DB behind head revision -> FAIL."""
        settings = _make_settings()
        with patch("scripts.staging_preflight._run_alembic_command") as mock_run:
            mock_run.side_effect = [
                (0, "018_variance_bridge_analyses (head)"),  # current
                (0, "020_chat_sessions_messages (head)"),   # heads
                (0, "New upgrade operations detected"),     # check
            ]
            result = check_alembic(settings)
        assert result.status == "FAIL"

    def test_alembic_hex_revision_parsed(self) -> None:
        """Legacy hex revision IDs are also parsed correctly."""
        settings = _make_settings()
        with patch("scripts.staging_preflight._run_alembic_command") as mock_run:
            mock_run.side_effect = [
                (0, "fa33e2cd9dda (head)"),  # current
                (0, "fa33e2cd9dda (head)"),  # heads
                (0, "No new upgrade operations detected"),
            ]
            result = check_alembic(settings)
        assert result.status == "PASS"

    def test_alembic_command_failure(self) -> None:
        """alembic current fails -> FAIL."""
        settings = _make_settings()
        with patch("scripts.staging_preflight._run_alembic_command") as mock_run:
            mock_run.return_value = (1, "alembic not found on PATH")
            result = check_alembic(settings)
        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: Secret self-verification
# ---------------------------------------------------------------------------


class TestCheckNoSecrets:
    """check_no_secrets_in_report detects leaked secrets."""

    def test_clean_report_passes(self) -> None:
        """Report without secrets -> PASS."""
        report = PreflightReport(
            overall="PASS",
            checks=[CheckResult(name="a", status="PASS", detail="ok")],
        )
        settings = _make_settings(
            SECRET_KEY="my-production-secret-key-12345",
            DATABASE_URL="postgresql+asyncpg://user:s3cret@host/db",
        )
        result = check_no_secrets_in_report(report, settings)
        assert result.status == "PASS"

    def test_leaked_db_password_fails(self) -> None:
        """Report containing DB password -> FAIL."""
        report = PreflightReport(
            overall="PASS",
            checks=[
                CheckResult(
                    name="a",
                    status="FAIL",
                    detail="DB error: s3cret leaked in output",
                ),
            ],
        )
        settings = _make_settings(
            DATABASE_URL="postgresql+asyncpg://user:s3cret@host/db",
        )
        result = check_no_secrets_in_report(report, settings)
        assert result.status == "FAIL"
        assert "DATABASE_URL" in result.detail

    def test_leaked_secret_key_fails(self) -> None:
        """Report containing full SECRET_KEY -> FAIL."""
        key = "my-production-secret-key-12345"
        report = PreflightReport(
            overall="PASS",
            checks=[
                CheckResult(
                    name="a",
                    status="PASS",
                    detail=f"Config: {key}",
                ),
            ],
        )
        # Use a DB URL without a password to isolate the SECRET_KEY detection
        settings = _make_settings(
            SECRET_KEY=key,
            DATABASE_URL="postgresql+asyncpg://host/db",
        )
        result = check_no_secrets_in_report(report, settings)
        assert result.status == "FAIL"
        assert "SECRET_KEY" in result.detail


# ---------------------------------------------------------------------------
# Test: redact_secret_key short key guard
# ---------------------------------------------------------------------------


class TestRedactSecretKeyShort:
    """Short secret keys are fully redacted."""

    def test_short_key_fully_redacted(self) -> None:
        """Keys <= 4 chars return '***' (full key not exposed)."""
        assert redact_secret_key("abc") == "***"
        assert redact_secret_key("abcd") == "***"

    def test_five_char_key_partial(self) -> None:
        """Keys > 4 chars show first 4 + '***'."""
        assert redact_secret_key("abcde") == "abcd***"
