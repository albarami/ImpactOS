"""Tests for B-2 + B-3: Document list and document detail."""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


@pytest.fixture
def workspace_id() -> str:
    return str(uuid7())


@pytest.fixture
def other_workspace_id() -> str:
    return str(uuid7())


async def _upload_document(
    client: AsyncClient,
    workspace_id: str,
    *,
    filename: str = "test.pdf",
    doc_type: str = "BOQ",
    source_type: str = "CLIENT",
    classification: str = "CONFIDENTIAL",
) -> str:
    """Upload a document via the existing POST endpoint and return doc_id."""
    import io

    resp = await client.post(
        f"/v1/workspaces/{workspace_id}/documents",
        files={"file": (filename, io.BytesIO(b"fake pdf content"), "application/pdf")},
        data={
            "doc_type": doc_type,
            "source_type": source_type,
            "classification": classification,
            "uploaded_by": str(uuid7()),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["doc_id"]


# =========================================================================
# B-2: Document List
# =========================================================================


class TestDocumentList:
    @pytest.mark.anyio
    async def test_list_empty(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(f"/v1/workspaces/{workspace_id}/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["next_cursor"] is None

    @pytest.mark.anyio
    async def test_list_populated(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        doc_id = await _upload_document(client, workspace_id, filename="alpha.pdf")
        resp = await client.get(f"/v1/workspaces/{workspace_id}/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["doc_id"] == doc_id
        assert item["filename"] == "alpha.pdf"
        assert "doc_type" in item
        assert "classification" in item
        assert "status" in item
        assert "uploaded_at" in item

    @pytest.mark.anyio
    async def test_list_pagination(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Upload 3 docs, request limit=2 — should get next_cursor."""
        for i in range(3):
            await _upload_document(client, workspace_id, filename=f"doc_{i}.pdf")

        # First page
        resp1 = await client.get(
            f"/v1/workspaces/{workspace_id}/documents",
            params={"limit": 2},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert len(data1["items"]) == 2
        assert data1["total"] == 3
        assert data1["next_cursor"] is not None

        # Second page
        resp2 = await client.get(
            f"/v1/workspaces/{workspace_id}/documents",
            params={"limit": 2, "cursor": data1["next_cursor"]},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) == 1
        assert data2["next_cursor"] is None

    @pytest.mark.anyio
    async def test_workspace_isolation(
        self, client: AsyncClient, workspace_id: str, other_workspace_id: str,
    ) -> None:
        """Documents in workspace A must not appear when querying workspace B."""
        await _upload_document(client, workspace_id, filename="ws_a.pdf")
        await _upload_document(client, other_workspace_id, filename="ws_b.pdf")

        resp_a = await client.get(f"/v1/workspaces/{workspace_id}/documents")
        resp_b = await client.get(f"/v1/workspaces/{other_workspace_id}/documents")

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        filenames_a = [d["filename"] for d in resp_a.json()["items"]]
        filenames_b = [d["filename"] for d in resp_b.json()["items"]]
        assert "ws_a.pdf" in filenames_a
        assert "ws_b.pdf" not in filenames_a
        assert "ws_b.pdf" in filenames_b
        assert "ws_a.pdf" not in filenames_b


# =========================================================================
# B-3: Document Detail
# =========================================================================


class TestDocumentDetail:
    @pytest.mark.anyio
    async def test_get_existing(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        doc_id = await _upload_document(client, workspace_id, filename="detail.pdf")
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["doc_id"] == doc_id
        assert data["filename"] == "detail.pdf"
        assert data["doc_type"] == "BOQ"
        assert data["classification"] == "CONFIDENTIAL"
        assert "extraction_status" in data
        assert "line_item_count" in data

    @pytest.mark.anyio
    async def test_404_missing(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/documents/{uuid7()}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_404_wrong_workspace(
        self, client: AsyncClient, workspace_id: str, other_workspace_id: str,
    ) -> None:
        """Document exists but belongs to a different workspace → 404."""
        doc_id = await _upload_document(client, workspace_id, filename="private.pdf")
        resp = await client.get(
            f"/v1/workspaces/{other_workspace_id}/documents/{doc_id}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_extraction_status_and_line_item_count(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Before extraction, status should be None/null and line_item_count 0."""
        doc_id = await _upload_document(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/documents/{doc_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        # No extraction job → null status, 0 line items
        assert data["extraction_status"] is None
        assert data["line_item_count"] == 0
