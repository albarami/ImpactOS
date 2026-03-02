"""D-5.1 API provenance gate tests.

TDD: runtime endpoints reject models without curated_real provenance.
Export gate uses effective_used_synthetic (quality flag OR model provenance).
"""

import hashlib

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.db.tables import (
    ModelDataRow,
    ModelVersionRow,
    RunQualitySummaryRow,
    RunSnapshotRow,
    ScenarioSpecRow,
)
from src.models.common import new_uuid7, utc_now

WS_ID = uuid7()
N = 3
SECTOR_CODES = ["A", "B", "C"]
Z = np.eye(N, dtype=np.float64) * 0.1
X = np.ones(N, dtype=np.float64) * 100.0
SAT = {"jobs_coeff": [0.1] * N, "import_ratio": [0.2] * N, "va_ratio": [0.5] * N}


async def _seed_model(db_session, *, provenance_class="unknown"):
    mid = uuid7()
    hasher = hashlib.sha256()
    hasher.update(Z.tobytes())
    hasher.update(X.tobytes())
    checksum = f"sha256:{hasher.hexdigest()}"
    mv = ModelVersionRow(
        model_version_id=mid, base_year=2023, source="test",
        sector_count=N, checksum=checksum,
        provenance_class=provenance_class, created_at=utc_now(),
    )
    db_session.add(mv)
    md = ModelDataRow(
        model_version_id=mid, z_matrix_json=Z.tolist(),
        x_vector_json=X.tolist(), sector_codes=SECTOR_CODES,
        storage_format="json",
    )
    db_session.add(md)
    await db_session.flush()
    return mid


async def _seed_scenario(db_session, *, model_id, compiled=True):
    sid = uuid7()
    shock_items = []
    if compiled:
        shock_items = [{
            "type": "FINAL_DEMAND_SHOCK", "sector_code": "A",
            "year": 2024, "amount_real_base_year": 1000.0,
            "domestic_share": 0.65, "import_share": 0.35,
            "evidence_refs": [],
        }]
    row = ScenarioSpecRow(
        scenario_spec_id=sid, version=1, name="Test",
        workspace_id=WS_ID, disclosure_tier="TIER0",
        base_model_version_id=model_id, currency="SAR",
        base_year=2023, time_horizon={"start_year": 2024, "end_year": 2025},
        shock_items=shock_items, assumption_ids=[], is_locked=False,
        created_at=utc_now(), updated_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()
    return sid


async def _seed_run_and_quality(db_session, *, model_id):
    """Seed run snapshot + quality summary (used_synthetic_fallback=False)."""
    run_id = uuid7()
    snap = RunSnapshotRow(
        run_id=run_id, model_version_id=model_id,
        taxonomy_version_id=uuid7(), concordance_version_id=uuid7(),
        mapping_library_version_id=uuid7(),
        assumption_library_version_id=uuid7(),
        prompt_pack_version_id=uuid7(),
        workspace_id=WS_ID, source_checksums=[], created_at=utc_now(),
    )
    db_session.add(snap)
    qual = RunQualitySummaryRow(
        summary_id=new_uuid7(), run_id=run_id, workspace_id=WS_ID,
        overall_run_score=0.8, overall_run_grade="B",
        coverage_pct=0.9, publication_gate_pass=True,
        publication_gate_mode="PASS",
        summary_version="1.0.0", summary_hash="",
        payload={
            "assessment_version": 1,
            "used_synthetic_fallback": False,
            "data_mode": "curated_real",
        },
        created_at=utc_now(),
    )
    db_session.add(qual)
    await db_session.flush()
    return run_id


class TestRunRejectsNonCuratedModel:
    """POST /engine/runs rejects synthetic/unknown/curated_estimated."""

    @pytest.mark.anyio
    async def test_run_rejects_unknown(self, client, db_session):
        mid = await _seed_model(db_session, provenance_class="unknown")
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": str(mid),
                "annual_shocks": {"2024": [1.0] * N},
                "base_year": 2023,
                "satellite_coefficients": SAT,
            },
        )
        assert resp.status_code == 409
        assert "provenance_class" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_run_rejects_synthetic(self, client, db_session):
        mid = await _seed_model(db_session, provenance_class="synthetic")
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": str(mid),
                "annual_shocks": {"2024": [1.0] * N},
                "base_year": 2023,
                "satellite_coefficients": SAT,
            },
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_run_rejects_curated_estimated(self, client, db_session):
        mid = await _seed_model(
            db_session, provenance_class="curated_estimated",
        )
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": str(mid),
                "annual_shocks": {"2024": [1.0] * N},
                "base_year": 2023,
                "satellite_coefficients": SAT,
            },
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_run_allows_curated_real(self, client, db_session):
        mid = await _seed_model(
            db_session, provenance_class="curated_real",
        )
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": str(mid),
                "annual_shocks": {"2024": [1.0] * N},
                "base_year": 2023,
                "satellite_coefficients": SAT,
            },
        )
        assert resp.status_code == 200


