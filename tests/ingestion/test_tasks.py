"""Tests for extraction orchestration (tasks.py) — S0-3.

Tests run_extraction directly with mock providers (no Celery needed).
"""

import csv
import io
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from uuid_extensions import uuid7

from src.ingestion.providers.base import ExtractionOptions
from src.ingestion.tasks import run_extraction
from src.models.document import (
    DocumentGraph,
    ExtractionMetadata,
    ExtractedTable,
    PageBlock,
    TableCell,
)
from src.models.governance import BoundingBox

VALID_CHECKSUM = "sha256:" + "a" * 64


def _make_csv_bytes() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows([
        ["Description", "Quantity", "Unit", "Unit Price", "Total"],
        ["Structural Steel", "5000", "tonnes", "3500", "17500000"],
        ["Concrete", "20000", "m3", "450", "9000000"],
    ])
    return buf.getvalue().encode("utf-8")


def _make_mock_graph(doc_id: UUID) -> DocumentGraph:
    """Build a simple DocumentGraph for testing."""
    cells = [
        TableCell(row=0, col=0, text="Description", bbox=BoundingBox(x0=0, y0=0, x1=0.5, y1=0.5), confidence=1.0),
        TableCell(row=0, col=1, text="Total", bbox=BoundingBox(x0=0.5, y0=0, x1=1, y1=0.5), confidence=1.0),
        TableCell(row=1, col=0, text="Steel", bbox=BoundingBox(x0=0, y0=0.5, x1=0.5, y1=1), confidence=1.0),
        TableCell(row=1, col=1, text="17500000", bbox=BoundingBox(x0=0.5, y0=0.5, x1=1, y1=1), confidence=1.0),
    ]
    table = ExtractedTable(
        table_id="test_table_0",
        page_number=0,
        bbox=BoundingBox(x0=0, y0=0, x1=1, y1=1),
        cells=cells,
    )
    return DocumentGraph(
        document_id=doc_id,
        pages=[PageBlock(page_number=0, blocks=[], tables=[table])],
        extraction_metadata=ExtractionMetadata(engine="test", engine_version="1.0"),
    )


class TestRunExtraction:
    """Test the run_extraction orchestration function."""

    @pytest.mark.anyio
    async def test_csv_extraction_completes(self) -> None:
        """CSV documents should extract successfully via provider router."""
        job_id = uuid7()
        doc_id = uuid7()
        workspace_id = uuid7()

        mock_job_repo = AsyncMock()
        mock_line_item_repo = AsyncMock()

        status = await run_extraction(
            job_id=job_id,
            doc_id=doc_id,
            workspace_id=workspace_id,
            document_bytes=_make_csv_bytes(),
            mime_type="text/csv",
            filename="boq.csv",
            classification="RESTRICTED",
            doc_checksum=VALID_CHECKSUM,
            extract_tables=True,
            extract_line_items=True,
            language_hint="en",
            job_repo=mock_job_repo,
            line_item_repo=mock_line_item_repo,
        )

        assert status == "COMPLETED"

    @pytest.mark.anyio
    async def test_updates_job_to_running(self) -> None:
        mock_job_repo = AsyncMock()
        mock_line_item_repo = AsyncMock()
        job_id = uuid7()

        await run_extraction(
            job_id=job_id,
            doc_id=uuid7(),
            workspace_id=uuid7(),
            document_bytes=_make_csv_bytes(),
            mime_type="text/csv",
            filename="boq.csv",
            classification="RESTRICTED",
            doc_checksum=VALID_CHECKSUM,
            job_repo=mock_job_repo,
            line_item_repo=mock_line_item_repo,
        )

        # First call should be update to RUNNING
        mock_job_repo.update_status.assert_any_call(job_id, "RUNNING")

    @pytest.mark.anyio
    async def test_updates_job_to_completed(self) -> None:
        mock_job_repo = AsyncMock()
        mock_line_item_repo = AsyncMock()
        job_id = uuid7()

        await run_extraction(
            job_id=job_id,
            doc_id=uuid7(),
            workspace_id=uuid7(),
            document_bytes=_make_csv_bytes(),
            mime_type="text/csv",
            filename="boq.csv",
            classification="RESTRICTED",
            doc_checksum=VALID_CHECKSUM,
            job_repo=mock_job_repo,
            line_item_repo=mock_line_item_repo,
        )

        # Last call should be update to COMPLETED
        mock_job_repo.update_status.assert_called_with(
            job_id, "COMPLETED", error_message=None,
        )

    @pytest.mark.anyio
    async def test_persists_line_items(self) -> None:
        mock_job_repo = AsyncMock()
        mock_line_item_repo = AsyncMock()

        await run_extraction(
            job_id=uuid7(),
            doc_id=uuid7(),
            workspace_id=uuid7(),
            document_bytes=_make_csv_bytes(),
            mime_type="text/csv",
            filename="boq.csv",
            classification="RESTRICTED",
            doc_checksum=VALID_CHECKSUM,
            extract_line_items=True,
            job_repo=mock_job_repo,
            line_item_repo=mock_line_item_repo,
        )

        mock_line_item_repo.create_many.assert_called_once()
        items = mock_line_item_repo.create_many.call_args[0][0]
        assert len(items) == 2  # 2 data rows in CSV

    @pytest.mark.anyio
    async def test_skip_line_items_when_disabled(self) -> None:
        mock_job_repo = AsyncMock()
        mock_line_item_repo = AsyncMock()

        await run_extraction(
            job_id=uuid7(),
            doc_id=uuid7(),
            workspace_id=uuid7(),
            document_bytes=_make_csv_bytes(),
            mime_type="text/csv",
            filename="boq.csv",
            classification="RESTRICTED",
            doc_checksum=VALID_CHECKSUM,
            extract_line_items=False,
            job_repo=mock_job_repo,
            line_item_repo=mock_line_item_repo,
        )

        mock_line_item_repo.create_many.assert_not_called()

    @pytest.mark.anyio
    async def test_no_repos_still_works(self) -> None:
        """Without repos, extraction still runs (just no DB persistence)."""
        status = await run_extraction(
            job_id=uuid7(),
            doc_id=uuid7(),
            workspace_id=uuid7(),
            document_bytes=_make_csv_bytes(),
            mime_type="text/csv",
            filename="boq.csv",
            classification="RESTRICTED",
            doc_checksum=VALID_CHECKSUM,
        )

        assert status == "COMPLETED"


