"""AzureDIProvider — Azure Document Intelligence (layout model).

Calls Azure DI for layout analysis with native Arabic OCR support.
Parses response into DocumentGraph with table cells and bounding boxes.
Falls back to LocalPdfProvider if Azure DI is unavailable.
"""

import asyncio
import logging
from uuid import UUID

import httpx

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

# Azure DI API version
_API_VERSION = "2024-11-30"
_POLL_INTERVAL_S = 2.0
_POLL_MAX_ATTEMPTS = 60


class AzureDIProvider(ExtractionProvider):
    """Azure Document Intelligence layout extraction.

    Supports Arabic text natively via Azure DI's built-in OCR.
    On failure, logs warning and raises so the router can fall back
    to LocalPdfProvider.
    """

    def __init__(self, endpoint: str, key: str) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._key = key

    @property
    def name(self) -> str:
        return "azure-di"

    async def extract(
        self,
        document_bytes: bytes,
        mime_type: str,
        doc_id: UUID,
        options: ExtractionOptions,
    ) -> DocumentGraph:
        analyze_url = (
            f"{self._endpoint}/documentintelligence/documentModels/"
            f"prebuilt-layout:analyze?api-version={_API_VERSION}"
        )

        headers = {
            "Ocp-Apim-Subscription-Key": self._key,
            "Content-Type": "application/pdf",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Submit analysis
            resp = await client.post(
                analyze_url,
                headers=headers,
                content=document_bytes,
            )
            resp.raise_for_status()

            operation_url = resp.headers.get("Operation-Location", "")
            if not operation_url:
                raise RuntimeError("Azure DI did not return Operation-Location header")

            # Poll for result
            result = await self._poll_result(client, operation_url)

        return self._parse_result(result, doc_id)

    def supported_mime_types(self) -> frozenset[str]:
        return _PDF_MIMES

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll_result(
        self,
        client: httpx.AsyncClient,
        operation_url: str,
    ) -> dict:
        """Poll Azure DI until analysis completes."""
        headers = {"Ocp-Apim-Subscription-Key": self._key}

        for _ in range(_POLL_MAX_ATTEMPTS):
            resp = await client.get(operation_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")

            if status == "succeeded":
                return data.get("analyzeResult", {})
            elif status == "failed":
                error_msg = data.get("error", {}).get("message", "Unknown error")
                raise RuntimeError(f"Azure DI analysis failed: {error_msg}")

            await asyncio.sleep(_POLL_INTERVAL_S)

        raise RuntimeError("Azure DI analysis timed out")

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_result(self, result: dict, doc_id: UUID) -> DocumentGraph:
        """Convert Azure DI analyzeResult to DocumentGraph."""
        pages_data = result.get("pages", [])
        tables_data = result.get("tables", [])
        paragraphs_data = result.get("paragraphs", [])

        # Build page dimensions lookup
        page_dims: dict[int, tuple[float, float]] = {}
        for p in pages_data:
            page_num = p.get("pageNumber", 1) - 1  # Azure uses 1-indexed
            page_dims[page_num] = (
                float(p.get("width", 1.0)),
                float(p.get("height", 1.0)),
            )

        # Group tables by page
        tables_by_page: dict[int, list[ExtractedTable]] = {}
        for t_idx, table in enumerate(tables_data):
            page_num = self._get_table_page(table)
            width, height = page_dims.get(page_num, (1.0, 1.0))
            ext_table = self._parse_table(table, t_idx, page_num, width, height)
            tables_by_page.setdefault(page_num, []).append(ext_table)

        # Group text blocks by page
        text_by_page: dict[int, list[TextBlock]] = {}
        for para in paragraphs_data:
            page_num = self._get_paragraph_page(para)
            width, height = page_dims.get(page_num, (1.0, 1.0))
            block = self._parse_paragraph(para, width, height)
            if block:
                text_by_page.setdefault(page_num, []).append(block)

        # Build pages
        all_page_nums = set(page_dims.keys()) | set(tables_by_page.keys()) | set(text_by_page.keys())
        pages: list[PageBlock] = []
        for pn in sorted(all_page_nums):
            pages.append(PageBlock(
                page_number=pn,
                blocks=text_by_page.get(pn, []),
                tables=tables_by_page.get(pn, []),
            ))

        return DocumentGraph(
            document_id=doc_id,
            pages=pages,
            extraction_metadata=ExtractionMetadata(
                engine="azure-di",
                engine_version=_API_VERSION,
                completed_at=utc_now(),
            ),
        )

    @staticmethod
    def _get_table_page(table: dict) -> int:
        """Extract 0-indexed page number from Azure DI table."""
        cells = table.get("cells", [])
        if cells:
            regions = cells[0].get("boundingRegions", [])
            if regions:
                return regions[0].get("pageNumber", 1) - 1
        return 0

    @staticmethod
    def _get_paragraph_page(para: dict) -> int:
        """Extract 0-indexed page number from Azure DI paragraph."""
        regions = para.get("boundingRegions", [])
        if regions:
            return regions[0].get("pageNumber", 1) - 1
        return 0

    def _parse_table(
        self,
        table: dict,
        table_idx: int,
        page_num: int,
        page_width: float,
        page_height: float,
    ) -> ExtractedTable:
        """Parse an Azure DI table into ExtractedTable."""
        row_count = table.get("rowCount", 0)
        col_count = table.get("columnCount", 0)

        cells: list[TableCell] = []
        for cell in table.get("cells", []):
            row_idx = cell.get("rowIndex", 0)
            col_idx = cell.get("columnIndex", 0)
            text = cell.get("content", "")
            confidence = cell.get("confidence", 0.9)

            bbox = self._extract_bbox(cell, page_width, page_height)

            cells.append(TableCell(
                row=row_idx,
                col=col_idx,
                text=text,
                bbox=bbox,
                confidence=confidence,
            ))

        # Table-level bbox from bounding regions
        table_bbox = self._extract_bbox(table, page_width, page_height)

        return ExtractedTable(
            table_id=f"azdi_p{page_num}_t{table_idx}",
            page_number=page_num,
            bbox=table_bbox,
            cells=cells,
        )

    @staticmethod
    def _extract_bbox(
        element: dict,
        page_width: float,
        page_height: float,
    ) -> BoundingBox:
        """Extract and normalize bounding box from Azure DI element."""
        regions = element.get("boundingRegions", [])
        if regions:
            polygon = regions[0].get("polygon", [])
            if len(polygon) >= 8:
                # polygon is [x0,y0, x1,y1, x2,y2, x3,y3]
                xs = [polygon[i] for i in range(0, 8, 2)]
                ys = [polygon[i] for i in range(1, 8, 2)]
                return BoundingBox(
                    x0=max(0.0, min(min(xs) / page_width, 1.0)),
                    y0=max(0.0, min(min(ys) / page_height, 1.0)),
                    x1=max(0.0, min(max(xs) / page_width, 1.0)),
                    y1=max(0.0, min(max(ys) / page_height, 1.0)),
                )
        return BoundingBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0)

    def _parse_paragraph(
        self,
        para: dict,
        page_width: float,
        page_height: float,
    ) -> TextBlock | None:
        """Parse an Azure DI paragraph into TextBlock."""
        text = para.get("content", "")
        if not text.strip():
            return None

        bbox = self._extract_bbox(para, page_width, page_height)
        role = para.get("role", "text")

        return TextBlock(
            text=text,
            bbox=bbox,
            block_type=role,
        )
