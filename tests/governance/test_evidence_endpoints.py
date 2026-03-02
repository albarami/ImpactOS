"""Tests for B-7 evidence list/detail/link endpoints.

Covers:
- GET  /{ws}/governance/evidence              -- list evidence snippets by source_id
- GET  /{ws}/governance/evidence/{snippet_id} -- evidence detail with bbox
- POST /{ws}/governance/evidence/{snippet_id}/link -- link snippet to claim
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

from src.repositories.governance import EvidenceSnippetRepository

WS_ID = str(uuid7())
DOC_ID = uuid7()


async def _seed_snippet(
    db_session,
    source_id=None,
    page: int = 0,
    text: str = "sample text",
) -> "EvidenceSnippetRow":  # noqa: F821
    """Insert an evidence snippet directly via repository."""
    repo = EvidenceSnippetRepository(db_session)
    return await repo.create(
        snippet_id=uuid7(),
        source_id=source_id or DOC_ID,
        page=page,
        bbox_x0=0.0,
        bbox_y0=0.0,
        bbox_x1=1.0,
        bbox_y1=1.0,
        extracted_text=text,
        checksum="sha256:" + "a" * 64,
    )


# Draft text helpers (re-used from claim endpoint tests)
_ASSUMPTION_TEXT = "We assume 65% domestic share."


async def _extract_claims(client: AsyncClient, draft_text: str, run_id: str | None = None) -> dict:
    """Extract claims via the existing endpoint and return the response JSON."""
    rid = run_id or str(uuid7())
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/governance/claims/extract",
        json={"draft_text": draft_text, "run_id": rid},
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# TestEvidenceList
# ---------------------------------------------------------------------------


class TestEvidenceList:
    @pytest.mark.anyio
    async def test_list_empty(self, client: AsyncClient, db_session) -> None:
        """Unknown source_id -> 200, empty items, total=0."""
        unknown_source = str(uuid7())
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/evidence",
            params={"source_id": unknown_source},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.anyio
    async def test_list_returns_snippets(self, client: AsyncClient, db_session) -> None:
        """Seed 2 snippets for same source, list by source_id -> finds both."""
        source = uuid7()
        await _seed_snippet(db_session, source_id=source, page=0, text="first")
        await _seed_snippet(db_session, source_id=source, page=1, text="second")

        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/evidence",
            params={"source_id": str(source)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        # Each item should have essential fields
        for item in data["items"]:
            assert "snippet_id" in item
            assert "source_id" in item
            assert "page" in item
            assert "extracted_text" in item
            assert "checksum" in item
            assert "created_at" in item

    @pytest.mark.anyio
    async def test_list_filters_by_source(self, client: AsyncClient, db_session) -> None:
        """Two different source_ids -- verify isolation."""
        source_a = uuid7()
        source_b = uuid7()
        await _seed_snippet(db_session, source_id=source_a, text="doc A snippet")
        await _seed_snippet(db_session, source_id=source_b, text="doc B snippet")

        resp_a = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/evidence",
            params={"source_id": str(source_a)},
        )
        resp_b = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/evidence",
            params={"source_id": str(source_b)},
        )
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        ids_a = {item["snippet_id"] for item in resp_a.json()["items"]}
        ids_b = {item["snippet_id"] for item in resp_b.json()["items"]}
        assert ids_a.isdisjoint(ids_b), "Snippets from different sources must not overlap"


# ---------------------------------------------------------------------------
# TestEvidenceDetail
# ---------------------------------------------------------------------------


class TestEvidenceDetail:
    @pytest.mark.anyio
    async def test_detail_returns_snippet(self, client: AsyncClient, db_session) -> None:
        """Seed snippet, get by id -> 200 with all fields including bbox."""
        row = await _seed_snippet(db_session, text="detail test snippet")
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/evidence/{row.snippet_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["snippet_id"] == str(row.snippet_id)
        assert data["source_id"] == str(row.source_id)
        assert data["page"] == row.page
        assert data["extracted_text"] == "detail test snippet"
        assert data["checksum"] == row.checksum
        # Verify bbox structure
        assert "bbox" in data
        bbox = data["bbox"]
        assert bbox["x0"] == 0.0
        assert bbox["y0"] == 0.0
        assert bbox["x1"] == 1.0
        assert bbox["y1"] == 1.0
        assert "created_at" in data

    @pytest.mark.anyio
    async def test_detail_404(self, client: AsyncClient) -> None:
        """Fake snippet_id -> 404."""
        fake_id = str(uuid7())
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/evidence/{fake_id}",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestEvidenceLink
# ---------------------------------------------------------------------------


class TestEvidenceLink:
    @pytest.mark.anyio
    async def test_link_evidence_to_claim(self, client: AsyncClient, db_session) -> None:
        """Create claim (via extract), create snippet, link -> 200.

        Verify via claim detail that snippet_id is in evidence_refs.
        """
        # Create a claim via extract
        run_id = str(uuid7())
        extract = await _extract_claims(client, _ASSUMPTION_TEXT, run_id=run_id)
        claim_id = extract["claims"][0]["claim_id"]

        # Seed an evidence snippet
        row = await _seed_snippet(db_session, text="evidence for claim")

        # Link snippet to claim
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/governance/evidence/{row.snippet_id}/link",
            json={"claim_id": claim_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["linked"] is True
        assert data["snippet_id"] == str(row.snippet_id)
        assert data["claim_id"] == claim_id

        # Verify via claim detail that evidence_refs now contains snippet_id
        claim_resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}",
        )
        assert claim_resp.status_code == 200
        claim_data = claim_resp.json()
        assert str(row.snippet_id) in claim_data["evidence_refs"]

    @pytest.mark.anyio
    async def test_link_nonexistent_snippet_404(self, client: AsyncClient, db_session) -> None:
        """Fake snippet_id -> 404."""
        # Create a real claim
        run_id = str(uuid7())
        extract = await _extract_claims(client, _ASSUMPTION_TEXT, run_id=run_id)
        claim_id = extract["claims"][0]["claim_id"]

        fake_snippet = str(uuid7())
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/governance/evidence/{fake_snippet}/link",
            json={"claim_id": claim_id},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_link_nonexistent_claim_404(self, client: AsyncClient, db_session) -> None:
        """Real snippet, fake claim -> 404."""
        row = await _seed_snippet(db_session, text="orphan snippet")
        fake_claim = str(uuid7())
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/governance/evidence/{row.snippet_id}/link",
            json={"claim_id": fake_claim},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestEvidencePersistenceWiring — Sprint 4 Task 8
# ---------------------------------------------------------------------------


class TestEvidencePersistenceWiring:
    """Integration: extract CSV -> evidence snippets appear in DB."""

    @pytest.mark.anyio
    async def test_extraction_persists_evidence_snippets(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Integration: extract CSV -> evidence snippets appear in DB."""
        import csv
        import io

        ws_id = str(uuid7())
        uploaded_by = str(uuid7())

        # Build a simple CSV with header + 2 data rows
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["item", "qty", "price"])
        writer.writerow(["Steel beams", "100", "50000"])
        writer.writerow(["Concrete", "200", "30000"])
        csv_bytes = buf.getvalue().encode("utf-8")

        # Upload document
        upload_resp = await client.post(
            f"/v1/workspaces/{ws_id}/documents",
            files={"file": ("test.csv", csv_bytes, "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "INTERNAL",
                "uploaded_by": uploaded_by,
            },
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["doc_id"]

        # Trigger extraction
        extract_resp = await client.post(
            f"/v1/workspaces/{ws_id}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True},
        )
        assert extract_resp.status_code == 202
        assert extract_resp.json()["status"] == "COMPLETED"

        # Evidence snippets should now exist via the evidence list endpoint
        evidence_resp = await client.get(
            f"/v1/workspaces/{ws_id}/governance/evidence",
            params={"source_id": doc_id},
        )
        assert evidence_resp.status_code == 200
        data = evidence_resp.json()
        # CSV has 2 data rows (header is skipped), so expect >= 2 snippets
        assert data["total"] >= 2, f"Expected >=2 snippets, got {data['total']}"
