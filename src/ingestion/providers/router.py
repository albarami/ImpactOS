"""Classification-based extraction routing — S0-3.

Routes document extraction to the appropriate provider based on:
- Workspace classification (data sensitivity tier)
- Document MIME type (PDF vs spreadsheet)

Routing rules:
- RESTRICTED → LocalPdfProvider only (never send restricted docs to external API)
- PUBLIC/CONFIDENTIAL → AzureDIProvider (if configured) else LocalPdfProvider
- INTERNAL → AzureDIProvider preferred, LocalPdfProvider fallback

All routing decisions are logged for audit trail.
"""

import logging

from src.ingestion.providers.azure_di import AzureDIProvider
from src.ingestion.providers.base import ExtractionProvider
from src.ingestion.providers.local_pdf import LocalPdfProvider
from src.ingestion.providers.local_spreadsheet import LocalSpreadsheetProvider

logger = logging.getLogger(__name__)


class ExtractionRouter:
    """Selects the appropriate ExtractionProvider for a document."""

    def __init__(
        self,
        *,
        azure_di_endpoint: str = "",
        azure_di_key: str = "",
    ) -> None:
        self._local_spreadsheet = LocalSpreadsheetProvider()
        self._local_pdf = LocalPdfProvider()

        self._azure_di: AzureDIProvider | None = None
        if azure_di_endpoint and azure_di_key:
            self._azure_di = AzureDIProvider(
                endpoint=azure_di_endpoint,
                key=azure_di_key,
            )
            logger.info("Azure DI provider configured at %s", azure_di_endpoint)
        else:
            logger.info("Azure DI not configured; using local providers only")

    def select_provider(
        self,
        classification: str,
        mime_type: str,
    ) -> ExtractionProvider:
        """Select provider based on classification and MIME type.

        Args:
            classification: Data sensitivity tier (PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED).
            mime_type: Document MIME type.

        Returns:
            The appropriate ExtractionProvider.
        """
        # Spreadsheets always use local provider
        if self._is_spreadsheet(mime_type):
            logger.info(
                "Routing %s [%s] → local-spreadsheet (spreadsheet type)",
                mime_type, classification,
            )
            return self._local_spreadsheet

        # PDF routing based on classification
        provider = self._select_pdf_provider(classification)
        logger.info(
            "Routing %s [%s] → %s",
            mime_type, classification, provider.name,
        )
        return provider

    def _select_pdf_provider(self, classification: str) -> ExtractionProvider:
        """Select PDF provider based on classification."""
        classification_upper = classification.upper()

        if classification_upper == "RESTRICTED":
            # Never send restricted documents to external APIs
            return self._local_pdf

        if classification_upper in ("PUBLIC", "CONFIDENTIAL", "INTERNAL"):
            # Prefer Azure DI if available
            if self._azure_di is not None:
                return self._azure_di
            return self._local_pdf

        # Unknown classification: safe default
        logger.warning("Unknown classification %r; defaulting to local-pdf", classification)
        return self._local_pdf

    @staticmethod
    def _is_spreadsheet(mime_type: str) -> bool:
        """Check if MIME type is a spreadsheet format."""
        mime_lower = mime_type.lower()
        return any(k in mime_lower for k in ("csv", "spreadsheet", "excel"))

    @property
    def has_azure_di(self) -> bool:
        """Whether Azure DI is configured."""
        return self._azure_di is not None