class TestScenarioRunRejectsNonCurated:
    """POST /scenarios/{id}/run rejects non-curated_real models."""

    @pytest.mark.anyio
    async def test_scenario_run_rejects_unknown(self, client, db_session):
        mid = await _seed_model(db_session, provenance_class="unknown")
        sid = await _seed_scenario(db_session, model_id=mid)
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{sid}/run",
            json={"mode": "SANDBOX", "satellite_coefficients": SAT},
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_scenario_run_allows_curated_real(
        self, client, db_session,
    ):
        mid = await _seed_model(
            db_session, provenance_class="curated_real",
        )
        sid = await _seed_scenario(db_session, model_id=mid)
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{sid}/run",
            json={"mode": "SANDBOX", "satellite_coefficients": SAT},
        )
        assert resp.status_code == 200


class TestBatchRunRejectsNonCurated:
    """POST /engine/batch rejects non-curated_real models."""

    @pytest.mark.anyio
    async def test_batch_rejects_unknown(self, client, db_session):
        mid = await _seed_model(db_session, provenance_class="unknown")
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/batch",
            json={
                "model_version_id": str(mid),
                "scenarios": [{
                    "name": "test",
                    "annual_shocks": {"2024": [1.0] * N},
                    "base_year": 2023,
                }],
                "satellite_coefficients": SAT,
            },
        )
        assert resp.status_code == 409


class TestExportTamperResistant:
    """Export blocked when model provenance is disallowed,
    even if quality payload says used_synthetic_fallback=False."""

    @pytest.mark.anyio
    async def test_export_blocked_despite_clean_quality(
        self, client, db_session,
    ):
        mid = await _seed_model(db_session, provenance_class="unknown")
        run_id = await _seed_run_and_quality(db_session, model_id=mid)

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/exports",
            json={
                "run_id": str(run_id),
                "mode": "SANDBOX",
                "export_formats": ["excel"],
                "pack_data": {},
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "BLOCKED"
        assert any(
            "provenance" in r.lower() for r in body["blocking_reasons"]
        )

    @pytest.mark.anyio
    async def test_export_allowed_with_curated_real(
        self, client, db_session,
    ):
        mid = await _seed_model(
            db_session, provenance_class="curated_real",
        )
        run_id = await _seed_run_and_quality(db_session, model_id=mid)

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/exports",
            json={
                "run_id": str(run_id),
                "mode": "SANDBOX",
                "export_formats": ["excel"],
                "pack_data": {},
            },
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "COMPLETED"


class TestMigrationBackwardCompat:
    """Existing models get provenance_class=unknown (blocked at runtime)."""

    @pytest.mark.anyio
    async def test_default_provenance_is_unknown(self, db_session):
        mid = uuid7()
        row = ModelVersionRow(
            model_version_id=mid, base_year=2023, source="legacy",
            sector_count=3, checksum="sha256:abc", created_at=utc_now(),
        )
        db_session.add(row)
        await db_session.flush()
        await db_session.refresh(row)
        assert row.provenance_class == "unknown"
