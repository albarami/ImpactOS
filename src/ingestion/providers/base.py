"""ExtractionProvider abstract interface — S0-3.

All extraction providers implement this interface. They accept raw document
bytes and return a DocumentGraph with tables, text blocks, and bounding boxes.
Evidence snippet generation is handled separately by ExtractionService.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from pydantic import Field

from src.models.common import ImpactOSBase
from src.models.document import DocumentGraph


class ExtractionOptions(ImpactOSBase):
    """Configuration for an extraction run."""

    extract_tables: bool = True
    extract_line_items: bool = True
    language_hint: str = "en"
    doc_checksum: str = Field(default="", description="SHA-256 hash for evidence linking.")


class ExtractionProvider(ABC):
    """Abstract extraction provider.

    All providers produce the same DocumentGraph output format regardless
    of the underlying engine (pdfplumber, Azure DI, CSV parser, etc.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name for audit logging."""
        ...

    @abstractmethod
    async def extract(
        self,
        document_bytes: bytes,
        mime_type: str,
        doc_id: UUID,
        options: ExtractionOptions,
    ) -> DocumentGraph:
        """Extract tables and text from document bytes.

        Args:
            document_bytes: Raw file content.
            mime_type: MIME type of the document.
            doc_id: Document ID for provenance.
            options: Extraction configuration.

        Returns:
            DocumentGraph with pages, tables, and text blocks.
        """
        ...

    @abstractmethod
    def supported_mime_types(self) -> frozenset[str]:
        """Set of MIME types this provider can handle."""
        ...
