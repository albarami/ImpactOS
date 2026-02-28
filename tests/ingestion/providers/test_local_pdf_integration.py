"""Integration tests for LocalPdfProvider — real PDF bytes, real pdfplumber.

No mocks. Generates a real PDF using fpdf2, feeds it to LocalPdfProvider,
and verifies the DocumentGraph output.
"""

import pytest
from uuid_extensions import uuid7

from src.ingestion.providers.base import ExtractionOptions
from src.ingestion.providers.local_pdf import LocalPdfProvider

VALID_CHECKSUM = "sha256:" + "a" * 64


def _options() -> ExtractionOptions:
    return ExtractionOptions(doc_checksum=VALID_CHECKSUM, language_hint="en")


@pytest.fixture()
def sample_boq_pdf_bytes() -> bytes:
    """Generate a real PDF with a BoQ table using fpdf2.

    Uses explicit cell borders and a core font (Helvetica)
    to ensure pdfplumber reliably detects table structure.
    """
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)

    headers = ["Description", "Qty", "Unit", "Unit Price", "Total"]
    rows = [
        ["Structural Steel", "5000", "tonnes", "3500", "17500000"],
        ["Concrete Supply", "20000", "m3", "450", "9000000"],
        ["Electrical Works", "1", "LS", "5000000", "5000000"],
    ]

    col_widths = [50, 25, 25, 35, 35]
    row_height = 10

    # Draw header with borders
    pdf.set_font("Helvetica", "B", 10)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], row_height, h, border=1)
    pdf.ln()

    # Draw data rows with borders
    pdf.set_font("Helvetica", size=10)
    for row in rows:
        for i, val in enumerate(row):
            pdf.cell(col_widths[i], row_height, val, border=1)
        pdf.ln()

    return pdf.output()  # returns bytes


class TestLocalPdfIntegration:
    """Real PDF bytes → real pdfplumber → verify DocumentGraph output."""

    @pytest.mark.anyio
    async def test_extract_real_pdf_produces_document_graph(
        self, sample_boq_pdf_bytes: bytes,
    ) -> None:
        """Full pipeline: real PDF → LocalPdfProvider → DocumentGraph with table."""
        provider = LocalPdfProvider()
        graph = await provider.extract(
            sample_boq_pdf_bytes, "application/pdf", uuid7(), _options(),
        )
        # Exactly 1 page
        assert len(graph.pages) == 1
        # At least 1 table detected
        assert len(graph.pages[0].tables) >= 1
        # Table has cells (header + 3 data rows = 4 rows, or 3 if header excluded)
        table = graph.pages[0].tables[0]
        assert len(table.cells) >= 3  # at minimum the data rows

    @pytest.mark.anyio
    async def test_bounding_boxes_normalized(
        self, sample_boq_pdf_bytes: bytes,
    ) -> None:
        """All bounding boxes must be in [0, 1] range (normalized to page dimensions)."""
        provider = LocalPdfProvider()
        graph = await provider.extract(
            sample_boq_pdf_bytes, "application/pdf", uuid7(), _options(),
        )
        for page in graph.pages:
            for table in page.tables:
                bbox = table.bbox
                assert 0.0 <= bbox.x0 <= 1.0
                assert 0.0 <= bbox.y0 <= 1.0
                assert 0.0 <= bbox.x1 <= 1.0
                assert 0.0 <= bbox.y1 <= 1.0
                for cell in table.cells:
                    if cell.bbox:
                        assert 0.0 <= cell.bbox.x0 <= 1.0
                        assert 0.0 <= cell.bbox.y0 <= 1.0
                        assert 0.0 <= cell.bbox.x1 <= 1.0
                        assert 0.0 <= cell.bbox.y1 <= 1.0

    @pytest.mark.anyio
    async def test_cell_text_contains_expected_values(
        self, sample_boq_pdf_bytes: bytes,
    ) -> None:
        """Key text values from the generated table must appear in extracted cells."""
        provider = LocalPdfProvider()
        graph = await provider.extract(
            sample_boq_pdf_bytes, "application/pdf", uuid7(), _options(),
        )
        all_cell_text = " ".join(
            cell.text
            for page in graph.pages
            for table in page.tables
            for cell in table.cells
            if cell.text
        )
        # At least some key values should appear
        assert "Steel" in all_cell_text or "5000" in all_cell_text or "17500000" in all_cell_text
