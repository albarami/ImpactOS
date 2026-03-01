"""Phase 0 v2 — End-to-end hardening integration tests.

Proves the full stored-document workflow:
upload -> extract -> compile -> (quality + claims) -> export

Tests cover:
1. Full flow: upload CSV -> extract -> verify line items -> create scenario ->
   compile from stored document -> sandbox export -> COMPLETED
2. Governed export blocked by unresolved claim
3. Governed export blocked by synthetic fallback quality
4. Sandbox export ignores synthetic quality issues
5. Governed export succeeds when claims resolved and no synthetic fallback
"""

from io import BytesIO
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import ClaimRow, RunQualitySummaryRow
from src.models.common import new_uuid7, utc_now

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WS_ID = "01961060-0000-7000-8000-000000000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_csv_content() -> bytes:
    """Return CSV bytes with 2 data rows (Structural Steel, Concrete Works)."""
    header = "description,quantity,unit,unit_price,total_value,currency_code"
    row1 = "Structural Steel Supply,100,ton,3500.0,350000.0,SAR"
    row2 = "Concrete Works,200,m3,1500.0,300000.0,SAR"
    return f"{header}\n{row1}\n{row2}\n".encode("utf-8")


async def _seed_quality_summary(
    db_session: AsyncSession,
    run_id: UUID,
    workspace_id: UUID,
    used_synthetic_fallback: bool,
    data_mode: str,
) -> RunQualitySummaryRow:
    """Insert a RunQualitySummaryRow directly into the test database."""
    row = RunQualitySummaryRow(
        summary_id=new_uuid7(),
        run_id=run_id,
        workspace_id=workspace_id,
        overall_run_score=0.85,
        overall_run_grade="B",
        coverage_pct=0.9,
        mapping_coverage_pct=0.8,
        publication_gate_pass=True,
        publication_gate_mode="SANDBOX",
        summary_version="1.0.0",
        summary_hash="sha256:test",
        payload={
            "assessment_version": 1,
            "composite_score": 0.85,
            "grade": "B",
            "data_mode": data_mode,
            "used_synthetic_fallback": used_synthetic_fallback,
            "fallback_reason": "no curated data" if used_synthetic_fallback else None,
            "data_source_id": "test-dataset",
            "checksum_verified": True,
            "warnings": [],
            "dimension_assessments": [],
            "applicable_dimensions": [],
            "assessed_dimensions": [],
            "missing_dimensions": [],
            "completeness_pct": 0.9,
            "waiver_required_count": 0,
            "critical_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "known_gaps": [],
        },
        created_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _seed_claim(
    db_session: AsyncSession,
    run_id: UUID,
    workspace_id: UUID,  # noqa: ARG001 — kept for caller symmetry
    status: str,
) -> ClaimRow:
    """Insert a ClaimRow directly into the test database.

    Note: ClaimRow does not have a workspace_id column — claims are
    associated with runs via run_id. The workspace_id parameter is accepted
    for interface consistency but is not persisted.
    """
    row = ClaimRow(
        claim_id=new_uuid7(),
        run_id=run_id,
        text="GDP impact claim needs evidence.",
        claim_type="MODEL",
        status=status,
        disclosure_tier="TIER0",
        model_refs=[],
        evidence_refs=[],
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()
    return row


def _make_export_payload(run_id: str, mode: str) -> dict:
    """Return an export request dict suitable for POST /exports."""
    return {
        "run_id": run_id,
        "mode": mode,
        "export_formats": ["excel"],
        "pack_data": {"title": "E2E Hardening Test"},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPhase0E2EHardening:
    """End-to-end hardening tests for Phase 0 v2."""

    @pytest.mark.anyio
    async def test_full_flow_sandbox_succeeds(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Happy path: upload CSV -> extract -> line items -> scenario ->
        compile from stored doc -> sandbox export -> COMPLETED."""
        ws_id = WS_ID
        user_id = str(new_uuid7())

        # --- 1. Upload CSV document ---
        csv_bytes = _make_csv_content()
        upload_resp = await client.post(
            f"/v1/workspaces/{ws_id}/documents",
            files={"file": ("boq_test.csv", BytesIO(csv_bytes), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "INTERNAL",
                "language": "en",
                "uploaded_by": user_id,
            },
        )
        assert upload_resp.status_code == 201, f"Upload failed: {upload_resp.text}"
        doc_id = upload_resp.json()["doc_id"]

        # --- 2. Extract document ---
        extract_resp = await client.post(
            f"/v1/workspaces/{ws_id}/documents/{doc_id}/extract",
            json={
                "extract_tables": True,
                "extract_line_items": True,
                "language_hint": "en",
            },
        )
        assert extract_resp.status_code == 202, f"Extract failed: {extract_resp.text}"

        # --- 3. Verify line items exist ---
        items_resp = await client.get(
            f"/v1/workspaces/{ws_id}/documents/{doc_id}/line-items",
        )
        assert items_resp.status_code == 200
        items = items_resp.json()["items"]
        assert len(items) >= 2, f"Expected >= 2 line items, got {len(items)}"

        # --- 4. Create scenario ---
        model_version_id = str(new_uuid7())
        scenario_resp = await client.post(
            f"/v1/workspaces/{ws_id}/scenarios",
            json={
                "name": "E2E Hardening Scenario",
                "base_model_version_id": model_version_id,
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
            },
        )
        assert scenario_resp.status_code == 201, (
            f"Scenario creation failed: {scenario_resp.text}"
        )
        scenario_id = scenario_resp.json()["scenario_spec_id"]

        # --- 5. Compile from stored document ---
        # Build decisions referencing the extracted line_item_ids
        decisions = [
            {
                "line_item_id": item["line_item_id"],
                "final_sector_code": "F",
                "decision_type": "APPROVED",
                "suggested_confidence": 0.9,
                "decided_by": user_id,
            }
            for item in items
        ]
        compile_resp = await client.post(
            f"/v1/workspaces/{ws_id}/scenarios/{scenario_id}/compile",
            json={
                "document_id": doc_id,
                "decisions": decisions,
                "phasing": {"2024": 0.5, "2025": 0.5},
                "default_domestic_share": 0.65,
            },
        )
        assert compile_resp.status_code == 200, (
            f"Compile failed: {compile_resp.text}"
        )
        compile_data = compile_resp.json()
        assert "shock_items" in compile_data
        assert len(compile_data["shock_items"]) >= 1

        # --- 6. Sandbox export -> COMPLETED ---
        run_id = str(new_uuid7())
        export_resp = await client.post(
            f"/v1/workspaces/{ws_id}/exports",
            json=_make_export_payload(run_id, "SANDBOX"),
        )
        assert export_resp.status_code == 201
        export_data = export_resp.json()
        assert export_data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_governed_export_blocked_by_unresolved_claim(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Governed export blocked when an unresolved claim exists."""
        ws_id = WS_ID
        run_id = new_uuid7()

        # Seed unresolved claim
        await _seed_claim(
            db_session, run_id, UUID(ws_id), status="NEEDS_EVIDENCE",
        )

        # Seed clean quality summary (no synthetic fallback)
        await _seed_quality_summary(
            db_session,
            run_id,
            UUID(ws_id),
            used_synthetic_fallback=False,
            data_mode="curated_real",
        )

        # POST governed export -> should be BLOCKED
        export_resp = await client.post(
            f"/v1/workspaces/{ws_id}/exports",
            json=_make_export_payload(str(run_id), "GOVERNED"),
        )
        assert export_resp.status_code == 201
        export_data = export_resp.json()
        assert export_data["status"] == "BLOCKED"
        assert len(export_data["blocking_reasons"]) >= 1

    @pytest.mark.anyio
    async def test_governed_export_blocked_by_synthetic_fallback(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Governed export blocked when quality uses synthetic fallback."""
        ws_id = WS_ID
        run_id = new_uuid7()

        # Seed quality with used_synthetic_fallback=True (no claims)
        await _seed_quality_summary(
            db_session,
            run_id,
            UUID(ws_id),
            used_synthetic_fallback=True,
            data_mode="synthetic_fallback",
        )

        # POST governed export -> BLOCKED, "synthetic" in blocking_reasons
        export_resp = await client.post(
            f"/v1/workspaces/{ws_id}/exports",
            json=_make_export_payload(str(run_id), "GOVERNED"),
        )
        assert export_resp.status_code == 201
        export_data = export_resp.json()
        assert export_data["status"] == "BLOCKED"
        blocking_text = " ".join(export_data["blocking_reasons"]).lower()
        assert "synthetic" in blocking_text, (
            f"Expected 'synthetic' in blocking reasons: {export_data['blocking_reasons']}"
        )

    @pytest.mark.anyio
    async def test_sandbox_export_ignores_synthetic_quality(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Sandbox export succeeds even with synthetic fallback quality."""
        ws_id = WS_ID
        run_id = new_uuid7()

        # Seed quality with synthetic fallback
        await _seed_quality_summary(
            db_session,
            run_id,
            UUID(ws_id),
            used_synthetic_fallback=True,
            data_mode="synthetic_fallback",
        )

        # POST sandbox export -> COMPLETED
        export_resp = await client.post(
            f"/v1/workspaces/{ws_id}/exports",
            json=_make_export_payload(str(run_id), "SANDBOX"),
        )
        assert export_resp.status_code == 201
        export_data = export_resp.json()
        assert export_data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_governed_succeeds_when_claims_resolved_and_no_synthetic(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Governed export succeeds with resolved claim and clean quality."""
        ws_id = WS_ID
        run_id = new_uuid7()

        # Seed claim with status="SUPPORTED"
        await _seed_claim(
            db_session, run_id, UUID(ws_id), status="SUPPORTED",
        )

        # Seed clean quality (no synthetic fallback)
        await _seed_quality_summary(
            db_session,
            run_id,
            UUID(ws_id),
            used_synthetic_fallback=False,
            data_mode="curated_real",
        )

        # POST governed export -> COMPLETED
        export_resp = await client.post(
            f"/v1/workspaces/{ws_id}/exports",
            json=_make_export_payload(str(run_id), "GOVERNED"),
        )
        assert export_resp.status_code == 201
        export_data = export_resp.json()
        assert export_data["status"] == "COMPLETED"
