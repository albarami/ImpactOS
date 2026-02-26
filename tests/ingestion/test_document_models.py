"""Tests for MVP-2 document ingestion Pydantic models.

Covers: Document, DocumentGraph, PageBlock, TableCell, ExtractedTable,
BoQLineItem, ExtractionJob, ExtractionStatus.
"""

from uuid import UUID

import pytest
from pydantic import ValidationError
from uuid_extensions import uuid7

from src.models.common import DataClassification
from src.models.document import (
    BoQLineItem,
    Document,
    DocumentGraph,
    DocumentType,
    ExtractionJob,
    ExtractionMetadata,
    ExtractionStatus,
    ExtractedTable,
    LanguageCode,
    PageBlock,
    SourceType,
    TableCell,
)
from src.models.governance import BoundingBox


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CHECKSUM = "sha256:" + "a" * 64


def _make_document(**overrides: object) -> Document:
    defaults: dict[str, object] = {
        "workspace_id": uuid7(),
        "filename": "boq_neom.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 1_048_576,
        "hash_sha256": VALID_CHECKSUM,
        "storage_key": "ws/doc_abc/boq_neom.pdf",
        "uploaded_by": uuid7(),
        "doc_type": DocumentType.BOQ,
        "source_type": SourceType.CLIENT,
        "classification": DataClassification.RESTRICTED,
        "language": LanguageCode.EN,
    }
    defaults.update(overrides)
    return Document(**defaults)  # type: ignore[arg-type]


def _make_table_cell(**overrides: object) -> TableCell:
    defaults: dict[str, object] = {
        "row": 0,
        "col": 0,
        "text": "100,000",
        "bbox": BoundingBox(x0=0.1, y0=0.2, x1=0.3, y1=0.25),
        "confidence": 0.95,
    }
    defaults.update(overrides)
    return TableCell(**defaults)  # type: ignore[arg-type]


def _make_extracted_table(**overrides: object) -> ExtractedTable:
    defaults: dict[str, object] = {
        "table_id": "table_001",
        "page_number": 0,
        "bbox": BoundingBox(x0=0.05, y0=0.1, x1=0.95, y1=0.8),
        "cells": [_make_table_cell()],
    }
    defaults.update(overrides)
    return ExtractedTable(**defaults)  # type: ignore[arg-type]


def _make_page_block(**overrides: object) -> PageBlock:
    defaults: dict[str, object] = {
        "page_number": 0,
        "blocks": [{"text": "Section 1", "bbox": BoundingBox(x0=0.1, y0=0.1, x1=0.9, y1=0.15), "block_type": "text"}],
        "tables": [_make_extracted_table()],
    }
    defaults.update(overrides)
    return PageBlock(**defaults)  # type: ignore[arg-type]


def _make_boq_line_item(**overrides: object) -> BoQLineItem:
    defaults: dict[str, object] = {
        "doc_id": uuid7(),
        "extraction_job_id": uuid7(),
        "raw_text": "Structural steel supply",
        "description": "Structural steel supply",
        "quantity": 5000.0,
        "unit": "tonnes",
        "unit_price": 3500.0,
        "total_value": 17_500_000.0,
        "currency_code": "SAR",
        "page_ref": 12,
        "evidence_snippet_ids": [uuid7()],
    }
    defaults.update(overrides)
    return BoQLineItem(**defaults)  # type: ignore[arg-type]


# ===================================================================
# ExtractionStatus enum
# ===================================================================


class TestExtractionStatus:
    """ExtractionStatus values are correct."""

    def test_all_statuses_exist(self) -> None:
        assert ExtractionStatus.QUEUED == "QUEUED"
        assert ExtractionStatus.RUNNING == "RUNNING"
        assert ExtractionStatus.COMPLETED == "COMPLETED"
        assert ExtractionStatus.FAILED == "FAILED"


# ===================================================================
# DocumentType and SourceType enums
# ===================================================================


class TestDocumentEnums:
    """Document-related enums have correct values."""

    def test_document_types(self) -> None:
        assert DocumentType.BOQ == "BOQ"
        assert DocumentType.CAPEX == "CAPEX"
        assert DocumentType.POLICY == "POLICY"
        assert DocumentType.OTHER == "OTHER"

    def test_source_types(self) -> None:
        assert SourceType.CLIENT == "CLIENT"
        assert SourceType.PUBLIC == "PUBLIC"
        assert SourceType.INTERNAL == "INTERNAL"

    def test_language_codes(self) -> None:
        assert LanguageCode.EN == "en"
        assert LanguageCode.AR == "ar"
        assert LanguageCode.BILINGUAL == "bilingual"


# ===================================================================
# Document model
# ===================================================================


