"""Document ingestion models — MVP-2 (Section 8 of tech spec).

Models for document upload, table extraction, BoQ structuring, and extraction jobs.
These are deterministic pipeline models — no LLM calls involved.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from src.models.common import (
    DataClassification,
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)
from src.models.governance import BoundingBox


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DocumentType(StrEnum):
    """Document type classification per Section 3.3.1."""

    BOQ = "BOQ"
    CAPEX = "CAPEX"
    POLICY = "POLICY"
    OTHER = "OTHER"


class SourceType(StrEnum):
    """Document source provenance."""

    CLIENT = "CLIENT"
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"


class LanguageCode(StrEnum):
    """Supported document languages."""

    EN = "en"
    AR = "ar"
    BILINGUAL = "bilingual"


class ExtractionStatus(StrEnum):
    """Lifecycle status for an extraction job."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Document (stored document metadata)
# ---------------------------------------------------------------------------


class Document(ImpactOSBase):
    """Uploaded document metadata per Section 8.1 and Data Spec 3.3.1.

    Stored alongside raw file in object storage with immutable versioning.
    """

    doc_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    filename: str = Field(..., min_length=1, max_length=500)
    mime_type: str = Field(..., min_length=1, max_length=200)
    size_bytes: int = Field(..., ge=0)
    hash_sha256: str = Field(
        ...,
        pattern=r"^sha256:[a-f0-9]{64}$",
        description="SHA-256 hash for immutability verification.",
    )
    storage_key: str = Field(
        ..., min_length=1, description="Object storage key (path)."
    )
    uploaded_by: UUID
    uploaded_at: UTCTimestamp = Field(default_factory=utc_now)
    doc_type: DocumentType
    source_type: SourceType
    classification: DataClassification
    language: LanguageCode = Field(default=LanguageCode.EN)


# ---------------------------------------------------------------------------
# Extraction data model: TableCell, ExtractedTable, PageBlock, DocumentGraph
# Per Section 8.3 (DocumentGraph)
# ---------------------------------------------------------------------------


class TableCell(ImpactOSBase):
    """Single cell in an extracted table with coordinates and confidence."""

    row: int = Field(..., ge=0)
    col: int = Field(..., ge=0)
    text: str = ""
    bbox: BoundingBox
    confidence: float = Field(..., ge=0.0, le=1.0)


class ExtractedTable(ImpactOSBase):
    """Table extracted from a document page with cell-level detail."""

    table_id: str = Field(..., min_length=1)
    page_number: int = Field(..., ge=0)
    bbox: BoundingBox
    cells: list[TableCell] = Field(default_factory=list)


class TextBlock(ImpactOSBase):
    """A block of text on a page with bounding box and type."""

    text: str = ""
    bbox: BoundingBox
    block_type: str = Field(default="text")


class PageBlock(ImpactOSBase):
    """A single page with text blocks and extracted tables (Section 8.3)."""

    page_number: int = Field(..., ge=0)
    blocks: list[TextBlock] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)


class ExtractionMetadata(ImpactOSBase):
    """Metadata about the extraction engine run."""

    engine: str = Field(..., min_length=1)
    engine_version: str = Field(..., min_length=1)
    started_at: UTCTimestamp = Field(default_factory=utc_now)
    completed_at: UTCTimestamp | None = None
    errors: list[str] = Field(default_factory=list)


class DocumentGraph(ImpactOSBase):
    """Full extracted representation of a document (Section 8.3).

    Contains all pages with their text blocks and tables.
    """

    document_id: UUID
    pages: list[PageBlock] = Field(default_factory=list)
    extraction_metadata: ExtractionMetadata


# ---------------------------------------------------------------------------
# BoQLineItem (Section 8.4 + Data Spec 3.3.2)
# ---------------------------------------------------------------------------


class BoQLineItem(ImpactOSBase):
    """Normalized spend line item extracted from a BoQ document.

    Every line item MUST link to at least one EvidenceSnippet via
    evidence_snippet_ids for audit-grade traceability.
    """

    line_item_id: UUIDv7 = Field(default_factory=new_uuid7)
    doc_id: UUID
    extraction_job_id: UUID
    raw_text: str = Field(..., min_length=1, max_length=5000)
    description: str = Field(default="", max_length=2000)
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    total_value: float | None = None
    currency_code: str = Field(default="SAR", max_length=10)
    year_or_phase: str | None = None
    vendor: str | None = None
    category_code: str | None = None
    page_ref: int = Field(..., ge=0, description="0-indexed page number.")
    evidence_snippet_ids: list[UUID] = Field(
        ..., min_length=1, description="At least one evidence snippet required."
    )
    completeness_score: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Fraction of expected fields that are populated.",
    )
    created_at: UTCTimestamp = Field(default_factory=utc_now)

    @field_validator("evidence_snippet_ids")
    @classmethod
    def _at_least_one_evidence(cls, v: list[UUID]) -> list[UUID]:
        if len(v) == 0:
            msg = "Every line item must link to at least one evidence snippet."
            raise ValueError(msg)
        return v


# ---------------------------------------------------------------------------
# ExtractionJob (async extraction tracking)
# ---------------------------------------------------------------------------


class ExtractionJob(ImpactOSBase):
    """Tracks an asynchronous document extraction job (Section 8.1 step 5)."""

    job_id: UUIDv7 = Field(default_factory=new_uuid7)
    doc_id: UUID
    workspace_id: UUID
    status: ExtractionStatus = Field(default=ExtractionStatus.QUEUED)
    extract_tables: bool = Field(default=True)
    extract_line_items: bool = Field(default=True)
    language_hint: LanguageCode = Field(default=LanguageCode.EN)
    error_message: str | None = None
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    updated_at: UTCTimestamp = Field(default_factory=utc_now)
