"""Tests for FastAPI document endpoints (MVP-2 Section 6.2.5).

Covers: POST upload, POST extract (async job), GET job status,
GET extracted line items.
"""

import csv
import io

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


def _make_csv_content() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows([
        ["Description", "Quantity", "Unit", "Unit Price", "Total"],
        ["Structural Steel", "5000", "tonnes", "3500", "17500000"],
        ["Concrete Works", "20000", "m3", "450", "9000000"],
    ])
    return buf.getvalue().encode("utf-8")


# ===================================================================
# POST /v1/workspaces/{workspace_id}/documents (upload)
# ===================================================================


class TestDocumentUploadEndpoint:
    """POST upload stores document and returns doc metadata."""

    @pytest.mark.anyio
    async def test_upload_returns_201(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        response = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        assert response.status_code == 201

    @pytest.mark.anyio
    async def test_upload_returns_doc_id(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        response = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        data = response.json()
        assert "doc_id" in data
        assert "hash_sha256" in data
        assert data["status"] == "stored"

    @pytest.mark.anyio
    async def test_upload_empty_file_returns_422(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        response = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("empty.csv", b"", "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        assert response.status_code == 422


# ===================================================================
# POST /v1/workspaces/{workspace_id}/documents/{doc_id}/extract
# ===================================================================


class TestExtractionEndpoint:
    """POST extract triggers async extraction job."""

    @pytest.mark.anyio
    async def test_extract_returns_202(self, client: AsyncClient) -> None:
        # First upload a document
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        upload_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        doc_id = upload_resp.json()["doc_id"]

        # Trigger extraction
        response = await client.post(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True, "language_hint": "en"},
        )
        assert response.status_code == 202

    @pytest.mark.anyio
    async def test_extract_returns_job_id(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        upload_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        doc_id = upload_resp.json()["doc_id"]

        response = await client.post(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True},
        )
        data = response.json()
        assert "job_id" in data
        assert data["status"] in ("QUEUED", "COMPLETED")

    @pytest.mark.anyio
    async def test_extract_nonexistent_doc_returns_404(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        doc_id = str(uuid7())
        response = await client.post(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True},
        )
        assert response.status_code == 404


# ===================================================================
# GET /v1/workspaces/{workspace_id}/jobs/{job_id}
# ===================================================================


class TestJobStatusEndpoint:
    """GET job status returns current extraction job state."""

    @pytest.mark.anyio
    async def test_job_status_returns_200(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        # Upload + extract
        upload_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        doc_id = upload_resp.json()["doc_id"]
        extract_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True},
        )
        job_id = extract_resp.json()["job_id"]

        # Poll status
        response = await client.get(
            f"/v1/workspaces/{workspace_id}/jobs/{job_id}",
        )
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_job_status_has_fields(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        upload_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        doc_id = upload_resp.json()["doc_id"]
        extract_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True},
        )
        job_id = extract_resp.json()["job_id"]

        response = await client.get(
            f"/v1/workspaces/{workspace_id}/jobs/{job_id}",
        )
        data = response.json()
        assert "job_id" in data
        assert "status" in data
        assert "doc_id" in data

    @pytest.mark.anyio
    async def test_nonexistent_job_returns_404(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        job_id = str(uuid7())
        response = await client.get(
            f"/v1/workspaces/{workspace_id}/jobs/{job_id}",
        )
        assert response.status_code == 404


# ===================================================================
# GET /v1/workspaces/{workspace_id}/documents/{doc_id}/line-items
# ===================================================================


class TestLineItemsEndpoint:
    """GET extracted line items returns BoQLineItem list."""

    @pytest.mark.anyio
    async def test_line_items_after_extraction(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        # Upload + extract
        upload_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        doc_id = upload_resp.json()["doc_id"]

        # Extract
        await client.post(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True},
        )

        # Get line items
        response = await client.get(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/line-items",
        )
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_line_items_has_items(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        upload_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        doc_id = upload_resp.json()["doc_id"]

        await client.post(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True},
        )

        response = await client.get(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/line-items",
        )
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 2  # 2 data rows in CSV
        assert data["items"][0]["description"] == "Structural Steel"

    @pytest.mark.anyio
    async def test_line_items_have_evidence_refs(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        upload_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        doc_id = upload_resp.json()["doc_id"]

        await client.post(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True},
        )

        response = await client.get(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/line-items",
        )
        data = response.json()
        for item in data["items"]:
            assert len(item["evidence_snippet_ids"]) >= 1

    @pytest.mark.anyio
    async def test_line_items_no_extraction_returns_empty(self, client: AsyncClient) -> None:
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        upload_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        doc_id = upload_resp.json()["doc_id"]

        response = await client.get(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}/line-items",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
