"""Tests for B-7 evidence list/detail/link endpoints.

Covers:
- GET  /{ws}/governance/evidence              -- list evidence snippets by run_id
- GET  /{ws}/governance/evidence/{snippet_id} -- evidence detail with bbox
- POST /{ws}/governance/claims/{claim_id}/evidence -- link evidence to claim
- Workspace ownership enforcement via Document.workspace_id join
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

from src.repositories.documents import DocumentRepository
from src.repositories.engine import RunSnapshotRepository
from src.repositories.governance import EvidenceSnippetRepository

WS_ID = str(uuid7())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_document(db_session, workspace_id: str) -> UUID:
    """Create a document row and return its doc_id."""
    repo = DocumentRepository(db_session)
    doc_id = uuid7()
    await repo.create(
        doc_id=doc_id,
        workspace_id=UUID(workspace_id),
        filename="test.csv",
        mime_type="text/csv",
        size_bytes=100,
        hash_sha256="sha256:" + "b" * 64,
        storage_key="test/key",
        uploaded_by=uuid7(),
        doc_type="BOQ",
        source_type="CLIENT",
        classification="INTERNAL",
    )
    return doc_id


async def _seed_run_snapshot(db_session, run_id: str, workspace_id: str) -> None:
    """Create a RunSnapshot row linking run_id to workspace_id."""
    repo = RunSnapshotRepository(db_session)
    dummy_uuid = uuid7()
    await repo.create(
        run_id=UUID(run_id),
        model_version_id=dummy_uuid,
        taxonomy_version_id=dummy_uuid,
        concordance_version_id=dummy_uuid,
        mapping_library_version_id=dummy_uuid,
        assumption_library_version_id=dummy_uuid,
        prompt_pack_version_id=dummy_uuid,
        source_checksums=[],
        workspace_id=UUID(workspace_id),
    )


async def _seed_snippet(
    db_session,
    source_id: UUID | None = None,
    page: int = 0,
    text: str = "sample text",
) -> "EvidenceSnippetRow":  # noqa: F821
    """Insert an evidence snippet directly via repository."""
    repo = EvidenceSnippetRepository(db_session)
    return await repo.create(
        snippet_id=uuid7(),
        source_id=source_id or uuid7(),
        page=page,
        bbox_x0=0.0,
        bbox_y0=0.0,
        bbox_x1=1.0,
        bbox_y1=1.0,
        extracted_text=text,
        checksum="sha256:" + "a" * 64,
    )


_ASSUMPTION_TEXT = "We assume 65% domestic share."


async def _extract_claims(
    client: AsyncClient,
    draft_text: str,
    run_id: str | None = None,
    ws_id: str = WS_ID,
) -> dict:
    """Extract claims via the existing endpoint and return the response JSON."""
    rid = run_id or str(uuid7())
    resp = await client.post(
        f"/v1/workspaces/{ws_id}/governance/claims/extract",
        json={"draft_text": draft_text, "run_id": rid},
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# TestEvidenceList
# ---------------------------------------------------------------------------


class TestEvidenceList:
    @pytest.mark.anyio
    async def test_list_empty_workspace(self, client: AsyncClient) -> None:
        """Workspace with no documents -> 200, empty items."""
        ws = str(uuid7())
        run_id = str(uuid7())
        resp = await client.get(
            f"/v1/workspaces/{ws}/governance/evidence",
            params={"run_id": run_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.anyio
    async def test_list_returns_snippets_by_run(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Seed doc + snippets + run snapshot, list by run_id -> finds snippets."""
        run_id = str(uuid7())
        doc_id = await _seed_document(db_session, WS_ID)
        await _seed_run_snapshot(db_session, run_id, WS_ID)
        await _seed_snippet(db_session, source_id=doc_id, page=0, text="first")
        await _seed_snippet(db_session, source_id=doc_id, page=1, text="second")

        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/evidence",
            params={"run_id": run_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        for item in data["items"]:
            assert "snippet_id" in item
            assert "source_id" in item
            assert "page" in item
            assert "extracted_text" in item
            assert "checksum" in item
            assert "created_at" in item

    @pytest.mark.anyio
    async def test_list_run_wrong_workspace_empty(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Run belongs to ws_a, querying from ws_b -> empty result."""
        ws_a = str(uuid7())
        ws_b = str(uuid7())
        run_id = str(uuid7())
        doc_id = await _seed_document(db_session, ws_a)
        await _seed_run_snapshot(db_session, run_id, ws_a)
        await _seed_snippet(db_session, source_id=doc_id, text="ws_a snippet")

        resp = await client.get(
            f"/v1/workspaces/{ws_b}/governance/evidence",
            params={"run_id": run_id},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# TestEvidenceDetail
# ---------------------------------------------------------------------------


class TestEvidenceDetail:
    @pytest.mark.anyio
    async def test_detail_returns_snippet(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Seed doc + snippet, get by id -> 200 with all fields including bbox."""
        doc_id = await _seed_document(db_session, WS_ID)
        row = await _seed_snippet(
            db_session, source_id=doc_id, text="detail test snippet",
        )
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

    @pytest.mark.anyio
    async def test_detail_wrong_workspace_404(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Snippet's document belongs to ws_a, querying from ws_b -> 404."""
        ws_a = str(uuid7())
        ws_b = str(uuid7())
        doc_id = await _seed_document(db_session, ws_a)
        row = await _seed_snippet(
            db_session, source_id=doc_id, text="ws_a only",
        )
        resp = await client.get(
            f"/v1/workspaces/{ws_b}/governance/evidence/{row.snippet_id}",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestEvidenceLink
# ---------------------------------------------------------------------------


class TestEvidenceLink:
    @pytest.mark.anyio
    async def test_link_evidence_to_claim(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Link evidence to claim via POST /claims/{id}/evidence."""
        run_id = str(uuid7())
        doc_id = await _seed_document(db_session, WS_ID)
        await _seed_run_snapshot(db_session, run_id, WS_ID)
        extract = await _extract_claims(client, _ASSUMPTION_TEXT, run_id=run_id)
        claim_id = extract["claims"][0]["claim_id"]

        row = await _seed_snippet(
            db_session, source_id=doc_id, text="evidence for claim",
        )

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}/evidence",
            json={"evidence_ids": [str(row.snippet_id)]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["claim_id"] == claim_id
        assert str(row.snippet_id) in data["evidence_ids"]
        assert data["total_linked"] >= 1

        claim_resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}",
        )
        assert claim_resp.status_code == 200
        assert str(row.snippet_id) in claim_resp.json()["evidence_refs"]

    @pytest.mark.anyio
    async def test_link_deduplicates(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Linking same evidence twice does not create duplicates."""
        run_id = str(uuid7())
        doc_id = await _seed_document(db_session, WS_ID)
        await _seed_run_snapshot(db_session, run_id, WS_ID)
        extract = await _extract_claims(client, _ASSUMPTION_TEXT, run_id=run_id)
        claim_id = extract["claims"][0]["claim_id"]

        row = await _seed_snippet(
            db_session, source_id=doc_id, text="dedup test",
        )
        sid = str(row.snippet_id)

        await client.post(
            f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}/evidence",
            json={"evidence_ids": [sid]},
        )
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}/evidence",
            json={"evidence_ids": [sid, sid]},
        )
        assert resp.status_code == 200
        assert resp.json()["total_linked"] == 1

    @pytest.mark.anyio
    async def test_link_nonexistent_evidence_404(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Fake evidence_id -> 404."""
        run_id = str(uuid7())
        await _seed_run_snapshot(db_session, run_id, WS_ID)
        extract = await _extract_claims(client, _ASSUMPTION_TEXT, run_id=run_id)
        claim_id = extract["claims"][0]["claim_id"]

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}/evidence",
            json={"evidence_ids": [str(uuid7())]},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_link_nonexistent_claim_404(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Fake claim_id -> 404."""
        doc_id = await _seed_document(db_session, WS_ID)
        row = await _seed_snippet(
            db_session, source_id=doc_id, text="orphan snippet",
        )
        fake_claim = str(uuid7())
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/governance/claims/{fake_claim}/evidence",
            json={"evidence_ids": [str(row.snippet_id)]},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_link_wrong_workspace_evidence_404(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Evidence belongs to ws_a, claim belongs to ws_b -> 404."""
        ws_a = str(uuid7())
        ws_b = str(uuid7())
        run_id = str(uuid7())
        doc_a = await _seed_document(db_session, ws_a)
        await _seed_run_snapshot(db_session, run_id, ws_b)
        extract = await _extract_claims(
            client, _ASSUMPTION_TEXT, run_id=run_id, ws_id=ws_b,
        )
        claim_id = extract["claims"][0]["claim_id"]

        row = await _seed_snippet(
            db_session, source_id=doc_a, text="wrong ws evidence",
        )
        resp = await client.post(
            f"/v1/workspaces/{ws_b}/governance/claims/{claim_id}/evidence",
            json={"evidence_ids": [str(row.snippet_id)]},
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
        run_id = str(uuid7())
        await _seed_run_snapshot(db_session, run_id, ws_id)

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["item", "qty", "price"])
        writer.writerow(["Steel beams", "100", "50000"])
        writer.writerow(["Concrete", "200", "30000"])
        csv_bytes = buf.getvalue().encode("utf-8")

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

        extract_resp = await client.post(
            f"/v1/workspaces/{ws_id}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True},
        )
        assert extract_resp.status_code == 202
        assert extract_resp.json()["status"] == "COMPLETED"

        evidence_resp = await client.get(
            f"/v1/workspaces/{ws_id}/governance/evidence",
            params={"run_id": run_id},
        )
        assert evidence_resp.status_code == 200
        data = evidence_resp.json()
        assert data["total"] >= 2, f"Expected >=2 snippets, got {data['total']}"
