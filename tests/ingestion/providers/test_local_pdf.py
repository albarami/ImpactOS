"""Tests for LocalPdfProvider — S0-3.

Uses mocked pdfplumber to test transformation logic without real PDFs.
"""

from unittest.mock import MagicMock, patch

import pytest
from uuid_extensions import uuid7

from src.ingestion.providers.base import ExtractionOptions
from src.ingestion.providers.local_pdf import LocalPdfProvider
from src.models.document import DocumentGraph

VALID_CHECKSUM = "sha256:" + "a" * 64


def _options(**kwargs):
    defaults = {"doc_checksum": VALID_CHECKSUM, "language_hint": "en"}
    defaults.update(kwargs)
    return ExtractionOptions(**defaults)


def _mock_pdfplumber_page(
    *,
    width: float = 612.0,
    height: float = 792.0,
    tables: list[dict] | None = None,
    text: str = "",
):
    """Create a mock pdfplumber page.

    Args:
        width: Page width in PDF points.
        height: Page height in PDF points.
        tables: List of dicts with 'bbox' and 'data' keys.
        text: Plain text content on the page.
    """
    page = MagicMock()
    page.width = width
    page.height = height
    page.extract_text.return_value = text

    mock_tables = []
    if tables:
        for t in tables:
            mock_table = MagicMock()
            mock_table.bbox = t["bbox"]
            mock_table.extract.return_value = t["data"]
            mock_tables.append(mock_table)

    page.find_tables.return_value = mock_tables
    page.extract_words.return_value = []
    return page


def _mock_pdf(*pages):
    """Create a mock pdfplumber PDF."""
    pdf = MagicMock()
    pdf.pages = list(pages)
    pdf.close = MagicMock()
    return pdf


# ===================================================================
# Table extraction
# ===================================================================


class TestLocalPdfTableExtraction:
    """Table extraction from digital PDFs."""

    @pytest.mark.anyio
    async def test_extract_returns_document_graph(self) -> None:
        page = _mock_pdfplumber_page(
            tables=[{
                "bbox": (50.0, 100.0, 500.0, 700.0),
                "data": [
                    ["Description", "Qty", "Total"],
                    ["Steel", "5000", "17500000"],
                ],
            }],
        )
        pdf = _mock_pdf(page)

        with patch("src.ingestion.providers.local_pdf._pdfplumber_lib") as mock_lib:
            mock_lib.open.return_value = pdf
            provider = LocalPdfProvider()
            graph = await provider.extract(b"fake-pdf", "application/pdf", uuid7(), _options())

        assert isinstance(graph, DocumentGraph)

    @pytest.mark.anyio
    async def test_single_table_produces_cells(self) -> None:
        page = _mock_pdfplumber_page(
            tables=[{
                "bbox": (0.0, 0.0, 612.0, 792.0),
                "data": [
                    ["Description", "Qty"],
                    ["Steel", "5000"],
                    ["Concrete", "20000"],
                ],
            }],
        )
        pdf = _mock_pdf(page)

        with patch("src.ingestion.providers.local_pdf._pdfplumber_lib") as mock_lib:
            mock_lib.open.return_value = pdf
            provider = LocalPdfProvider()
            graph = await provider.extract(b"fake-pdf", "application/pdf", uuid7(), _options())

        assert len(graph.pages) == 1
        assert len(graph.pages[0].tables) == 1
        table = graph.pages[0].tables[0]
        # 3 rows x 2 cols = 6 cells
        assert len(table.cells) == 6

    @pytest.mark.anyio
    async def test_cell_text_matches_source(self) -> None:
        page = _mock_pdfplumber_page(
            tables=[{
                "bbox": (0.0, 0.0, 612.0, 792.0),
                "data": [
                    ["Description", "Qty"],
                    ["Structural Steel", "5000"],
                ],
            }],
        )
        pdf = _mock_pdf(page)

        with patch("src.ingestion.providers.local_pdf._pdfplumber_lib") as mock_lib:
            mock_lib.open.return_value = pdf
            provider = LocalPdfProvider()
            graph = await provider.extract(b"fake-pdf", "application/pdf", uuid7(), _options())

        cells = graph.pages[0].tables[0].cells
        cell = next(c for c in cells if c.row == 1 and c.col == 0)
        assert cell.text == "Structural Steel"

    @pytest.mark.anyio
    async def test_bounding_boxes_normalized(self) -> None:
        """All bounding boxes should be in [0, 1] range."""
        page = _mock_pdfplumber_page(
            tables=[{
                "bbox": (50.0, 100.0, 500.0, 700.0),
                "data": [
                    ["A", "B"],
                    ["C", "D"],
                ],
            }],
        )
        pdf = _mock_pdf(page)

        with patch("src.ingestion.providers.local_pdf._pdfplumber_lib") as mock_lib:
            mock_lib.open.return_value = pdf
            provider = LocalPdfProvider()
            graph = await provider.extract(b"fake-pdf", "application/pdf", uuid7(), _options())

        for cell in graph.pages[0].tables[0].cells:
            assert 0.0 <= cell.bbox.x0 <= 1.0
            assert 0.0 <= cell.bbox.y0 <= 1.0
            assert 0.0 <= cell.bbox.x1 <= 1.0
            assert 0.0 <= cell.bbox.y1 <= 1.0

    @pytest.mark.anyio
    async def test_pdf_confidence_below_one(self) -> None:
        """PDF extraction confidence should be < 1.0 (not exact like CSV)."""
        page = _mock_pdfplumber_page(
            tables=[{
                "bbox": (0.0, 0.0, 612.0, 792.0),
                "data": [["A"], ["B"]],
            }],
        )
        pdf = _mock_pdf(page)

        with patch("src.ingestion.providers.local_pdf._pdfplumber_lib") as mock_lib:
            mock_lib.open.return_value = pdf
            provider = LocalPdfProvider()
            graph = await provider.extract(b"fake-pdf", "application/pdf", uuid7(), _options())

        for cell in graph.pages[0].tables[0].cells:
            assert cell.confidence < 1.0


