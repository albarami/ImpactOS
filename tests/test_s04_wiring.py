"""S0-4 Wiring Tests — Doc→Shock, CORS, Backward Compatibility.

Tests the S0-4 wiring fixes:
1. Compile from stored document (G4 doc→shock)
2. CORS reads from settings (G11)
3. Backward compatibility: inline line_items still works (Amendment 5)
"""

from datetime import datetime, timezone
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from uuid_extensions import uuid7

from src.db.tables import DocumentRow, ExtractionJobRow, LineItemRow

WS_ID = "01961060-0000-7000-8000-000000000001"
WS_ID_UUID = UUID(WS_ID)
WS_ID_OTHER = "01961060-0000-7000-8000-000000000002"
WS_ID_OTHER_UUID = UUID(WS_ID_OTHER)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_document(db_session, workspace_id=WS_ID_UUID):  # noqa: ANN001
    """Create a document row in the test DB."""
    doc_id = uuid7()
    now = datetime.now(timezone.utc)
    row = DocumentRow(
        doc_id=doc_id,
        workspace_id=workspace_id,
        filename="test_boq.csv",
        mime_type="text/csv",
        size_bytes=1024,
        hash_sha256="sha256:" + "a" * 64,
        storage_key=f"workspaces/{workspace_id}/documents/{doc_id}/test_boq.csv",
        uploaded_by=uuid7(),
        uploaded_at=now,
        doc_type="BOQ",
        source_type="UPLOAD",
        classification="INTERNAL",
        language="en",
    )
    db_session.add(row)
    await db_session.flush()
    return doc_id


async def _seed_extraction_job(  # noqa: ANN001
    db_session,
    doc_id,
    status="COMPLETED",
):
    """Create an extraction job row."""
    job_id = uuid7()
    now = datetime.now(timezone.utc)
    row = ExtractionJobRow(
        job_id=job_id,
        doc_id=doc_id,
        workspace_id=WS_ID_UUID,
        status=status,
        extract_tables=True,
        extract_line_items=True,
        language_hint="en",
        created_at=now,
        updated_at=now,
    )
    db_session.add(row)
    await db_session.flush()
    return job_id


async def _seed_line_items(  # noqa: ANN001
    db_session,
    doc_id,
    job_id,
    descriptions=None,
):
    """Create line item rows for a document/job."""
    if descriptions is None:
        descriptions = ["Structural Steel Supply", "Concrete Works", "Electrical Systems"]
    now = datetime.now(timezone.utc)
    items = []
    for desc in descriptions:
        li_id = uuid7()
        row = LineItemRow(
            line_item_id=li_id,
            doc_id=doc_id,
            extraction_job_id=job_id,
            raw_text=desc,
            description=desc,
            quantity=100.0,
            unit="ton",
            unit_price=3500.0,
            total_value=350_000.0,
            currency_code="SAR",
            page_ref=0,
            evidence_snippet_ids=[str(uuid7())],
            created_at=now,
        )
        db_session.add(row)
        items.append(row)
    await db_session.flush()
    return items


# ===================================================================
# 1. Doc→Shock Wiring (G4)
# ===================================================================


