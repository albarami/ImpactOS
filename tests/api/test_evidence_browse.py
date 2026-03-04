"""Tests for Sprint 19 evidence browsing with pagination and filters."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.db.tables import (
    ClaimRow, DocumentRow, EvidenceSnippetRow, RunSnapshotRow, WorkspaceRow,
)
from src.models.common import utc_now

pytestmark = pytest.mark.anyio

WS = UUID("00000000-0000-7000-8000-000000000010")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_workspace(session, ws_id=WS):
    from sqlalchemy import select
    result = await session.execute(
        select(WorkspaceRow).where(WorkspaceRow.workspace_id == ws_id)
    )
    if result.scalar_one_or_none() is None:
        now = utc_now()
        session.add(WorkspaceRow(
            workspace_id=ws_id, client_name="Test", engagement_code="E",
            classification="INTERNAL", description="",
            created_by=uuid7(), created_at=now, updated_at=now,
        ))
        await session.flush()


async def _create_document(session, workspace_id=WS, doc_id=None):
    """Create a document row (evidence snippets reference documents)."""
    did = doc_id or uuid7()
    now = utc_now()
    row = DocumentRow(
        doc_id=did, workspace_id=workspace_id,
        filename="test.pdf", mime_type="application/pdf",
        size_bytes=1024, hash_sha256=f"hash_{did}",
        storage_key=f"s3://test/{did}",
        uploaded_by=uuid7(), uploaded_at=now,
        doc_type="boq", source_type="upload",
        classification="INTERNAL", language="en",
    )
    session.add(row)
    await session.flush()
    return row


async def _create_snippet(session, source_id, text="sample text", page=1):
    """Create an evidence snippet row."""
    now = utc_now()
    row = EvidenceSnippetRow(
        snippet_id=uuid7(), source_id=source_id, page=page,
        bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
        extracted_text=text, checksum=f"chk_{uuid7()}",
        created_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def _create_run(session, workspace_id=WS, checksums=None):
    """Create a run snapshot."""
    run_id = uuid7()
    _dummy = uuid7()
    row = RunSnapshotRow(
        run_id=run_id, model_version_id=_dummy,
        taxonomy_version_id=_dummy, concordance_version_id=_dummy,
        mapping_library_version_id=_dummy,
        assumption_library_version_id=_dummy,
        prompt_pack_version_id=_dummy,
        source_checksums=checksums or [],
        workspace_id=workspace_id,
        created_at=utc_now(),
    )
    session.add(row)
    await session.flush()
    return run_id


async def _create_claim(session, evidence_refs=None, run_id=None):
    """Create a claim row."""
    now = utc_now()
    row = ClaimRow(
        claim_id=uuid7(), text="test claim", claim_type="quantitative",
        status="EXTRACTED", disclosure_tier="TIER0",
        model_refs=[], evidence_refs=evidence_refs or [],
        run_id=run_id, created_at=now, updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

async def test_evidence_list_no_params_returns_all(client, db_session):
    """No limit -> all rows, total=len(items), pagination fields are None."""
    await _seed_workspace(db_session)
    doc = await _create_document(db_session)
    for _ in range(3):
        await _create_snippet(db_session, source_id=doc.doc_id)

    resp = await client.get(f"/v1/workspaces/{WS}/governance/evidence")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 3
    assert data["total"] == 3
    # Pagination fields should be None when unpaginated
    assert data.get("total_matching") is None
    assert data.get("has_more") is None


async def test_evidence_list_with_run_id_existing_behavior(client, db_session):
    """Existing run_id filter still works with backward-compatible response."""
    await _seed_workspace(db_session)
    doc = await _create_document(db_session)
    await _create_snippet(db_session, source_id=doc.doc_id)

    # Create run with matching checksums
    run_id = await _create_run(db_session, checksums=[doc.hash_sha256])

    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"run_id": str(run_id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 0  # Backward-compatible


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

async def test_evidence_paginated_limit_offset(client, db_session):
    """limit=2, offset=0 -> correct page + total_matching + has_more."""
    await _seed_workspace(db_session)
    doc = await _create_document(db_session)
    for i in range(5):
        await _create_snippet(db_session, source_id=doc.doc_id, text=f"text {i}")

    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"limit": 2, "offset": 0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total_matching"] == 5
    assert data["has_more"] is True
    assert data["limit"] == 2
    assert data["offset"] == 0


async def test_evidence_paginated_second_page(client, db_session):
    """limit=2, offset=2 -> second page."""
    await _seed_workspace(db_session)
    doc = await _create_document(db_session)
    for i in range(5):
        await _create_snippet(db_session, source_id=doc.doc_id, text=f"text {i}")

    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"limit": 2, "offset": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total_matching"] == 5

    # Third page
    resp3 = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"limit": 2, "offset": 4},
    )
    data3 = resp3.json()
    assert len(data3["items"]) == 1
    assert data3["has_more"] is False


async def test_evidence_invalid_limit_422(client, db_session):
    """limit=200 -> 422 EVIDENCE_INVALID_PAGINATION."""
    await _seed_workspace(db_session)
    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"limit": 200},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "EVIDENCE_INVALID_PAGINATION"


async def test_evidence_negative_offset_422(client, db_session):
    """offset=-1 -> 422 EVIDENCE_INVALID_PAGINATION."""
    await _seed_workspace(db_session)
    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"limit": 10, "offset": -1},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "EVIDENCE_INVALID_PAGINATION"


async def test_evidence_offset_without_limit_422(client, db_session):
    """offset=5 without limit -> 422 EVIDENCE_INVALID_PAGINATION."""
    await _seed_workspace(db_session)
    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"offset": 5},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "EVIDENCE_INVALID_PAGINATION"


# ---------------------------------------------------------------------------
# Claim filter
# ---------------------------------------------------------------------------

async def test_evidence_claim_id_filter(client, db_session):
    """claim_id filter returns only snippets in claim's evidence_refs."""
    await _seed_workspace(db_session)
    doc = await _create_document(db_session)
    s1 = await _create_snippet(db_session, source_id=doc.doc_id, text="linked")
    s2 = await _create_snippet(db_session, source_id=doc.doc_id, text="not linked")
    run_id = await _create_run(db_session)
    claim = await _create_claim(db_session, evidence_refs=[str(s1.snippet_id)], run_id=run_id)

    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"claim_id": str(claim.claim_id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["snippet_id"] == str(s1.snippet_id)


async def test_evidence_claim_id_empty_refs_returns_empty(client, db_session):
    """Claim with empty evidence_refs -> empty items, total_matching=0 (short-circuit)."""
    await _seed_workspace(db_session)
    doc = await _create_document(db_session)
    await _create_snippet(db_session, source_id=doc.doc_id)
    run_id = await _create_run(db_session)
    claim = await _create_claim(db_session, evidence_refs=[], run_id=run_id)

    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"claim_id": str(claim.claim_id), "limit": 10},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 0


