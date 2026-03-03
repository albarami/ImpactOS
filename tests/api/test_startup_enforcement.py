"""Tests for S13-1: Startup config validation enforced at boot.

Covers: non-dev app boot with dev defaults raises, dev boot succeeds,
startup error messages exclude secrets.
"""


import pytest

from src.config.settings import Settings, validate_settings_for_env


class TestStartupEnforcementAtBoot:
    """validate_settings_for_env is called during app startup in non-dev."""

    def test_non_dev_boot_with_dev_defaults_raises(self) -> None:
        """Staging boot with dev defaults should produce errors."""
        from src.api.main import _check_startup_config

        settings = Settings(
            ENVIRONMENT="staging",
            SECRET_KEY="dev-secret-change-in-production",
        )
        with pytest.raises(SystemExit):
            _check_startup_config(settings)

    def test_dev_boot_succeeds(self) -> None:
        """Dev boot with defaults should not raise."""
        from src.api.main import _check_startup_config

        settings = Settings(ENVIRONMENT="dev")
        _check_startup_config(settings)

    def test_startup_error_excludes_secrets(self) -> None:
        """Error messages from startup validation don't leak key values."""
        settings = Settings(
            ENVIRONMENT="staging",
            SECRET_KEY="dev-secret-change-in-production",
            DATABASE_URL="postgresql+asyncpg://user:s3cret@host/db",
        )
        errors = validate_settings_for_env(settings)
        combined = " ".join(errors)
        assert "s3cret" not in combined
