"""Tests for BoQ structuring pipeline (MVP-2 Section 8.4).

Covers: column normalization, value parsing, header deduplication,
completeness scoring, BoQLineItem output, evidence linking.
"""

import csv
import io
from uuid import UUID

import pytest
from uuid_extensions import uuid7

from src.models.document import BoQLineItem, DocumentGraph
from src.models.governance import BoundingBox, EvidenceSnippet, TableCellRef
from src.ingestion.boq_structuring import BoQStructuringPipeline
from src.ingestion.extraction import ExtractionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CHECKSUM = "sha256:" + "a" * 64


def _make_csv_bytes(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _extract_csv(rows: list[list[str]]) -> tuple[DocumentGraph, list[EvidenceSnippet]]:
    """Helper to extract CSV and generate snippets."""
    content = _make_csv_bytes(rows)
    doc_id = uuid7()
    svc = ExtractionService()
    graph = svc.extract_csv(doc_id=doc_id, content=content, doc_checksum=VALID_CHECKSUM)
    snippets = svc.generate_evidence_snippets(
        document_graph=graph, source_id=doc_id, doc_checksum=VALID_CHECKSUM,
    )
    return graph, snippets


# --- Standard BoQ table ---

STANDARD_BOQ = [
    ["Description", "Quantity", "Unit", "Unit Price", "Total"],
    ["Structural Steel", "5000", "tonnes", "3500", "17500000"],
    ["Concrete Works", "20000", "m3", "450", "9000000"],
    ["Rebar Supply", "3000", "tonnes", "4200", "12600000"],
]

# --- BoQ with alternate headers ---

ALTERNATE_HEADERS_BOQ = [
    ["Item Description", "Qty", "UOM", "Rate (SAR)", "Amount (SAR)"],
    ["Excavation", "10000", "m3", "50", "500000"],
    ["Backfill", "8000", "m3", "35", "280000"],
]

# --- BoQ with repeated headers (pages split) ---

REPEATED_HEADERS_BOQ = [
    ["Description", "Quantity", "Unit", "Unit Price", "Total"],
    ["Structural Steel", "5000", "tonnes", "3500", "17500000"],
    ["Description", "Quantity", "Unit", "Unit Price", "Total"],
    ["Concrete Works", "20000", "m3", "450", "9000000"],
]

# --- BoQ with section header rows ---

SECTION_HEADERS_BOQ = [
    ["Description", "Quantity", "Unit", "Unit Price", "Total"],
    ["SECTION A: CIVIL WORKS", "", "", "", ""],
    ["Excavation", "10000", "m3", "50", "500000"],
    ["Backfill", "8000", "m3", "35", "280000"],
    ["SECTION B: STEEL", "", "", "", ""],
    ["Structural Steel", "5000", "tonnes", "3500", "17500000"],
]

# --- BoQ with subtotal row ---

SUBTOTAL_BOQ = [
    ["Description", "Quantity", "Unit", "Unit Price", "Total"],
    ["Excavation", "10000", "m3", "50", "500000"],
    ["Backfill", "8000", "m3", "35", "280000"],
    ["Subtotal", "", "", "", "780000"],
]

# --- Incomplete BoQ (missing columns) ---

INCOMPLETE_BOQ = [
    ["Description", "Total"],
    ["Structural Steel", "17500000"],
    ["Concrete Works", "9000000"],
]


# ===================================================================
# Column normalization
# ===================================================================


class TestColumnNormalization:
    """Pipeline maps variant headers to canonical fields."""

    def test_standard_headers(self) -> None:
        graph, snippets = _extract_csv(STANDARD_BOQ)
        pipeline = BoQStructuringPipeline()
        items = pipeline.structure(
            document_graph=graph,
            evidence_snippets=snippets,
            extraction_job_id=uuid7(),
        )
        assert len(items) == 3
        assert all(isinstance(it, BoQLineItem) for it in items)

    def test_alternate_headers_mapped(self) -> None:
        graph, snippets = _extract_csv(ALTERNATE_HEADERS_BOQ)
        pipeline = BoQStructuringPipeline()
        items = pipeline.structure(
            document_graph=graph,
            evidence_snippets=snippets,
            extraction_job_id=uuid7(),
        )
        assert len(items) == 2
        assert items[0].description == "Excavation"
        assert items[0].quantity == 10000.0
        assert items[0].unit == "m3"
        assert items[0].unit_price == 50.0
        assert items[0].total_value == 500000.0


# ===================================================================
# Value parsing
# ===================================================================


class TestValueParsing:
    """Pipeline parses numeric values from text."""

    def test_numeric_parsing(self) -> None:
        graph, snippets = _extract_csv(STANDARD_BOQ)
        pipeline = BoQStructuringPipeline()
        items = pipeline.structure(
            document_graph=graph,
            evidence_snippets=snippets,
            extraction_job_id=uuid7(),
        )
        steel = items[0]
        assert steel.quantity == 5000.0
        assert steel.unit_price == 3500.0
        assert steel.total_value == 17500000.0

    def test_comma_separated_numbers(self) -> None:
        rows = [
            ["Description", "Quantity", "Unit", "Unit Price", "Total"],
            ["Steel", "5,000", "tonnes", "3,500.00", "17,500,000"],
        ]
        graph, snippets = _extract_csv(rows)
        pipeline = BoQStructuringPipeline()
        items = pipeline.structure(
            document_graph=graph,
            evidence_snippets=snippets,
            extraction_job_id=uuid7(),
        )
        assert items[0].quantity == 5000.0
        assert items[0].unit_price == 3500.0
        assert items[0].total_value == 17500000.0


# ===================================================================
# Header deduplication
# ===================================================================


class TestHeaderDeduplication:
    """Pipeline removes repeated header rows from multi-page tables."""

    def test_repeated_headers_removed(self) -> None:
        graph, snippets = _extract_csv(REPEATED_HEADERS_BOQ)
        pipeline = BoQStructuringPipeline()
        items = pipeline.structure(
            document_graph=graph,
            evidence_snippets=snippets,
            extraction_job_id=uuid7(),
        )
        # Only 2 data rows, not 3 (the repeated header is dropped)
        assert len(items) == 2
        descriptions = [it.description for it in items]
        assert "Structural Steel" in descriptions
        assert "Concrete Works" in descriptions


# ===================================================================
# Section headers / subtotals filtering
# ===================================================================


class TestSectionFiltering:
    """Pipeline skips section headers and subtotal rows."""

    def test_section_headers_skipped(self) -> None:
        graph, snippets = _extract_csv(SECTION_HEADERS_BOQ)
        pipeline = BoQStructuringPipeline()
        items = pipeline.structure(
            document_graph=graph,
            evidence_snippets=snippets,
            extraction_job_id=uuid7(),
        )
        # 3 data rows (Excavation, Backfill, Structural Steel)
        assert len(items) == 3
        descriptions = [it.description for it in items]
        assert "SECTION A: CIVIL WORKS" not in descriptions
        assert "SECTION B: STEEL" not in descriptions

    def test_subtotals_skipped(self) -> None:
        graph, snippets = _extract_csv(SUBTOTAL_BOQ)
        pipeline = BoQStructuringPipeline()
        items = pipeline.structure(
            document_graph=graph,
            evidence_snippets=snippets,
            extraction_job_id=uuid7(),
        )
        # 2 data rows (Subtotal row is dropped)
        assert len(items) == 2
        descriptions = [it.description for it in items]
        assert "Subtotal" not in descriptions


# ===================================================================
# Completeness scoring
# ===================================================================


class TestCompletenessScoring:
    """Pipeline computes completeness score per line item."""

    def test_full_item_has_high_completeness(self) -> None:
        graph, snippets = _extract_csv(STANDARD_BOQ)
        pipeline = BoQStructuringPipeline()
        items = pipeline.structure(
            document_graph=graph,
            evidence_snippets=snippets,
            extraction_job_id=uuid7(),
        )
        for item in items:
            assert item.completeness_score is not None
            assert item.completeness_score >= 0.8

    def test_incomplete_item_has_lower_completeness(self) -> None:
        graph, snippets = _extract_csv(INCOMPLETE_BOQ)
        pipeline = BoQStructuringPipeline()
        items = pipeline.structure(
            document_graph=graph,
            evidence_snippets=snippets,
            extraction_job_id=uuid7(),
        )
        for item in items:
            assert item.completeness_score is not None
            assert item.completeness_score < 0.8


# ===================================================================
# Evidence linking
# ===================================================================


class TestEvidenceLinking:
    """Every BoQLineItem must link to its source EvidenceSnippet."""

    def test_each_item_has_evidence_ref(self) -> None:
        graph, snippets = _extract_csv(STANDARD_BOQ)
        pipeline = BoQStructuringPipeline()
        items = pipeline.structure(
            document_graph=graph,
            evidence_snippets=snippets,
            extraction_job_id=uuid7(),
        )
        for item in items:
            assert len(item.evidence_snippet_ids) >= 1
            # Each reference should be a valid UUID
            for ref_id in item.evidence_snippet_ids:
                assert isinstance(ref_id, UUID)

    def test_evidence_ids_match_generated_snippets(self) -> None:
        graph, snippets = _extract_csv(STANDARD_BOQ)
        pipeline = BoQStructuringPipeline()
        items = pipeline.structure(
            document_graph=graph,
            evidence_snippets=snippets,
            extraction_job_id=uuid7(),
        )
        snippet_ids = {s.snippet_id for s in snippets}
        for item in items:
            for ref_id in item.evidence_snippet_ids:
                assert ref_id in snippet_ids
