"""Tests for AzureDIProvider — S0-3.

Mocks the Azure Document Intelligence API to test response parsing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uuid_extensions import uuid7

from src.ingestion.providers.azure_di import AzureDIProvider
from src.ingestion.providers.base import ExtractionOptions
from src.models.document import DocumentGraph

VALID_CHECKSUM = "sha256:" + "a" * 64


def _options(**kwargs):
    defaults = {"doc_checksum": VALID_CHECKSUM}
    defaults.update(kwargs)
    return ExtractionOptions(**defaults)


def _make_azure_analyze_result(
    *,
    pages: list[dict] | None = None,
    tables: list[dict] | None = None,
    paragraphs: list[dict] | None = None,
) -> dict:
    """Build a mock Azure DI analyzeResult."""
    return {
        "pages": pages or [{"pageNumber": 1, "width": 8.5, "height": 11.0}],
        "tables": tables or [],
        "paragraphs": paragraphs or [],
    }


def _make_table(
    *,
    row_count: int = 2,
    col_count: int = 2,
    cells: list[dict] | None = None,
    page_number: int = 1,
) -> dict:
    """Build a mock Azure DI table."""
    if cells is None:
        cells = []
        for r in range(row_count):
            for c in range(col_count):
                cells.append({
                    "rowIndex": r,
                    "columnIndex": c,
                    "content": f"R{r}C{c}",
                    "confidence": 0.95,
                    "boundingRegions": [{
                        "pageNumber": page_number,
                        "polygon": [0.5, 0.5, 2.0, 0.5, 2.0, 2.0, 0.5, 2.0],
                    }],
                })
    return {
        "rowCount": row_count,
        "columnCount": col_count,
        "cells": cells,
        "boundingRegions": [{
            "pageNumber": page_number,
            "polygon": [0.0, 0.0, 8.5, 0.0, 8.5, 11.0, 0.0, 11.0],
        }],
    }


def _make_paragraph(text: str, page_number: int = 1) -> dict:
    return {
        "content": text,
        "role": "text",
        "boundingRegions": [{
            "pageNumber": page_number,
            "polygon": [0.5, 0.5, 4.0, 0.5, 4.0, 1.0, 0.5, 1.0],
        }],
    }


async def _mock_extract(
    provider: AzureDIProvider,
    analyze_result: dict,
    doc_id=None,
) -> DocumentGraph:
    """Run extraction with mocked HTTP calls."""
    if doc_id is None:
        doc_id = uuid7()

    # Mock HTTP responses
    submit_response = MagicMock()
    submit_response.raise_for_status = MagicMock()
    submit_response.headers = {"Operation-Location": "https://example.com/result/123"}

    poll_response = MagicMock()
    poll_response.raise_for_status = MagicMock()
    poll_response.json.return_value = {
        "status": "succeeded",
        "analyzeResult": analyze_result,
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = submit_response
    mock_client.get.return_value = poll_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.ingestion.providers.azure_di.httpx.AsyncClient", return_value=mock_client):
        return await provider.extract(
            b"fake-pdf", "application/pdf", doc_id, _options(),
        )


# ===================================================================
# Table parsing
# ===================================================================


class TestAzureDITableParsing:
    """Parse Azure DI table response into ExtractedTable."""

    @pytest.mark.anyio
    async def test_extract_returns_document_graph(self) -> None:
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="test-key")
        result = _make_azure_analyze_result(
            tables=[_make_table(row_count=2, col_count=3)],
        )

        graph = await _mock_extract(provider, result)
        assert isinstance(graph, DocumentGraph)

    @pytest.mark.anyio
    async def test_table_cells_count(self) -> None:
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="test-key")
        result = _make_azure_analyze_result(
            tables=[_make_table(row_count=3, col_count=2)],
        )

        graph = await _mock_extract(provider, result)
        assert len(graph.pages) == 1
        assert len(graph.pages[0].tables) == 1
        assert len(graph.pages[0].tables[0].cells) == 6

    @pytest.mark.anyio
    async def test_cell_text_from_content(self) -> None:
        cells = [
            {
                "rowIndex": 0, "columnIndex": 0,
                "content": "Steel Beams",
                "confidence": 0.98,
                "boundingRegions": [{"pageNumber": 1, "polygon": [0, 0, 1, 0, 1, 1, 0, 1]}],
            },
        ]
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="test-key")
        result = _make_azure_analyze_result(
            tables=[_make_table(row_count=1, col_count=1, cells=cells)],
        )

        graph = await _mock_extract(provider, result)
        assert graph.pages[0].tables[0].cells[0].text == "Steel Beams"

    @pytest.mark.anyio
    async def test_cell_confidence_preserved(self) -> None:
        cells = [
            {
                "rowIndex": 0, "columnIndex": 0,
                "content": "Test",
                "confidence": 0.72,
                "boundingRegions": [{"pageNumber": 1, "polygon": [0, 0, 1, 0, 1, 1, 0, 1]}],
            },
        ]
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="test-key")
        result = _make_azure_analyze_result(
            tables=[_make_table(row_count=1, col_count=1, cells=cells)],
        )

        graph = await _mock_extract(provider, result)
        assert graph.pages[0].tables[0].cells[0].confidence == 0.72

    @pytest.mark.anyio
    async def test_bounding_boxes_normalized(self) -> None:
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="test-key")
        result = _make_azure_analyze_result(
            tables=[_make_table(row_count=2, col_count=2)],
        )

        graph = await _mock_extract(provider, result)
        for cell in graph.pages[0].tables[0].cells:
            assert 0.0 <= cell.bbox.x0 <= 1.0
            assert 0.0 <= cell.bbox.y0 <= 1.0


# ===================================================================
# Paragraph / text extraction
# ===================================================================


class TestAzureDIParagraphs:
    """Parse Azure DI paragraphs into TextBlocks."""

    @pytest.mark.anyio
    async def test_paragraph_text_extracted(self) -> None:
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="test-key")
        result = _make_azure_analyze_result(
            paragraphs=[_make_paragraph("This is a test paragraph.")],
        )

        graph = await _mock_extract(provider, result)
        assert len(graph.pages[0].blocks) == 1
        assert graph.pages[0].blocks[0].text == "This is a test paragraph."

    @pytest.mark.anyio
    async def test_empty_paragraph_skipped(self) -> None:
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="test-key")
        result = _make_azure_analyze_result(
            paragraphs=[_make_paragraph("")],
        )

        graph = await _mock_extract(provider, result)
        assert len(graph.pages[0].blocks) == 0


# ===================================================================
# Multi-page
# ===================================================================


class TestAzureDIMultiPage:
    """Multi-page Azure DI results."""

    @pytest.mark.anyio
    async def test_multi_page_tables(self) -> None:
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="test-key")
        result = _make_azure_analyze_result(
            pages=[
                {"pageNumber": 1, "width": 8.5, "height": 11.0},
                {"pageNumber": 2, "width": 8.5, "height": 11.0},
            ],
            tables=[
                _make_table(row_count=2, col_count=2, page_number=1),
                _make_table(row_count=3, col_count=2, page_number=2),
            ],
        )

        graph = await _mock_extract(provider, result)
        assert len(graph.pages) == 2


# ===================================================================
# Metadata
# ===================================================================


class TestAzureDIMetadata:
    """Provider metadata."""

    def test_name(self) -> None:
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="key")
        assert provider.name == "azure-di"

    def test_supported_mime_types(self) -> None:
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="key")
        assert "application/pdf" in provider.supported_mime_types()

    @pytest.mark.anyio
    async def test_extraction_metadata_engine(self) -> None:
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="key")
        result = _make_azure_analyze_result()

        graph = await _mock_extract(provider, result)
        assert graph.extraction_metadata.engine == "azure-di"


# ===================================================================
# Error handling
# ===================================================================


class TestAzureDIErrors:
    """Error scenarios."""

    @pytest.mark.anyio
    async def test_failed_analysis_raises(self) -> None:
        provider = AzureDIProvider(endpoint="https://test.cognitiveservices.azure.com", key="key")

        submit_response = MagicMock()
        submit_response.raise_for_status = MagicMock()
        submit_response.headers = {"Operation-Location": "https://example.com/result/123"}

        poll_response = MagicMock()
        poll_response.raise_for_status = MagicMock()
        poll_response.json.return_value = {
            "status": "failed",
            "error": {"message": "Document could not be processed"},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = poll_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.ingestion.providers.azure_di.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Azure DI analysis failed"):
                await provider.extract(b"bad-pdf", "application/pdf", uuid7(), _options())
