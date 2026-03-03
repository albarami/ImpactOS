"""Tests for S13-2: Non-dev extraction blocks silent fallback.

Covers: non-dev Azure DI failure raises instead of falling back to
local-pdf, non-dev without Azure DI configured raises for non-RESTRICTED,
RESTRICTED classification still uses local-only in all envs.
"""


import pytest

from src.ingestion.providers.router import ExtractionRouter


class TestNonDevExtractionRouterRejectsLocal:
    """Non-dev router must not silently fall back to local-pdf."""

    def test_non_dev_non_restricted_without_azure_raises(self) -> None:
        """Staging: non-RESTRICTED PDF without Azure DI → error."""
        router = ExtractionRouter(
            azure_di_endpoint="", azure_di_key="",
        )
        with pytest.raises(RuntimeError, match="Azure DI"):
            router.select_provider(
                classification="CONFIDENTIAL",
                mime_type="application/pdf",
                environment="staging",
            )

    def test_non_dev_public_without_azure_raises(self) -> None:
        router = ExtractionRouter(
            azure_di_endpoint="", azure_di_key="",
        )
        with pytest.raises(RuntimeError, match="Azure DI"):
            router.select_provider(
                classification="PUBLIC",
                mime_type="application/pdf",
                environment="staging",
            )

    def test_restricted_always_uses_local(self) -> None:
        """RESTRICTED uses local-pdf regardless of environment."""
        router = ExtractionRouter(
            azure_di_endpoint="", azure_di_key="",
        )
        provider = router.select_provider(
            classification="RESTRICTED",
            mime_type="application/pdf",
            environment="staging",
        )
        assert provider.name == "local-pdf"

    def test_dev_allows_local_fallback(self) -> None:
        """Dev: non-RESTRICTED without Azure DI → local-pdf OK."""
        router = ExtractionRouter(
            azure_di_endpoint="", azure_di_key="",
        )
        provider = router.select_provider(
            classification="CONFIDENTIAL",
            mime_type="application/pdf",
            environment="dev",
        )
        assert provider.name == "local-pdf"

    def test_spreadsheets_always_local(self) -> None:
        """Spreadsheets use local provider in all environments."""
        router = ExtractionRouter(
            azure_di_endpoint="", azure_di_key="",
        )
        for env in ("dev", "staging", "prod"):
            provider = router.select_provider(
                classification="CONFIDENTIAL",
                mime_type="text/csv",
                environment=env,
            )
            assert "spreadsheet" in provider.name
