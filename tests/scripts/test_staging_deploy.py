"""Tests for staging deployment prerequisite checker.

Tests verify:
- PrereqResult/DeployReport dataclasses work correctly
- has_failures() correctly identifies FAIL status
- parse_env_file handles comments, quotes, empty lines
- Each check function validates staging requirements
- Dev defaults are rejected for all critical variables
- Placeholder values are detected and rejected
- run_checks cascades FAIL on missing env file
- run_checks produces PASS for fully valid staging config
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scripts.staging_deploy import (
    DeployReport,
    PrereqResult,
    check_database_url,
    check_env_file_exists,
    check_environment_value,
    check_idp_config,
    check_minio_credentials,
    check_object_storage,
    check_postgres_credentials,
    check_secret_key,
    parse_env_file,
    run_checks,
    generate_commands,
)


# ---------------------------------------------------------------------------
# Test: PrereqResult / DeployReport dataclasses
# ---------------------------------------------------------------------------


class TestPrereqResult:
    """PrereqResult dataclass has the expected fields."""

    def test_fields(self) -> None:
        pr = PrereqResult(name="test", status="PASS", detail="ok")
        assert pr.name == "test"
        assert pr.status == "PASS"
        assert pr.detail == "ok"


class TestDeployReport:
    """DeployReport correctly reports failures."""

    def test_no_failures(self) -> None:
        report = DeployReport(
            overall="PASS",
            env_file=".env.staging",
            checks=[
                PrereqResult(name="a", status="PASS", detail="ok"),
                PrereqResult(name="b", status="PASS", detail="ok"),
            ],
        )
        assert report.has_failures() is False

    def test_with_failure(self) -> None:
        report = DeployReport(
            overall="FAIL",
            env_file=".env.staging",
            checks=[
                PrereqResult(name="a", status="PASS", detail="ok"),
                PrereqResult(name="b", status="FAIL", detail="broken"),
            ],
        )
        assert report.has_failures() is True


# ---------------------------------------------------------------------------
# Test: parse_env_file
# ---------------------------------------------------------------------------


class TestParseEnvFile:
    """parse_env_file handles various .env file formats."""

    def test_basic_parsing(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=value\nOTHER=123\n")
        env = parse_env_file(str(env_file))
        assert env["KEY"] == "value"
        assert env["OTHER"] == "123"

    def test_comments_and_empty_lines(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nKEY=value\n")
        env = parse_env_file(str(env_file))
        assert env == {"KEY": "value"}

    def test_quoted_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text('SINGLE=\'hello\'\nDOUBLE="world"\n')
        env = parse_env_file(str(env_file))
        assert env["SINGLE"] == "hello"
        assert env["DOUBLE"] == "world"

    def test_inline_comments(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=value # inline comment\n")
        env = parse_env_file(str(env_file))
        assert env["KEY"] == "value"

    def test_empty_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("EMPTY=\n")
        env = parse_env_file(str(env_file))
        assert env["EMPTY"] == ""

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        env = parse_env_file(str(tmp_path / "missing.env"))
        assert env == {}

    def test_url_with_special_chars(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql+asyncpg://user:p@ss@host:5432/db\n"
        )
        env = parse_env_file(str(env_file))
        assert "postgresql+asyncpg://" in env["DATABASE_URL"]


# ---------------------------------------------------------------------------
# Test: check_env_file_exists
# ---------------------------------------------------------------------------


class TestCheckEnvFileExists:
    """check_env_file_exists validates file presence."""

    def test_exists(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.staging"
        env_file.write_text("ENVIRONMENT=staging\n")
        result = check_env_file_exists(str(env_file))
        assert result.status == "PASS"

    def test_missing(self, tmp_path: Path) -> None:
        result = check_env_file_exists(str(tmp_path / "nonexistent.env"))
        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: check_environment_value
# ---------------------------------------------------------------------------


class TestCheckEnvironmentValue:
    """check_environment_value validates ENVIRONMENT is staging or prod."""

    def test_staging_passes(self) -> None:
        result = check_environment_value({"ENVIRONMENT": "staging"})
        assert result.status == "PASS"

    def test_prod_passes(self) -> None:
        result = check_environment_value({"ENVIRONMENT": "prod"})
        assert result.status == "PASS"

    def test_dev_fails(self) -> None:
        result = check_environment_value({"ENVIRONMENT": "dev"})
        assert result.status == "FAIL"

    def test_empty_fails(self) -> None:
        result = check_environment_value({})
        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: check_secret_key
# ---------------------------------------------------------------------------


class TestCheckSecretKey:
    """check_secret_key validates SECRET_KEY strength."""

    def test_strong_key_passes(self) -> None:
        key = "a" * 64
        result = check_secret_key({"SECRET_KEY": key})
        assert result.status == "PASS"

    def test_dev_default_fails(self) -> None:
        result = check_secret_key(
            {"SECRET_KEY": "dev-secret-change-in-production"}
        )
        assert result.status == "FAIL"

    def test_empty_fails(self) -> None:
        result = check_secret_key({"SECRET_KEY": ""})
        assert result.status == "FAIL"

    def test_placeholder_fails(self) -> None:
        result = check_secret_key({"SECRET_KEY": "REPLACE_WITH_STRONG_KEY"})
        assert result.status == "FAIL"

    def test_short_key_fails(self) -> None:
        result = check_secret_key({"SECRET_KEY": "tooshort"})
        assert result.status == "FAIL"
        assert "32" in result.detail

    def test_missing_key_fails(self) -> None:
        result = check_secret_key({})
        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: check_database_url
# ---------------------------------------------------------------------------


class TestCheckDatabaseUrl:
    """check_database_url validates DATABASE_URL for staging."""

    def test_real_url_passes(self) -> None:
        result = check_database_url(
            {"DATABASE_URL": "postgresql+asyncpg://staging_user:pass@db-host:5432/impactos"}
        )
        assert result.status == "PASS"

    def test_localhost_fails(self) -> None:
        result = check_database_url(
            {"DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db"}
        )
        assert result.status == "FAIL"
        assert "localhost" in result.detail

    def test_changeme_fails(self) -> None:
        result = check_database_url(
            {"DATABASE_URL": "postgresql+asyncpg://user:changeme@host:5432/db"}
        )
        assert result.status == "FAIL"

    def test_empty_fails(self) -> None:
        result = check_database_url({"DATABASE_URL": ""})
        assert result.status == "FAIL"

    def test_placeholder_fails(self) -> None:
        result = check_database_url(
            {"DATABASE_URL": "REPLACE_WITH_STAGING_URL"}
        )
        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: check_object_storage
# ---------------------------------------------------------------------------


class TestCheckObjectStorage:
    """check_object_storage validates OBJECT_STORAGE_PATH."""

    def test_absolute_path_passes(self) -> None:
        result = check_object_storage(
            {"OBJECT_STORAGE_PATH": "/data/impactos-storage"}
        )
        assert result.status == "PASS"

    def test_s3_uri_passes(self) -> None:
        result = check_object_storage(
            {"OBJECT_STORAGE_PATH": "s3://impactos-staging-bucket"}
        )
        assert result.status == "PASS"

    def test_relative_dot_slash_fails(self) -> None:
        result = check_object_storage(
            {"OBJECT_STORAGE_PATH": "./uploads"}
        )
        assert result.status == "FAIL"

    def test_bare_relative_path_fails(self) -> None:
        result = check_object_storage(
            {"OBJECT_STORAGE_PATH": "uploads"}
        )
        assert result.status == "FAIL"

    def test_windows_absolute_passes(self) -> None:
        result = check_object_storage(
            {"OBJECT_STORAGE_PATH": "C:\\data\\impactos"}
        )
        assert result.status == "PASS"

    def test_empty_fails(self) -> None:
        result = check_object_storage({"OBJECT_STORAGE_PATH": ""})
        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: check_idp_config
# ---------------------------------------------------------------------------


class TestCheckIdpConfig:
    """check_idp_config validates JWT/IdP variables."""

    def test_all_set_passes(self) -> None:
        result = check_idp_config({
            "JWT_ISSUER": "https://idp.example.com",
            "JWT_AUDIENCE": "impactos-api",
            "JWKS_URL": "https://idp.example.com/.well-known/jwks.json",
        })
        assert result.status == "PASS"

    def test_missing_issuer_fails(self) -> None:
        result = check_idp_config({
            "JWT_ISSUER": "",
            "JWT_AUDIENCE": "impactos-api",
            "JWKS_URL": "https://idp.example.com/.well-known/jwks.json",
        })
        assert result.status == "FAIL"
        assert "JWT_ISSUER" in result.detail

    def test_all_missing_fails(self) -> None:
        result = check_idp_config({})
        assert result.status == "FAIL"
        assert "JWT_ISSUER" in result.detail
        assert "JWT_AUDIENCE" in result.detail
        assert "JWKS_URL" in result.detail

    def test_placeholder_fails(self) -> None:
        result = check_idp_config({
            "JWT_ISSUER": "https://your-idp.example.com",
            "JWT_AUDIENCE": "impactos-api",
            "JWKS_URL": "https://your-idp.example.com/.well-known/jwks.json",
        })
        assert result.status == "FAIL"
        assert "placeholder" in result.detail.lower()


# ---------------------------------------------------------------------------
# Test: check_minio_credentials
# ---------------------------------------------------------------------------


class TestCheckMinioCredentials:
    """check_minio_credentials validates MinIO credentials."""

    def test_real_creds_pass(self) -> None:
        result = check_minio_credentials({
            "MINIO_ACCESS_KEY": "staging-access-key",
            "MINIO_SECRET_KEY": "staging-secret-key-value",
        })
        assert result.status == "PASS"

    def test_dev_defaults_fail(self) -> None:
        result = check_minio_credentials({
            "MINIO_ACCESS_KEY": "impactos",
            "MINIO_SECRET_KEY": "impactos-secret",
        })
        assert result.status == "FAIL"
        assert "dev defaults" in result.detail.lower()

    def test_empty_fails(self) -> None:
        result = check_minio_credentials({
            "MINIO_ACCESS_KEY": "",
            "MINIO_SECRET_KEY": "",
        })
        assert result.status == "FAIL"

    def test_placeholder_fails(self) -> None:
        result = check_minio_credentials({
            "MINIO_ACCESS_KEY": "REPLACE_WITH_KEY",
            "MINIO_SECRET_KEY": "REPLACE_WITH_SECRET",
        })
        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: check_postgres_credentials
# ---------------------------------------------------------------------------


class TestCheckPostgresCredentials:
    """check_postgres_credentials validates Postgres credentials."""

    def test_real_creds_pass(self) -> None:
        result = check_postgres_credentials({
            "POSTGRES_USER": "staging_user",
            "POSTGRES_PASSWORD": "strong-staging-pass",
        })
        assert result.status == "PASS"

    def test_dev_defaults_fail(self) -> None:
        result = check_postgres_credentials({
            "POSTGRES_USER": "impactos",
            "POSTGRES_PASSWORD": "impactos",
        })
        assert result.status == "FAIL"

    def test_empty_fails(self) -> None:
        result = check_postgres_credentials({
            "POSTGRES_USER": "",
            "POSTGRES_PASSWORD": "",
        })
        assert result.status == "FAIL"

    def test_placeholder_password_fails(self) -> None:
        result = check_postgres_credentials({
            "POSTGRES_USER": "staging_user",
            "POSTGRES_PASSWORD": "REPLACE_WITH_STRONG_PASSWORD",
        })
        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: run_checks integration
# ---------------------------------------------------------------------------


class TestRunChecks:
    """run_checks integrates all prerequisite checks."""

    def test_missing_env_file_fails_fast(self, tmp_path: Path) -> None:
        """Missing env file fails with only one check."""
        report = run_checks(str(tmp_path / "missing.env"))
        assert report.overall == "FAIL"
        assert len(report.checks) == 1
        assert report.checks[0].name == "env_file_exists"

    def test_valid_staging_config_passes(self, tmp_path: Path) -> None:
        """A properly configured staging env file passes all checks."""
        env_file = tmp_path / ".env.staging"
        env_file.write_text(textwrap.dedent("""\
            ENVIRONMENT=staging
            SECRET_KEY=abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmnopqrstu
            DATABASE_URL=postgresql+asyncpg://staging_user:strongpass@db-staging:5432/impactos
            OBJECT_STORAGE_PATH=/data/impactos-storage
            JWT_ISSUER=https://auth.impactos.example.com
            JWT_AUDIENCE=impactos-api
            JWKS_URL=https://auth.impactos.example.com/.well-known/jwks.json
            MINIO_ACCESS_KEY=staging-access
            MINIO_SECRET_KEY=staging-secret-value
            POSTGRES_USER=staging_user
            POSTGRES_PASSWORD=strongpass
        """))

        report = run_checks(str(env_file))
        assert report.overall == "PASS"
        assert report.has_failures() is False
        assert len(report.checks) == 8  # file + 7 checks

    def test_dev_defaults_all_fail(self, tmp_path: Path) -> None:
        """An env file with all dev defaults fails."""
        env_file = tmp_path / ".env.staging"
        env_file.write_text(textwrap.dedent("""\
            ENVIRONMENT=dev
            SECRET_KEY=dev-secret-change-in-production
            DATABASE_URL=postgresql+asyncpg://impactos:impactos@localhost:5432/impactos
            OBJECT_STORAGE_PATH=./uploads
            JWT_ISSUER=
            JWT_AUDIENCE=
            JWKS_URL=
            MINIO_ACCESS_KEY=impactos
            MINIO_SECRET_KEY=impactos-secret
            POSTGRES_USER=impactos
            POSTGRES_PASSWORD=impactos
        """))

        report = run_checks(str(env_file))
        assert report.overall == "FAIL"
        # All checks except env_file_exists should fail
        fail_count = sum(1 for c in report.checks if c.status == "FAIL")
        assert fail_count >= 7  # environment + secret + db + storage + idp + minio + postgres


# ---------------------------------------------------------------------------
# Test: generate_commands
# ---------------------------------------------------------------------------


class TestGenerateCommands:
    """generate_commands produces deployment command list."""

    def test_generates_commands(self) -> None:
        commands = generate_commands(".env.staging")
        text = "\n".join(commands)
        assert "docker compose" in text
        assert "staging_preflight" in text or "staging_smoke" in text
        assert "alembic upgrade head" in text
        assert ".env.staging" in text

    def test_custom_env_file(self) -> None:
        commands = generate_commands(".env.production")
        text = "\n".join(commands)
        assert ".env.production" in text