class TestLocalPdfMultiPage:
    """Multi-page PDF extraction."""

    @pytest.mark.anyio
    async def test_multi_page_produces_multiple_pages(self) -> None:
        page1 = _mock_pdfplumber_page(
            tables=[{
                "bbox": (0.0, 0.0, 612.0, 792.0),
                "data": [["A"], ["B"]],
            }],
        )
        page2 = _mock_pdfplumber_page(
            tables=[{
                "bbox": (0.0, 0.0, 612.0, 792.0),
                "data": [["C"], ["D"]],
            }],
        )
        pdf = _mock_pdf(page1, page2)

        with patch("src.ingestion.providers.local_pdf._pdfplumber_lib") as mock_lib:
            mock_lib.open.return_value = pdf
            provider = LocalPdfProvider()
            graph = await provider.extract(b"fake-pdf", "application/pdf", uuid7(), _options())

        assert len(graph.pages) == 2
        assert graph.pages[0].page_number == 0
        assert graph.pages[1].page_number == 1


class TestLocalPdfTextBlocks:
    """Text block extraction."""

    @pytest.mark.anyio
    async def test_extracts_page_text(self) -> None:
        page = _mock_pdfplumber_page(text="Sample paragraph text")
        pdf = _mock_pdf(page)

        with patch("src.ingestion.providers.local_pdf._pdfplumber_lib") as mock_lib:
            mock_lib.open.return_value = pdf
            provider = LocalPdfProvider()
            graph = await provider.extract(b"fake-pdf", "application/pdf", uuid7(), _options())

        assert len(graph.pages[0].blocks) == 1
        assert graph.pages[0].blocks[0].text == "Sample paragraph text"

    @pytest.mark.anyio
    async def test_empty_text_produces_no_blocks(self) -> None:
        page = _mock_pdfplumber_page(text="")
        pdf = _mock_pdf(page)

        with patch("src.ingestion.providers.local_pdf._pdfplumber_lib") as mock_lib:
            mock_lib.open.return_value = pdf
            provider = LocalPdfProvider()
            graph = await provider.extract(b"fake-pdf", "application/pdf", uuid7(), _options())

        assert len(graph.pages[0].blocks) == 0


class TestLocalPdfNoneValues:
    """Handle None values in table cells (pdfplumber returns None for empty cells)."""

    @pytest.mark.anyio
    async def test_none_cell_becomes_empty_string(self) -> None:
        page = _mock_pdfplumber_page(
            tables=[{
                "bbox": (0.0, 0.0, 612.0, 792.0),
                "data": [["Header", None], ["Value", None]],
            }],
        )
        pdf = _mock_pdf(page)

        with patch("src.ingestion.providers.local_pdf._pdfplumber_lib") as mock_lib:
            mock_lib.open.return_value = pdf
            provider = LocalPdfProvider()
            graph = await provider.extract(b"fake-pdf", "application/pdf", uuid7(), _options())

        cells = graph.pages[0].tables[0].cells
        none_cell = next(c for c in cells if c.row == 0 and c.col == 1)
        assert none_cell.text == ""


class TestLocalPdfMetadata:
    """Provider metadata."""

    def test_name(self) -> None:
        assert LocalPdfProvider().name == "local-pdf"

    def test_supported_mime_types(self) -> None:
        mimes = LocalPdfProvider().supported_mime_types()
        assert "application/pdf" in mimes

    @pytest.mark.anyio
    async def test_extraction_metadata_engine(self) -> None:
        page = _mock_pdfplumber_page(text="Some text")
        pdf = _mock_pdf(page)

        with patch("src.ingestion.providers.local_pdf._pdfplumber_lib") as mock_lib:
            mock_lib.open.return_value = pdf
            provider = LocalPdfProvider()
            graph = await provider.extract(b"fake-pdf", "application/pdf", uuid7(), _options())

        assert graph.extraction_metadata.engine == "pdfplumber"


class TestLocalPdfOCRFallback:
    """OCR fallback when pytesseract is not available."""

    @pytest.mark.anyio
    async def test_no_content_logs_ocr_unavailable(self) -> None:
        """When no tables or text found and pytesseract unavailable, errors list explains."""
        page = _mock_pdfplumber_page(tables=[], text="")
        pdf = _mock_pdf(page)

        with patch("src.ingestion.providers.local_pdf._pdfplumber_lib") as mock_lib:
            mock_lib.open.return_value = pdf
            # Ensure pytesseract import fails
            with patch.dict("sys.modules", {"pytesseract": None}):
                provider = LocalPdfProvider()
                graph = await provider.extract(
                    b"fake-pdf", "application/pdf", uuid7(), _options(),
                )

        assert any("pytesseract" in e for e in graph.extraction_metadata.errors)