class TestDocToShockWiring:
    """Compile from stored documents — the doc→shock moat."""

    @pytest.mark.anyio
    async def test_compile_from_document_id(
        self, client: AsyncClient, db_session,  # noqa: ANN001
    ) -> None:
        """Upload doc → extract → compile by document_id → 201."""
        doc_id = await _seed_document(db_session)
        job_id = await _seed_extraction_job(db_session, doc_id)
        await _seed_line_items(db_session, doc_id, job_id)

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json={
                "scenario_name": "Doc Compile Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "document_id": str(doc_id),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["compilation_id"]
        assert len(data["suggestions"]) >= 1

    @pytest.mark.anyio
    async def test_compile_uses_stored_line_items(
        self, client: AsyncClient, db_session,  # noqa: ANN001
    ) -> None:
        """Verify suggestions correspond to stored line items."""
        doc_id = await _seed_document(db_session)
        job_id = await _seed_extraction_job(db_session, doc_id)
        items = await _seed_line_items(
            db_session, doc_id, job_id,
            descriptions=["concrete works for building"],
        )

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json={
                "scenario_name": "Stored Items Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "document_id": str(doc_id),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        # One item in, should get one suggestion out
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["line_item_id"] == str(items[0].line_item_id)

    @pytest.mark.anyio
    async def test_compile_uses_latest_extraction_only(
        self, client: AsyncClient, db_session,  # noqa: ANN001
    ) -> None:
        """Amendment 1: Two extractions → compile uses job 2's items only."""
        doc_id = await _seed_document(db_session)

        # First extraction: 2 items
        job1 = await _seed_extraction_job(db_session, doc_id)
        await _seed_line_items(
            db_session, doc_id, job1,
            descriptions=["OLD item A", "OLD item B"],
        )

        # Second extraction (more recent): 3 items
        job2 = await _seed_extraction_job(db_session, doc_id)
        items2 = await _seed_line_items(
            db_session, doc_id, job2,
            descriptions=["NEW steel supply", "NEW concrete works", "NEW electrical"],
        )

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json={
                "scenario_name": "Latest Extraction Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "document_id": str(doc_id),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        # Should use job2's 3 items, not job1's 2
        assert len(data["suggestions"]) == 3
        returned_ids = {s["line_item_id"] for s in data["suggestions"]}
        expected_ids = {str(li.line_item_id) for li in items2}
        assert returned_ids == expected_ids

    @pytest.mark.anyio
    async def test_compile_document_without_extraction_returns_409(
        self, client: AsyncClient, db_session,  # noqa: ANN001
    ) -> None:
        """Amendment 2: No completed extraction → 409."""
        doc_id = await _seed_document(db_session)
        # No extraction job created

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json={
                "scenario_name": "No Extraction Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "document_id": str(doc_id),
            },
        )
        assert resp.status_code == 409
        assert "no completed extraction" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_compile_rejects_missing_document(
        self, client: AsyncClient,
    ) -> None:
        """Non-existent document_id → 404."""
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json={
                "scenario_name": "Missing Doc Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "document_id": str(uuid7()),
            },
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_compile_rejects_cross_workspace_document(
        self, client: AsyncClient, db_session,  # noqa: ANN001
    ) -> None:
        """Document in ws1, compile from ws2 → 404."""
        # Create doc in OTHER workspace
        doc_id = await _seed_document(db_session, workspace_id=WS_ID_OTHER_UUID)
        job_id = await _seed_extraction_job(db_session, doc_id)
        await _seed_line_items(db_session, doc_id, job_id)

        # Compile from WS_ID (different workspace)
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json={
                "scenario_name": "Cross WS Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "document_id": str(doc_id),
            },
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_compile_validates_exactly_one_source(
        self, client: AsyncClient,
    ) -> None:
        """Neither line_items nor document_id → 422. Both → 422."""
        base = {
            "scenario_name": "Validation Test",
            "base_model_version_id": str(uuid7()),
            "base_year": 2023,
            "start_year": 2024,
            "end_year": 2030,
        }

        # Neither provided
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json=base,
        )
        assert resp.status_code == 422

        # Both provided
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json={
                **base,
                "line_items": [{"line_item_id": str(uuid7()), "raw_text": "test", "total_value": 1.0}],
                "document_id": str(uuid7()),
            },
        )
        assert resp.status_code == 422


# ===================================================================
# 2. CORS Configuration (G11)
# ===================================================================


class TestCORSConfig:
    """CORS reads from settings.ALLOWED_ORIGINS."""

    @pytest.mark.anyio
    async def test_cors_allows_configured_origins(self) -> None:
        """Request with allowed origin → CORS headers present."""
        from src.api.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert "access-control-allow-origin" in resp.headers

    @pytest.mark.anyio
    async def test_cors_blocks_unconfigured_origins(self) -> None:
        """Request with random origin → no CORS allow-origin header."""
        from src.api.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.options(
                "/health",
                headers={
                    "Origin": "http://evil-site.example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            allow_origin = resp.headers.get("access-control-allow-origin", "")
            assert "evil-site" not in allow_origin


# ===================================================================
# 3. Backward Compatibility (Amendment 5)
# ===================================================================


class TestBackwardCompat:
    """Inline line_items in request body still works."""

    @pytest.mark.anyio
    async def test_compile_with_inline_line_items_still_works(
        self, client: AsyncClient,
    ) -> None:
        """Old payload-based flow → 201."""
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json={
                "scenario_name": "Backward Compat Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "line_items": [
                    {
                        "line_item_id": str(uuid7()),
                        "raw_text": "concrete works for stadium",
                        "total_value": 5000000.0,
                    },
                ],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["compilation_id"]
        assert len(data["suggestions"]) == 1
