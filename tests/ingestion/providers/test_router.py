"""Tests for ExtractionRouter — S0-3.

Verifies classification-based routing logic.
"""

import pytest

from src.ingestion.providers.router import ExtractionRouter


class TestSpreadsheetRouting:
    """Spreadsheet MIME types always route to local-spreadsheet."""

    def test_csv_routes_to_local_spreadsheet(self) -> None:
        router = ExtractionRouter()
        provider = router.select_provider("RESTRICTED", "text/csv")
        assert provider.name == "local-spreadsheet"

    def test_xlsx_routes_to_local_spreadsheet(self) -> None:
        router = ExtractionRouter()
        provider = router.select_provider(
            "PUBLIC",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        assert provider.name == "local-spreadsheet"

    def test_excel_routes_to_local_spreadsheet(self) -> None:
        router = ExtractionRouter()
        provider = router.select_provider("INTERNAL", "application/vnd.ms-excel")
        assert provider.name == "local-spreadsheet"


class TestPdfRoutingNoAzure:
    """PDF routing when Azure DI is NOT configured."""

    def test_restricted_routes_to_local_pdf(self) -> None:
        router = ExtractionRouter()
        provider = router.select_provider("RESTRICTED", "application/pdf")
        assert provider.name == "local-pdf"

    def test_public_routes_to_local_pdf(self) -> None:
        router = ExtractionRouter()
        provider = router.select_provider("PUBLIC", "application/pdf")
        assert provider.name == "local-pdf"

    def test_confidential_routes_to_local_pdf(self) -> None:
        router = ExtractionRouter()
        provider = router.select_provider("CONFIDENTIAL", "application/pdf")
        assert provider.name == "local-pdf"

    def test_internal_routes_to_local_pdf(self) -> None:
        router = ExtractionRouter()
        provider = router.select_provider("INTERNAL", "application/pdf")
        assert provider.name == "local-pdf"


class TestPdfRoutingWithAzure:
    """PDF routing when Azure DI IS configured."""

    def _router_with_azure(self) -> ExtractionRouter:
        return ExtractionRouter(
            azure_di_endpoint="https://test.cognitiveservices.azure.com",
            azure_di_key="test-key",
        )

    def test_restricted_always_local(self) -> None:
        """RESTRICTED documents NEVER go to external APIs."""
        router = self._router_with_azure()
        provider = router.select_provider("RESTRICTED", "application/pdf")
        assert provider.name == "local-pdf"

    def test_public_routes_to_azure(self) -> None:
        router = self._router_with_azure()
        provider = router.select_provider("PUBLIC", "application/pdf")
        assert provider.name == "azure-di"

    def test_confidential_routes_to_azure(self) -> None:
        router = self._router_with_azure()
        provider = router.select_provider("CONFIDENTIAL", "application/pdf")
        assert provider.name == "azure-di"

    def test_internal_routes_to_azure(self) -> None:
        router = self._router_with_azure()
        provider = router.select_provider("INTERNAL", "application/pdf")
        assert provider.name == "azure-di"

    def test_spreadsheet_ignores_azure(self) -> None:
        """Spreadsheets always local, even when Azure is configured."""
        router = self._router_with_azure()
        provider = router.select_provider("PUBLIC", "text/csv")
        assert provider.name == "local-spreadsheet"


class TestRouterMeta:
    """Router metadata."""

    def test_has_azure_di_false_by_default(self) -> None:
        router = ExtractionRouter()
        assert router.has_azure_di is False

    def test_has_azure_di_true_when_configured(self) -> None:
        router = ExtractionRouter(
            azure_di_endpoint="https://test.cognitiveservices.azure.com",
            azure_di_key="test-key",
        )
        assert router.has_azure_di is True

    def test_unknown_classification_defaults_to_local(self) -> None:
        router = ExtractionRouter()
        provider = router.select_provider("UNKNOWN", "application/pdf")
        assert provider.name == "local-pdf"