class TestDocument:
    """Document model creation and validation."""

    def test_creation_succeeds(self) -> None:
        doc = _make_document()
        assert isinstance(doc.doc_id, UUID)
        assert doc.filename == "boq_neom.pdf"

    def test_uuid_is_generated(self) -> None:
        doc = _make_document()
        assert isinstance(doc.doc_id, UUID)

    def test_timestamp_is_timezone_aware(self) -> None:
        doc = _make_document()
        assert doc.uploaded_at.tzinfo is not None

    def test_bad_checksum_rejected(self) -> None:
        with pytest.raises(ValidationError, match="hash_sha256"):
            _make_document(hash_sha256="md5:bad")

    def test_empty_filename_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_document(filename="")

    def test_negative_size_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_document(size_bytes=-1)

    def test_invalid_doc_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_document(doc_type="INVALID")

    def test_invalid_source_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_document(source_type="INVALID")

    def test_invalid_classification_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_document(classification="TOP_SECRET")


# ===================================================================
# TableCell model
# ===================================================================


class TestTableCell:
    """TableCell stores cell coordinates, text, and confidence."""

    def test_creation_succeeds(self) -> None:
        cell = _make_table_cell()
        assert cell.row == 0
        assert cell.col == 0
        assert cell.text == "100,000"

    def test_negative_row_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_table_cell(row=-1)

    def test_negative_col_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_table_cell(col=-1)

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_table_cell(confidence=1.5)

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_table_cell(confidence=-0.1)


# ===================================================================
# ExtractedTable model
# ===================================================================


class TestExtractedTable:
    """ExtractedTable bundles cells with bounding box."""

    def test_creation_succeeds(self) -> None:
        table = _make_extracted_table()
        assert table.table_id == "table_001"
        assert len(table.cells) == 1

    def test_empty_table_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_extracted_table(table_id="")


# ===================================================================
# PageBlock model
# ===================================================================


class TestPageBlock:
    """PageBlock represents a single page with blocks and tables."""

    def test_creation_succeeds(self) -> None:
        page = _make_page_block()
        assert page.page_number == 0
        assert len(page.tables) == 1

    def test_negative_page_number_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_page_block(page_number=-1)


# ===================================================================
# DocumentGraph model
# ===================================================================


class TestDocumentGraph:
    """DocumentGraph bundles pages with extraction metadata."""

    def test_creation_succeeds(self) -> None:
        graph = DocumentGraph(
            document_id=uuid7(),
            pages=[_make_page_block()],
            extraction_metadata=ExtractionMetadata(
                engine="layout-aware-v1",
                engine_version="1.0.0",
            ),
        )
        assert len(graph.pages) == 1
        assert graph.extraction_metadata.engine == "layout-aware-v1"

    def test_empty_pages_allowed(self) -> None:
        graph = DocumentGraph(
            document_id=uuid7(),
            pages=[],
            extraction_metadata=ExtractionMetadata(
                engine="layout-aware-v1",
                engine_version="1.0.0",
            ),
        )
        assert len(graph.pages) == 0


# ===================================================================
# BoQLineItem model
# ===================================================================


class TestBoQLineItem:
    """BoQLineItem represents a normalized spend line from extraction."""

    def test_creation_succeeds(self) -> None:
        item = _make_boq_line_item()
        assert isinstance(item.line_item_id, UUID)
        assert item.total_value == 17_500_000.0

    def test_evidence_snippet_ids_required(self) -> None:
        """Every line item must link to at least one evidence snippet."""
        with pytest.raises(ValidationError, match="evidence_snippet_ids"):
            _make_boq_line_item(evidence_snippet_ids=[])

    def test_empty_raw_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_boq_line_item(raw_text="")

    def test_nullable_fields_default_to_none(self) -> None:
        item = _make_boq_line_item(
            quantity=None,
            unit=None,
            unit_price=None,
            total_value=None,
            year_or_phase=None,
            vendor=None,
            category_code=None,
        )
        assert item.quantity is None
        assert item.vendor is None

    def test_page_ref_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_boq_line_item(page_ref=-1)

    def test_completeness_score_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_boq_line_item(completeness_score=1.5)


# ===================================================================
# ExtractionJob model
# ===================================================================


class TestExtractionJob:
    """ExtractionJob tracks async extraction work."""

    def test_creation_defaults(self) -> None:
        job = ExtractionJob(
            doc_id=uuid7(),
            workspace_id=uuid7(),
        )
        assert job.status == ExtractionStatus.QUEUED
        assert isinstance(job.job_id, UUID)
        assert job.error_message is None

    def test_status_transitions(self) -> None:
        job = ExtractionJob(
            doc_id=uuid7(),
            workspace_id=uuid7(),
            status=ExtractionStatus.RUNNING,
        )
        assert job.status == ExtractionStatus.RUNNING

    def test_failed_job_can_have_error_message(self) -> None:
        job = ExtractionJob(
            doc_id=uuid7(),
            workspace_id=uuid7(),
            status=ExtractionStatus.FAILED,
            error_message="PDF corrupted",
        )
        assert job.error_message == "PDF corrupted"

    def test_extract_tables_default_true(self) -> None:
        job = ExtractionJob(
            doc_id=uuid7(),
            workspace_id=uuid7(),
        )
        assert job.extract_tables is True

    def test_extract_line_items_default_true(self) -> None:
        job = ExtractionJob(
            doc_id=uuid7(),
            workspace_id=uuid7(),
        )
        assert job.extract_line_items is True