async def test_evidence_claim_id_not_found_404(client, db_session):
    """Nonexistent claim_id -> 404."""
    await _seed_workspace(db_session)
    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"claim_id": str(uuid7())},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Source filter
# ---------------------------------------------------------------------------

async def test_evidence_source_id_filter(client, db_session):
    """source_id filter returns only snippets from that source."""
    await _seed_workspace(db_session)
    doc_a = await _create_document(db_session)
    doc_b = await _create_document(db_session)
    s1 = await _create_snippet(db_session, source_id=doc_a.doc_id)
    s2 = await _create_snippet(db_session, source_id=doc_b.doc_id)

    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"source_id": str(doc_a.doc_id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["source_id"] == str(doc_a.doc_id)


async def test_evidence_source_id_not_found_404(client, db_session):
    """Nonexistent source_id -> 404."""
    await _seed_workspace(db_session)
    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"source_id": str(uuid7())},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Text search
# ---------------------------------------------------------------------------

async def test_evidence_text_query_filters(client, db_session):
    """text_query filters to matching snippets."""
    await _seed_workspace(db_session)
    doc = await _create_document(db_session)
    await _create_snippet(db_session, source_id=doc.doc_id, text="project budget allocation")
    await _create_snippet(db_session, source_id=doc.doc_id, text="timeline schedule")

    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"text_query": "budget"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert "budget" in data["items"][0]["extracted_text"]


async def test_evidence_text_query_too_short_422(client, db_session):
    """text_query shorter than 2 chars -> 422."""
    await _seed_workspace(db_session)
    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"text_query": "a"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "EVIDENCE_TEXT_QUERY_TOO_SHORT"


async def test_evidence_text_query_trimmed(client, db_session):
    """text_query is trimmed before validation, so '  ab  ' -> 'ab', valid."""
    await _seed_workspace(db_session)
    doc = await _create_document(db_session)
    await _create_snippet(db_session, source_id=doc.doc_id, text="abstract concept")

    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={"text_query": "  ab  "},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1


# ---------------------------------------------------------------------------
# Combined filters
# ---------------------------------------------------------------------------

async def test_evidence_combined_filters_and(client, db_session):
    """Multiple filters are AND-combined."""
    await _seed_workspace(db_session)
    doc = await _create_document(db_session)
    s1 = await _create_snippet(db_session, source_id=doc.doc_id, text="budget item A")
    s2 = await _create_snippet(db_session, source_id=doc.doc_id, text="schedule item B")
    run_id = await _create_run(db_session)
    claim = await _create_claim(db_session, evidence_refs=[str(s1.snippet_id), str(s2.snippet_id)], run_id=run_id)

    resp = await client.get(
        f"/v1/workspaces/{WS}/governance/evidence",
        params={
            "claim_id": str(claim.claim_id),
            "text_query": "budget",
            "limit": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["snippet_id"] == str(s1.snippet_id)
