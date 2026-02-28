"""LocalSpreadsheetProvider — wraps existing CSV/Excel extraction.

Delegates to ExtractionService which uses openpyxl for Excel and the
stdlib csv module for CSV files. Confidence is 1.0 (exact data).
"""

from uuid import UUID

from src.ingestion.extraction import ExtractionService
from src.ingestion.providers.base import ExtractionOptions, ExtractionProvider
from src.models.document import DocumentGraph

_SPREADSHEET_MIMES = frozenset({
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
})


class LocalSpreadsheetProvider(ExtractionProvider):
    """CSV and Excel extraction via openpyxl / stdlib csv."""

    def __init__(self) -> None:
        self._svc = ExtractionService()

    @property
    def name(self) -> str:
        return "local-spreadsheet"

    async def extract(
        self,
        document_bytes: bytes,
        mime_type: str,
        doc_id: UUID,
        options: ExtractionOptions,
    ) -> DocumentGraph:
        mime_lower = mime_type.lower()
        if "csv" in mime_lower:
            return self._svc.extract_csv(
                doc_id=doc_id,
                content=document_bytes,
                doc_checksum=options.doc_checksum,
            )
        return self._svc.extract_excel(
            doc_id=doc_id,
            content=document_bytes,
            doc_checksum=options.doc_checksum,
        )

    def supported_mime_types(self) -> frozenset[str]:
        return _SPREADSHEET_MIMES
