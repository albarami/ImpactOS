"""Tests for FastAPI export endpoints (MVP-6).

Covers: POST create export, GET export status, POST variance bridge.
S0-4: Workspace-scoped routes.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

from src.db.tables import RunQualitySummaryRow, RunSnapshotRow
from src.models.common import new_uuid7, utc_now

WS_ID = str(uuid7())


async def _seed_run_snapshot(db_session, run_id: str, workspace_id: str):
    """Seed ModelVersionRow + RunSnapshotRow so provenance check passes."""
    from src.db.tables import ModelVersionRow
    mid = uuid7()
    mv = ModelVersionRow(
        model_version_id=mid, base_year=2023, source="test",
        sector_count=2, checksum="sha256:" + "a" * 64,
        provenance_class="curated_real", created_at=utc_now(),
    )
    db_session.add(mv)
    row = RunSnapshotRow(
        run_id=UUID(run_id),
        model_version_id=mid,
        taxonomy_version_id=uuid7(),
        concordance_version_id=uuid7(),
        mapping_library_version_id=uuid7(),
        assumption_library_version_id=uuid7(),
        prompt_pack_version_id=uuid7(),
        workspace_id=UUID(workspace_id),
        source_checksums=[],
        created_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()


def _make_export_payload(*, run_id: str | None = None) -> dict:
    rid = run_id or str(uuid7())
    return {
        "run_id": rid,
        "mode": "SANDBOX",
        "export_formats": ["excel"],
        "pack_data": {
            "run_id": rid,
            "scenario_name": "Test Scenario",
            "base_year": 2023,
            "currency": "SAR",
            "model_version_id": str(uuid7()),
            "scenario_version": 1,
            "executive_summary": {"headline_gdp": 4.2e9, "headline_jobs": 21200},
            "sector_impacts": [
                {"sector_code": "C41", "sector_name": "Steel", "direct_impact": 500.0,
                 "indirect_impact": 250.0, "total_impact": 750.0, "multiplier": 1.5,
                 "domestic_share": 0.65, "import_leakage": 0.35},
            ],
            "input_vectors": {"C41": 1000.0},
            "sensitivity": [],
            "assumptions": [],
            "evidence_ledger": [],
        },
    }


class TestCreateExport:
    @pytest.mark.anyio
    async def test_create_returns_201(self, client: AsyncClient) -> None:
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=_make_export_payload())
        assert response.status_code == 201

    @pytest.mark.anyio
    async def test_create_returns_export_id(self, client: AsyncClient) -> None:
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=_make_export_payload())
        data = response.json()
        assert "export_id" in data
        assert "status" in data

    @pytest.mark.anyio
    async def test_create_sandbox_succeeds(self, client: AsyncClient, db_session) -> None:
        run_id = str(uuid7())
        await _seed_run_snapshot(db_session, run_id, WS_ID)
        quality_row = RunQualitySummaryRow(
            summary_id=new_uuid7(),
            run_id=UUID(run_id),
            workspace_id=UUID(WS_ID),
            overall_run_score=0.8,
            overall_run_grade="B",
            coverage_pct=0.9,
            publication_gate_pass=True,
            publication_gate_mode="ADVISORY",
            payload={"assessment_version": 1, "used_synthetic_fallback": False, "data_mode": "curated_real"},
            created_at=utc_now(),
        )
        db_session.add(quality_row)
        await db_session.flush()

        payload = _make_export_payload(run_id=run_id)
        payload["mode"] = "SANDBOX"
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=payload)
        data = response.json()
        assert data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_create_with_pptx_format(self, client: AsyncClient, db_session) -> None:
        run_id = str(uuid7())
        await _seed_run_snapshot(db_session, run_id, WS_ID)
        quality_row = RunQualitySummaryRow(
            summary_id=new_uuid7(),
            run_id=UUID(run_id),
            workspace_id=UUID(WS_ID),
            overall_run_score=0.8,
            overall_run_grade="B",
            coverage_pct=0.9,
            publication_gate_pass=True,
            publication_gate_mode="ADVISORY",
            payload={"assessment_version": 1, "used_synthetic_fallback": False, "data_mode": "curated_real"},
            created_at=utc_now(),
        )
        db_session.add(quality_row)
        await db_session.flush()

        payload = _make_export_payload(run_id=run_id)
        payload["export_formats"] = ["pptx"]
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=payload)
        data = response.json()
        assert data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_create_returns_checksums(self, client: AsyncClient) -> None:
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=_make_export_payload())
        data = response.json()
        assert "checksums" in data


class TestGetExportStatus:
    @pytest.mark.anyio
    async def test_get_status_returns_200(self, client: AsyncClient, db_session) -> None:
        run_id = str(uuid7())
        await _seed_run_snapshot(db_session, run_id, WS_ID)
        payload = _make_export_payload(run_id=run_id)
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=payload)
        export_id = create_resp.json()["export_id"]
        response = await client.get(f"/v1/workspaces/{WS_ID}/exports/{export_id}")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_get_status_contains_fields(self, client: AsyncClient, db_session) -> None:
        run_id = str(uuid7())
        await _seed_run_snapshot(db_session, run_id, WS_ID)
        payload = _make_export_payload(run_id=run_id)
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=payload)
        export_id = create_resp.json()["export_id"]
        response = await client.get(f"/v1/workspaces/{WS_ID}/exports/{export_id}")
        data = response.json()
        assert "export_id" in data
        assert "status" in data
        assert "mode" in data

    @pytest.mark.anyio
    async def test_get_nonexistent_returns_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/v1/workspaces/{WS_ID}/exports/{uuid7()}")
        assert response.status_code == 404


class TestVarianceBridge:
    @pytest.mark.anyio
    async def test_bridge_returns_200(self, client: AsyncClient) -> None:
        payload = {
            "run_a": {
                "run_id": str(uuid7()),
                "total_impact": 4_200_000_000.0,
                "phasing": {"2026": 0.3, "2027": 0.4, "2028": 0.3},
                "import_shares": {"C41": 0.35},
                "mapping_count": 50,
                "constraints_active": 0,
                "model_version": "v1",
            },
            "run_b": {
                "run_id": str(uuid7()),
                "total_impact": 4_500_000_000.0,
                "phasing": {"2026": 0.5, "2027": 0.3, "2028": 0.2},
                "import_shares": {"C41": 0.35},
                "mapping_count": 50,
                "constraints_active": 0,
                "model_version": "v1",
            },
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports/variance-bridge", json=payload)
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_bridge_returns_waterfall(self, client: AsyncClient) -> None:
        payload = {
            "run_a": {
                "run_id": str(uuid7()),
                "total_impact": 4_200_000_000.0,
                "phasing": {"2026": 0.3},
                "import_shares": {},
                "mapping_count": 50,
                "constraints_active": 0,
                "model_version": "v1",
            },
            "run_b": {
                "run_id": str(uuid7()),
                "total_impact": 4_500_000_000.0,
                "phasing": {"2026": 0.3},
                "import_shares": {},
                "mapping_count": 50,
                "constraints_active": 0,
                "model_version": "v2",
            },
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports/variance-bridge", json=payload)
        data = response.json()
        assert "start_value" in data
        assert "end_value" in data
        assert "total_variance" in data
        assert "drivers" in data
