"""B-16: Tests for run-from-scenario convenience endpoint.

TDD — tests written before endpoint implementation.
Tests cover: success (compiled), uncompiled (409), wrong workspace (404),
governed+unlocked (409), governed+locked (200), and deterministic shape checks.
"""

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.db.tables import (
    ModelDataRow,
    ModelVersionRow,
    ScenarioSpecRow,
)
from src.models.common import utc_now

WS_ID = uuid7()
OTHER_WS_ID = uuid7()


SECTOR_CODES = ["A", "B", "C"]
N = len(SECTOR_CODES)
Z_MATRIX = np.eye(N, dtype=np.float64) * 0.1
X_VECTOR = np.ones(N, dtype=np.float64) * 100.0

SATELLITE_COEFFICIENTS = {
    "jobs_coeff": [0.1] * N,
    "import_ratio": [0.2] * N,
    "va_ratio": [0.5] * N,
}


async def _seed_model(db_session):
    """Seed a registered I-O model for engine runs."""
    import hashlib
    mid = uuid7()
    z = Z_MATRIX
    x = X_VECTOR
    hasher = hashlib.sha256()
    hasher.update(z.tobytes())
    hasher.update(x.tobytes())
    checksum = f"sha256:{hasher.hexdigest()}"

    mv = ModelVersionRow(
        model_version_id=mid, base_year=2023, source="test",
        sector_count=N, checksum=checksum,
        provenance_class="curated_real", created_at=utc_now(),
    )
    db_session.add(mv)

    md = ModelDataRow(
        model_version_id=mid,
        z_matrix_json=z.tolist(),
        x_vector_json=x.tolist(),
        sector_codes=SECTOR_CODES,
        storage_format="json",
    )
    db_session.add(md)
    await db_session.flush()
    return mid


async def _seed_scenario(
    db_session, *, workspace_id=WS_ID, model_version_id=None,
    compiled=True, is_locked=False,
):
    """Seed a scenario spec with optional shock items."""
    sid = uuid7()
    shock_items = []
    if compiled:
        shock_items = [{
            "type": "FINAL_DEMAND_SHOCK",
            "sector_code": "A",
            "year": 2024,
            "amount_real_base_year": 1000.0,
            "domestic_share": 0.65,
            "import_share": 0.35,
            "evidence_refs": [],
        }]

    row = ScenarioSpecRow(
        scenario_spec_id=sid,
        version=1,
        name="Test Scenario",
        workspace_id=workspace_id,
        disclosure_tier="TIER0",
        base_model_version_id=model_version_id or uuid7(),
        currency="SAR",
        base_year=2023,
        time_horizon={"start_year": 2024, "end_year": 2025},
        shock_items=shock_items,
        assumption_ids=[],
        is_locked=is_locked,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()
    return sid


class TestRunFromScenario:
    """B-16: POST /v1/workspaces/{ws}/scenarios/{sid}/run."""

    @pytest.mark.anyio
    async def test_run_from_compiled_scenario_success(self, client, db_session):
        model_id = await _seed_model(db_session)
        scenario_id = await _seed_scenario(
            db_session, compiled=True, model_version_id=model_id,
        )

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/run",
            json={
                "mode": "SANDBOX",
                "satellite_coefficients": SATELLITE_COEFFICIENTS,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "run_id" in body
        assert "result_sets" in body
        assert len(body["result_sets"]) > 0

    @pytest.mark.anyio
    async def test_run_from_uncompiled_scenario_returns_409(self, client, db_session):
        model_id = await _seed_model(db_session)
        scenario_id = await _seed_scenario(
            db_session, compiled=False, model_version_id=model_id,
        )

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/run",
            json={
                "mode": "SANDBOX",
                "satellite_coefficients": SATELLITE_COEFFICIENTS,
            },
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_run_from_wrong_workspace_returns_404(self, client, db_session):
        model_id = await _seed_model(db_session)
        scenario_id = await _seed_scenario(
            db_session, workspace_id=OTHER_WS_ID, compiled=True,
            model_version_id=model_id,
        )

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/run",
            json={
                "mode": "SANDBOX",
                "satellite_coefficients": SATELLITE_COEFFICIENTS,
            },
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_governed_mode_unlocked_returns_409(self, client, db_session):
        model_id = await _seed_model(db_session)
        scenario_id = await _seed_scenario(
            db_session, compiled=True, is_locked=False,
            model_version_id=model_id,
        )

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/run",
            json={
                "mode": "GOVERNED",
                "satellite_coefficients": SATELLITE_COEFFICIENTS,
            },
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_governed_mode_locked_succeeds(self, client, db_session):
        model_id = await _seed_model(db_session)
        scenario_id = await _seed_scenario(
            db_session, compiled=True, is_locked=True,
            model_version_id=model_id,
        )

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/run",
            json={
                "mode": "GOVERNED",
                "satellite_coefficients": SATELLITE_COEFFICIENTS,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "run_id" in body
        assert "result_sets" in body

    @pytest.mark.anyio
    async def test_result_sets_have_expected_metrics(self, client, db_session):
        """Deterministic shape check: result_sets include standard metric types."""
        model_id = await _seed_model(db_session)
        scenario_id = await _seed_scenario(
            db_session, compiled=True, model_version_id=model_id,
        )

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/run",
            json={
                "mode": "SANDBOX",
                "satellite_coefficients": SATELLITE_COEFFICIENTS,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        metric_types = {rs["metric_type"] for rs in body["result_sets"]}
        assert "total_output" in metric_types
        assert "employment" in metric_types


class TestScenarioLockPersistence:
    """Lock state persistence tests."""

    @pytest.mark.anyio
    async def test_lock_endpoint_persists_is_locked(self, client, db_session):
        """Lock endpoint must set is_locked=True on the new version."""
        model_id = await _seed_model(db_session)
        scenario_id = await _seed_scenario(
            db_session, compiled=True, model_version_id=model_id,
        )

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/lock",
            json={"actor": str(uuid7())},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "locked"

        detail = await client.get(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}",
        )
        assert detail.status_code == 200
        assert detail.json()["status"] == "LOCKED"

    @pytest.mark.anyio
    async def test_compile_after_lock_resets_lock(self, client, db_session):
        """Compiling after lock creates a new unlocked version (mutable)."""
        model_id = await _seed_model(db_session)
        scenario_id = await _seed_scenario(
            db_session, compiled=True, is_locked=True,
            model_version_id=model_id,
        )

        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/compile",
            json={
                "line_items": [{
                    "line_item_id": str(uuid7()),
                    "description": "Test item",
                    "total_value": 500.0,
                }],
                "decisions": [{
                    "line_item_id": str(uuid7()),
                    "final_sector_code": "A",
                    "decision_type": "APPROVED",
                    "decided_by": str(uuid7()),
                }],
                "phasing": {"2024": 0.5, "2025": 0.5},
            },
        )
        assert resp.status_code == 200

        detail = await client.get(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}",
        )
        assert detail.status_code == 200
        assert detail.json()["status"] != "LOCKED"