class TestRunExtractionPdfRouting:
    """Test that PDF extraction routes through the provider correctly."""

    @pytest.mark.anyio
    async def test_pdf_routes_to_local_pdf_for_restricted(self) -> None:
        """RESTRICTED PDFs should use local-pdf provider."""
        mock_job_repo = AsyncMock()
        doc_id = uuid7()
        graph = _make_mock_graph(doc_id)

        with patch(
            "src.ingestion.providers.local_pdf.LocalPdfProvider.extract",
            new_callable=AsyncMock,
            return_value=graph,
        ) as mock_extract:
            status = await run_extraction(
                job_id=uuid7(),
                doc_id=doc_id,
                workspace_id=uuid7(),
                document_bytes=b"fake-pdf-bytes",
                mime_type="application/pdf",
                filename="boq.pdf",
                classification="RESTRICTED",
                doc_checksum=VALID_CHECKSUM,
                extract_line_items=False,
                job_repo=mock_job_repo,
            )

        assert status == "COMPLETED"
        mock_extract.assert_called_once()


class TestRunExtractionErrorHandling:
    """Error handling in extraction orchestration."""

    @pytest.mark.anyio
    async def test_extraction_failure_returns_failed(self) -> None:
        mock_job_repo = AsyncMock()

        with patch(
            "src.ingestion.providers.local_pdf.LocalPdfProvider.extract",
            new_callable=AsyncMock,
            side_effect=RuntimeError("pdfplumber crashed"),
        ):
            status = await run_extraction(
                job_id=uuid7(),
                doc_id=uuid7(),
                workspace_id=uuid7(),
                document_bytes=b"bad-pdf",
                mime_type="application/pdf",
                filename="bad.pdf",
                classification="RESTRICTED",
                doc_checksum=VALID_CHECKSUM,
                extract_line_items=False,
                job_repo=mock_job_repo,
            )

        assert status == "FAILED"

    @pytest.mark.anyio
    async def test_failure_updates_job_with_error(self) -> None:
        mock_job_repo = AsyncMock()
        job_id = uuid7()

        with patch(
            "src.ingestion.providers.local_pdf.LocalPdfProvider.extract",
            new_callable=AsyncMock,
            side_effect=RuntimeError("pdfplumber crashed"),
        ):
            await run_extraction(
                job_id=job_id,
                doc_id=uuid7(),
                workspace_id=uuid7(),
                document_bytes=b"bad-pdf",
                mime_type="application/pdf",
                filename="bad.pdf",
                classification="RESTRICTED",
                doc_checksum=VALID_CHECKSUM,
                job_repo=mock_job_repo,
            )

        mock_job_repo.update_status.assert_called_with(
            job_id, "FAILED", error_message="pdfplumber crashed",
        )
