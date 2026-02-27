"""LocalPdfProvider — pdfplumber + camelot for PDF extraction.

Uses pdfplumber for digital PDFs with table detection and text extraction.
Falls back to camelot for complex table layouts when pdfplumber finds no tables.
For scanned/image PDFs, attempts Tesseract OCR with Arabic language support.
"""

import asyncio
import io
import logging
from uuid import UUID

import pdfplumber as _pdfplumber_lib

from src.ingestion.providers.base import ExtractionOptions, ExtractionProvider
from src.models.common import utc_now
from src.models.document import (
    DocumentGraph,
    ExtractionMetadata,
    ExtractedTable,
    PageBlock,
    TableCell,
    TextBlock,
)
from src.models.governance import BoundingBox

logger = logging.getLogger(__name__)

_PDF_MIMES = frozenset({"application/pdf"})


class LocalPdfProvider(ExtractionProvider):
    """Extract tables and text from PDFs using pdfplumber.

    Fallback chain:
    1. pdfplumber (digital PDFs with table detection)
    2. camelot (complex table layouts, lattice mode)
    3. Tesseract OCR (scanned/image PDFs, Arabic support)
    """

    @property
    def name(self) -> str:
        return "local-pdf"

    async def extract(
        self,
        document_bytes: bytes,
        mime_type: str,
        doc_id: UUID,
        options: ExtractionOptions,
    ) -> DocumentGraph:
        return await asyncio.to_thread(
            self._extract_sync, document_bytes, doc_id, options,
        )

    def supported_mime_types(self) -> frozenset[str]:
        return _PDF_MIMES

    # ------------------------------------------------------------------
    # Synchronous extraction (runs in thread via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _extract_sync(
        self,
        document_bytes: bytes,
        doc_id: UUID,
        options: ExtractionOptions,
    ) -> DocumentGraph:
        errors: list[str] = []
        pages: list[PageBlock] = []

        pdf = _pdfplumber_lib.open(io.BytesIO(document_bytes))
        try:
            for page_num, page in enumerate(pdf.pages):
                page_width = float(page.width)
                page_height = float(page.height)

                tables = self._extract_tables(page, page_num, page_width, page_height)
                text_blocks = self._extract_text_blocks(page, page_width, page_height)

                pages.append(PageBlock(
                    page_number=page_num,
                    blocks=text_blocks,
                    tables=tables,
                ))
        finally:
            pdf.close()

        # Fallback: camelot for complex tables
        if not any(p.tables for p in pages):
            camelot_pages = self._try_camelot_fallback(document_bytes)
            if camelot_pages:
                # Merge camelot tables into existing pages
                for cp in camelot_pages:
                    existing = next(
                        (p for p in pages if p.page_number == cp.page_number), None
                    )
                    if existing:
                        existing.tables.extend(cp.tables)
                    else:
                        pages.append(cp)
                errors.append("pdfplumber found no tables; used camelot fallback")

        # Fallback: OCR for scanned PDFs
        has_content = any(p.tables or p.blocks for p in pages)
        if not has_content:
            ocr_pages, ocr_errors = self._try_ocr_fallback(
                document_bytes, options.language_hint,
            )
            if ocr_pages:
                pages = ocr_pages
            errors.extend(ocr_errors)

        return DocumentGraph(
            document_id=doc_id,
            pages=pages,
            extraction_metadata=ExtractionMetadata(
                engine="pdfplumber",
                engine_version="1.0.0",
                completed_at=utc_now(),
                errors=errors,
            ),
        )

    # ------------------------------------------------------------------
    # Table extraction via pdfplumber
    # ------------------------------------------------------------------

    def _extract_tables(
        self,
        page: object,
        page_num: int,
        page_width: float,
        page_height: float,
    ) -> list[ExtractedTable]:
        tables: list[ExtractedTable] = []
        found = page.find_tables()  # type: ignore[union-attr]

        for table_idx, table_obj in enumerate(found):
            raw_data = table_obj.extract()
            if not raw_data:
                continue

            # Normalize table bbox to [0,1]
            t_bbox = table_obj.bbox  # (x0, y0, x1, y1) in PDF points
            table_bbox = BoundingBox(
                x0=max(0.0, min(t_bbox[0] / page_width, 1.0)),
                y0=max(0.0, min(t_bbox[1] / page_height, 1.0)),
                x1=max(0.0, min(t_bbox[2] / page_width, 1.0)),
                y1=max(0.0, min(t_bbox[3] / page_height, 1.0)),
            )

            cells = self._build_cells(raw_data, table_bbox)

            tables.append(ExtractedTable(
                table_id=f"pdf_p{page_num}_t{table_idx}",
                page_number=page_num,
                bbox=table_bbox,
                cells=cells,
            ))

        return tables

    @staticmethod
    def _build_cells(
        raw_data: list[list[str | None]],
        table_bbox: BoundingBox,
    ) -> list[TableCell]:
        """Build TableCell list with bboxes proportional within table area."""
        cells: list[TableCell] = []
        num_rows = len(raw_data)
        num_cols = max(len(row) for row in raw_data) if raw_data else 0

        if num_rows == 0 or num_cols == 0:
            return cells

        row_height = (table_bbox.y1 - table_bbox.y0) / num_rows
        col_width = (table_bbox.x1 - table_bbox.x0) / num_cols

        for r_idx, row in enumerate(raw_data):
            for c_idx, value in enumerate(row):
                cell_x0 = table_bbox.x0 + c_idx * col_width
                cell_y0 = table_bbox.y0 + r_idx * row_height
                cell_x1 = min(cell_x0 + col_width, 1.0)
                cell_y1 = min(cell_y0 + row_height, 1.0)

                cells.append(TableCell(
                    row=r_idx,
                    col=c_idx,
                    text=value or "",
                    bbox=BoundingBox(
                        x0=cell_x0, y0=cell_y0,
                        x1=cell_x1, y1=cell_y1,
                    ),
                    confidence=0.85,
                ))

        return cells

    # ------------------------------------------------------------------
    # Text block extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text_blocks(
        page: object,
        page_width: float,
        page_height: float,
    ) -> list[TextBlock]:
        text = page.extract_text() or ""  # type: ignore[union-attr]
        if not text.strip():
            return []

        return [TextBlock(
            text=text,
            bbox=BoundingBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
            block_type="text",
        )]

    # ------------------------------------------------------------------
    # Camelot fallback for complex table layouts
    # ------------------------------------------------------------------

    @staticmethod
    def _try_camelot_fallback(
        document_bytes: bytes,
    ) -> list[PageBlock] | None:
        try:
            import camelot
        except ImportError:
            logger.warning("camelot-py not installed; skipping camelot fallback")
            return None

        try:
            import tempfile
            import os

            fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            try:
                os.write(fd, document_bytes)
                os.close(fd)
                tables = camelot.read_pdf(tmp_path, pages="all", flavor="lattice")
            finally:
                os.unlink(tmp_path)

            if not tables or len(tables) == 0:
                return None

            pages: list[PageBlock] = []
            for t_idx, table in enumerate(tables):
                page_num = table.page - 1  # camelot uses 1-indexed pages
                df = table.df
                rows = df.values.tolist()

                num_rows = len(rows)
                num_cols = len(rows[0]) if rows else 0
                cells: list[TableCell] = []

                if num_rows > 0 and num_cols > 0:
                    row_h = 1.0 / num_rows
                    col_w = 1.0 / num_cols
                    for r_idx, row in enumerate(rows):
                        for c_idx, val in enumerate(row):
                            cells.append(TableCell(
                                row=r_idx,
                                col=c_idx,
                                text=str(val) if val else "",
                                bbox=BoundingBox(
                                    x0=c_idx * col_w,
                                    y0=r_idx * row_h,
                                    x1=min((c_idx + 1) * col_w, 1.0),
                                    y1=min((r_idx + 1) * row_h, 1.0),
                                ),
                                confidence=0.80,
                            ))

                ext_table = ExtractedTable(
                    table_id=f"camelot_p{page_num}_t{t_idx}",
                    page_number=page_num,
                    bbox=BoundingBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
                    cells=cells,
                )

                existing = next((p for p in pages if p.page_number == page_num), None)
                if existing:
                    existing.tables.append(ext_table)
                else:
                    pages.append(PageBlock(
                        page_number=page_num,
                        blocks=[],
                        tables=[ext_table],
                    ))

            return pages if pages else None

        except Exception as exc:
            logger.warning("camelot fallback failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # OCR fallback for scanned/image PDFs (Arabic support)
    # ------------------------------------------------------------------

    @staticmethod
    def _try_ocr_fallback(
        document_bytes: bytes,
        language_hint: str,
    ) -> tuple[list[PageBlock], list[str]]:
        """Attempt Tesseract OCR on scanned PDF pages."""
        errors: list[str] = []

        try:
            import pytesseract  # noqa: F401
        except ImportError:
            errors.append(
                "pytesseract not installed; OCR fallback unavailable. "
                "Install with: pip install pytesseract"
            )
            return [], errors

        try:
            lang = "eng"
            if language_hint == "ar":
                lang = "ara+eng"
            elif language_hint == "bilingual":
                lang = "ara+eng"

            pdf = _pdfplumber_lib.open(io.BytesIO(document_bytes))
            pages: list[PageBlock] = []

            for page_num, page in enumerate(pdf.pages):
                img = page.to_image(resolution=300)
                pil_image = img.original

                text = pytesseract.image_to_string(pil_image, lang=lang)
                if text.strip():
                    pages.append(PageBlock(
                        page_number=page_num,
                        blocks=[TextBlock(
                            text=text,
                            bbox=BoundingBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
                            block_type="ocr_text",
                        )],
                        tables=[],
                    ))

            pdf.close()
            return pages, errors

        except Exception as exc:
            errors.append(f"OCR fallback failed: {exc}")
            return [], errors
