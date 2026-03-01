"""Tests for G1: export route must pass quality_assessment into ExportOrchestrator.

Governed exports should be BLOCKED when the run used synthetic fallback data.
Sandbox exports should ignore synthetic fallback and COMPLETE normally.
Governed exports should also be BLOCKED when unresolved claims exist (independent
of quality assessment). When no quality summary and no claims exist, governed
exports should COMPLETE.

These tests will FAIL until the export route (src/api/exports.py) is updated
to fetch RunQualitySummaryRow from DB and reconstruct a RunQualityAssessment
to pass into ExportOrchestrator.execute().
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.db.tables import ClaimRow, RunQualitySummaryRow
from src.models.common import new_uuid7, utc_now


def _make_export_payload(run_id: str, mode: str = "SANDBOX") -> dict:
    return {
        "run_id": run_id,
        "mode": mode,
        "export_formats": ["excel"],
        "pack_data": {
            "run_id": run_id,
            "scenario_name": "Test",
            "base_year": 2023,
            "currency": "SAR",
            "model_version_id": str(uuid7()),
            "scenario_version": 1,
            "executive_summary": {"headline_gdp": 4.2e9, "headline_jobs": 21200},
            "sector_impacts": [
                {
                    "sector_code": "C41",
                    "sector_name": "Steel",
                    "direct_impact": 500.0,
                    "indirect_impact": 250.0,
                    "total_impact": 750.0,
                    "multiplier": 1.5,
                    "domestic_share": 0.65,
                    "import_leakage": 0.35,
                },
            ],
            "input_vectors": {"C41": 1000.0},
            "sensitivity": [],
            "assumptions": [],
            "evidence_ledger": [],
        },
    }


def _to_uuid(value: str | UUID) -> UUID:
    """Ensure value is a UUID object (not a string)."""
    if isinstance(value, UUID):
        return value
    return UUID(value)


async def _seed_quality_summary(
    db_session: AsyncSession,
    *,
    run_id: str | UUID,
    ws_id: str | UUID,
    used_synthetic_fallback: bool = False,
    data_mode: str = "curated_real",
) -> None:
    """Insert a RunQualitySummaryRow for test setup."""
    row = RunQualitySummaryRow(
        summary_id=new_uuid7(),
        run_id=_to_uuid(run_id),
        workspace_id=_to_uuid(ws_id),
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


async def _seed_unresolved_claim(
    db_session: AsyncSession,
    *,
    run_id: str | UUID,
) -> None:
    """Insert a ClaimRow with NEEDS_EVIDENCE status for test setup."""
    row = ClaimRow(
        claim_id=new_uuid7(),
        run_id=_to_uuid(run_id),
        text="Needs evidence.",
        claim_type="MODEL",
        status="NEEDS_EVIDENCE",
        disclosure_tier="TIER0",
        model_refs=[],
        evidence_refs=[],
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()


WS_ID = str(uuid7())


class TestExportQualityWiring:
    """G1: Export route must pass quality_assessment into ExportOrchestrator.

    Currently the export route does NOT fetch RunQualitySummaryRow from the
    database, so quality_assessment is never passed to the orchestrator.
    These tests verify that governed exports are blocked when synthetic
    fallback data was used.
    """

    @pytest.mark.anyio
    async def test_governed_export_blocked_by_synthetic_fallback(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """Governed export with synthetic fallback quality data must be BLOCKED."""
        run_id = str(uuid7())

        # Seed quality summary with synthetic fallback
        await _seed_quality_summary(
            db_session,
            run_id=run_id,
            ws_id=WS_ID,
            used_synthetic_fallback=True,
            data_mode="synthetic_fallback",
        )

        payload = _make_export_payload(run_id, mode="GOVERNED")
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/exports", json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "BLOCKED"
        assert any("synthetic" in r.lower() for r in data["blocking_reasons"])

    @pytest.mark.anyio
    async def test_sandbox_export_ignores_synthetic_fallback(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """Sandbox export should COMPLETE even with synthetic fallback data."""
        run_id = str(uuid7())

        # Seed quality summary with synthetic fallback
        await _seed_quality_summary(
            db_session,
            run_id=run_id,
            ws_id=WS_ID,
            used_synthetic_fallback=True,
            data_mode="synthetic_fallback",
        )

        payload = _make_export_payload(run_id, mode="SANDBOX")
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/exports", json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_governed_export_blocked_by_unresolved_claims_independently(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """Governed export with unresolved claims (no synthetic fallback) must be BLOCKED."""
        run_id = str(uuid7())

        # Seed quality summary WITHOUT synthetic fallback (clean quality)
        await _seed_quality_summary(
            db_session,
            run_id=run_id,
            ws_id=WS_ID,
            used_synthetic_fallback=False,
            data_mode="curated_real",
        )

        # Seed an unresolved claim for this run
        await _seed_unresolved_claim(db_session, run_id=run_id)

        payload = _make_export_payload(run_id, mode="GOVERNED")
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/exports", json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "BLOCKED"
        assert len(data["blocking_reasons"]) >= 1

    @pytest.mark.anyio
    async def test_governed_export_succeeds_no_quality_summary(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """Governed export with no quality summary and no claims should COMPLETE."""
        run_id = str(uuid7())

        # No quality summary seeded, no claims seeded
        payload = _make_export_payload(run_id, mode="GOVERNED")
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/exports", json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "COMPLETED"
