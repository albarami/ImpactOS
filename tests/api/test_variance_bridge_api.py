"""Tests for Sprint 23 variance bridge analytics API endpoints.

POST /v1/workspaces/{ws}/variance-bridges        — compute + persist bridge
GET  /v1/workspaces/{ws}/variance-bridges/{id}   — get single bridge
GET  /v1/workspaces/{ws}/variance-bridges         — list bridges
POST /v1/workspaces/{ws}/exports/variance-bridge  — legacy endpoint (unchanged)
"""

from uuid import UUID

import pytest
from uuid_extensions import uuid7

from src.db.tables import ResultSetRow, RunSnapshotRow, WorkspaceRow
from src.models.common import utc_now

pytestmark = pytest.mark.anyio

WS = "00000000-0000-7000-8000-000000000010"
OTHER_WS = str(uuid7())

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_IDS = {
    "taxonomy_version_id": str(uuid7()),
    "concordance_version_id": str(uuid7()),
    "mapping_library_version_id": str(uuid7()),
    "assumption_library_version_id": str(uuid7()),
    "prompt_pack_version_id": str(uuid7()),
}


async def _seed_ws(session, ws_id=WS):
    """Seed a workspace row (idempotent)."""
    from sqlalchemy import select

    result = await session.execute(
        select(WorkspaceRow).where(
            WorkspaceRow.workspace_id == UUID(ws_id)
        )
    )
    if result.scalar_one_or_none() is None:
        now = utc_now()
        session.add(WorkspaceRow(
            workspace_id=UUID(ws_id),
            client_name="Test",
            engagement_code="E",
            classification="INTERNAL",
            description="",
            created_by=uuid7(),
            created_at=now,
            updated_at=now,
        ))
        await session.flush()


async def _create_run(session, *, model_version_id=None, workspace_id=WS,
                      mapping_library_version_id=None):
    """Create a RunSnapshotRow and return (run_id, model_version_id)."""
    run_id = uuid7()
    mv_id = model_version_id or uuid7()
    ml_id = mapping_library_version_id or UUID(_DUMMY_IDS["mapping_library_version_id"])
    row = RunSnapshotRow(
        run_id=run_id,
        model_version_id=mv_id if isinstance(mv_id, UUID) else UUID(mv_id),
        taxonomy_version_id=UUID(_DUMMY_IDS["taxonomy_version_id"]),
        concordance_version_id=UUID(_DUMMY_IDS["concordance_version_id"]),
        mapping_library_version_id=ml_id,
        assumption_library_version_id=UUID(
            _DUMMY_IDS["assumption_library_version_id"]
        ),
        prompt_pack_version_id=UUID(_DUMMY_IDS["prompt_pack_version_id"]),
        source_checksums=[],
        workspace_id=UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id,
        created_at=utc_now(),
    )
    session.add(row)
    await session.flush()
    return run_id, mv_id


async def _add_result(session, run_id, metric_type, values):
    """Add a ResultSetRow for a run."""
    row = ResultSetRow(
        result_id=uuid7(),
        run_id=run_id,
        metric_type=metric_type,
        values=values,
        sector_breakdowns={},
        created_at=utc_now(),
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# POST /v1/workspaces/{ws}/variance-bridges — Create
# ---------------------------------------------------------------------------


class TestCreateVarianceBridge:
    """POST create_variance_bridge endpoint."""

    async def test_create_returns_201(self, client, db_session):
        """Valid input creates bridge and returns 201."""
        await _seed_ws(db_session)
        mv = uuid7()
        run_a, _ = await _create_run(db_session, model_version_id=mv)
        run_b, _ = await _create_run(db_session, model_version_id=mv)

        await _add_result(db_session, run_a, "total_output", {"total": 1000.0})
        await _add_result(db_session, run_b, "total_output", {"total": 1200.0})

        resp = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={
                "run_a_id": str(run_a),
                "run_b_id": str(run_b),
                "metric_type": "total_output",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["run_a_id"] == str(run_a)
        assert data["run_b_id"] == str(run_b)
        assert data["metric_type"] == "total_output"
        assert data["analysis_version"] == "bridge_v1"
        assert data["start_value"] == 1000.0
        assert data["end_value"] == 1200.0
        assert data["total_variance"] == 200.0
        assert data["config_hash"].startswith("sha256:")
        assert data["result_checksum"].startswith("sha256:")
        assert "analysis_id" in data
        assert "created_at" in data

    async def test_create_with_driver_attribution(self, client, db_session):
        """When snapshots differ in mapping_library_version_id, expect MAPPING driver."""
        await _seed_ws(db_session)
        mv = uuid7()
        ml_a = uuid7()
        ml_b = uuid7()
        run_a, _ = await _create_run(
            db_session, model_version_id=mv, mapping_library_version_id=ml_a,
        )
        run_b, _ = await _create_run(
            db_session, model_version_id=mv, mapping_library_version_id=ml_b,
        )

        await _add_result(db_session, run_a, "total_output", {"total": 500.0})
        await _add_result(db_session, run_b, "total_output", {"total": 700.0})

        resp = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={
                "run_a_id": str(run_a),
                "run_b_id": str(run_b),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        driver_types = [d["driver_type"] for d in data["drivers"]]
        assert "MAPPING" in driver_types
        assert data["total_variance"] == 200.0

    async def test_create_same_run_returns_422(self, client, db_session):
        """Same run_a_id and run_b_id returns 422 BRIDGE_SAME_RUN."""
        await _seed_ws(db_session)
        run_id = uuid7()

        resp = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={
                "run_a_id": str(run_id),
                "run_b_id": str(run_id),
            },
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["reason_code"] == "BRIDGE_SAME_RUN"

    async def test_create_nonexistent_run_returns_404(self, client, db_session):
        """Nonexistent run_id returns 404 BRIDGE_RUN_NOT_FOUND."""
        await _seed_ws(db_session)
        fake_a = uuid7()
        fake_b = uuid7()

        resp = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={
                "run_a_id": str(fake_a),
                "run_b_id": str(fake_b),
            },
        )
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["reason_code"] == "BRIDGE_RUN_NOT_FOUND"

    async def test_create_run_wrong_workspace_returns_404(self, client, db_session):
        """Run in different workspace returns 404 (not 403)."""
        await _seed_ws(db_session)
        await _seed_ws(db_session, ws_id=OTHER_WS)
        mv = uuid7()
        run_a, _ = await _create_run(db_session, model_version_id=mv, workspace_id=WS)
        run_b, _ = await _create_run(
            db_session, model_version_id=mv, workspace_id=OTHER_WS,
        )

        await _add_result(db_session, run_a, "total_output", {"total": 100.0})
        await _add_result(db_session, run_b, "total_output", {"total": 200.0})

        resp = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={
                "run_a_id": str(run_a),
                "run_b_id": str(run_b),
            },
        )
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["reason_code"] == "BRIDGE_RUN_NOT_FOUND"

    async def test_create_no_results_returns_404(self, client, db_session):
        """Run exists but has no result set for metric_type -> 404."""
        await _seed_ws(db_session)
        mv = uuid7()
        run_a, _ = await _create_run(db_session, model_version_id=mv)
        run_b, _ = await _create_run(db_session, model_version_id=mv)

        # Only add result for run_a, not run_b
        await _add_result(db_session, run_a, "total_output", {"total": 100.0})

        resp = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={
                "run_a_id": str(run_a),
                "run_b_id": str(run_b),
            },
        )
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["reason_code"] == "BRIDGE_NO_RESULTS"

    async def test_create_idempotent_by_config_hash(self, client, db_session):
        """Same request twice returns same analysis_id (idempotent)."""
        await _seed_ws(db_session)
        mv = uuid7()
        run_a, _ = await _create_run(db_session, model_version_id=mv)
        run_b, _ = await _create_run(db_session, model_version_id=mv)

        await _add_result(db_session, run_a, "total_output", {"total": 100.0})
        await _add_result(db_session, run_b, "total_output", {"total": 200.0})

        payload = {
            "run_a_id": str(run_a),
            "run_b_id": str(run_b),
            "metric_type": "total_output",
        }

        resp1 = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges", json=payload,
        )
        resp2 = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges", json=payload,
        )
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["analysis_id"] == resp2.json()["analysis_id"]

    async def test_create_directional_a_b_differs_from_b_a(self, client, db_session):
        """A->B and B->A produce different config_hash values."""
        await _seed_ws(db_session)
        mv = uuid7()
        run_a, _ = await _create_run(db_session, model_version_id=mv)
        run_b, _ = await _create_run(db_session, model_version_id=mv)

        await _add_result(db_session, run_a, "total_output", {"total": 100.0})
        await _add_result(db_session, run_b, "total_output", {"total": 200.0})

        resp_ab = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={"run_a_id": str(run_a), "run_b_id": str(run_b)},
        )
        resp_ba = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={"run_a_id": str(run_b), "run_b_id": str(run_a)},
        )
        assert resp_ab.status_code == 201
        assert resp_ba.status_code == 201
        assert resp_ab.json()["config_hash"] != resp_ba.json()["config_hash"]
        assert resp_ab.json()["analysis_id"] != resp_ba.json()["analysis_id"]


# ---------------------------------------------------------------------------
# GET /v1/workspaces/{ws}/variance-bridges/{analysis_id} — Get single
# ---------------------------------------------------------------------------


class TestGetVarianceBridgeAnalysis:
    """GET single bridge analysis endpoint."""

    async def test_get_existing_bridge_returns_200(self, client, db_session):
        """Retrieve a previously created bridge by analysis_id."""
        await _seed_ws(db_session)
        mv = uuid7()
        run_a, _ = await _create_run(db_session, model_version_id=mv)
        run_b, _ = await _create_run(db_session, model_version_id=mv)

        await _add_result(db_session, run_a, "total_output", {"total": 300.0})
        await _add_result(db_session, run_b, "total_output", {"total": 500.0})

        create_resp = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={"run_a_id": str(run_a), "run_b_id": str(run_b)},
        )
        assert create_resp.status_code == 201
        analysis_id = create_resp.json()["analysis_id"]

        get_resp = await client.get(
            f"/v1/workspaces/{WS}/variance-bridges/{analysis_id}",
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["analysis_id"] == analysis_id
        assert data["start_value"] == 300.0
        assert data["end_value"] == 500.0
        assert data["total_variance"] == 200.0

    async def test_get_nonexistent_bridge_returns_404(self, client, db_session):
        """Nonexistent analysis_id returns 404."""
        await _seed_ws(db_session)
        fake_id = uuid7()

        resp = await client.get(
            f"/v1/workspaces/{WS}/variance-bridges/{fake_id}",
        )
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["reason_code"] == "BRIDGE_NOT_FOUND"

    async def test_get_bridge_wrong_workspace_returns_404(self, client, db_session):
        """Bridge created in WS, fetched with OTHER_WS returns 404 (not 403)."""
        await _seed_ws(db_session)
        mv = uuid7()
        run_a, _ = await _create_run(db_session, model_version_id=mv)
        run_b, _ = await _create_run(db_session, model_version_id=mv)

        await _add_result(db_session, run_a, "total_output", {"total": 100.0})
        await _add_result(db_session, run_b, "total_output", {"total": 200.0})

        create_resp = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={"run_a_id": str(run_a), "run_b_id": str(run_b)},
        )
        assert create_resp.status_code == 201
        analysis_id = create_resp.json()["analysis_id"]

        # Fetch with a different workspace_id
        resp = await client.get(
            f"/v1/workspaces/{OTHER_WS}/variance-bridges/{analysis_id}",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/workspaces/{ws}/variance-bridges — List
# ---------------------------------------------------------------------------


class TestListVarianceBridges:
    """GET list variance bridges endpoint."""

    async def test_list_returns_200_with_bridges(self, client, db_session):
        """List bridges for a workspace returns 200."""
        await _seed_ws(db_session)
        mv = uuid7()
        run_a, _ = await _create_run(db_session, model_version_id=mv)
        run_b, _ = await _create_run(db_session, model_version_id=mv)

        await _add_result(db_session, run_a, "total_output", {"total": 100.0})
        await _add_result(db_session, run_b, "total_output", {"total": 200.0})

        await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={"run_a_id": str(run_a), "run_b_id": str(run_b)},
        )

        resp = await client.get(f"/v1/workspaces/{WS}/variance-bridges")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_list_empty_workspace_returns_200_empty(self, client, db_session):
        """Workspace with no bridges returns 200 with empty list."""
        await _seed_ws(db_session, ws_id=OTHER_WS)

        resp = await client.get(f"/v1/workspaces/{OTHER_WS}/variance-bridges")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Legacy endpoint — POST /v1/workspaces/{ws}/exports/variance-bridge
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# I-2: Scenario spec integration tests
# ---------------------------------------------------------------------------


class TestScenarioSpecIntegration:
    """I-2: scenario_spec_id stored on runs and available to bridge engine."""

    async def test_run_snapshot_stores_scenario_spec_id(self, db_session):
        """RunSnapshotRow accepts and stores scenario_spec_id/version."""
        await _seed_ws(db_session)
        run_id = uuid7()
        spec_id = uuid7()
        row = RunSnapshotRow(
            run_id=run_id,
            model_version_id=uuid7(),
            taxonomy_version_id=UUID(_DUMMY_IDS["taxonomy_version_id"]),
            concordance_version_id=UUID(_DUMMY_IDS["concordance_version_id"]),
            mapping_library_version_id=UUID(_DUMMY_IDS["mapping_library_version_id"]),
            assumption_library_version_id=UUID(_DUMMY_IDS["assumption_library_version_id"]),
            prompt_pack_version_id=UUID(_DUMMY_IDS["prompt_pack_version_id"]),
            source_checksums=[],
            workspace_id=UUID(WS),
            scenario_spec_id=spec_id,
            scenario_spec_version=3,
            created_at=utc_now(),
        )
        db_session.add(row)
        await db_session.flush()
        loaded = await db_session.get(RunSnapshotRow, run_id)
        assert loaded.scenario_spec_id == spec_id
        assert loaded.scenario_spec_version == 3

    async def test_run_snapshot_backward_compat_no_spec(self, db_session):
        """Runs created without scenario_spec_id still work (None)."""
        await _seed_ws(db_session)
        run_id, _ = await _create_run(db_session)
        loaded = await db_session.get(RunSnapshotRow, run_id)
        assert loaded.scenario_spec_id is None
        assert loaded.scenario_spec_version is None


class TestLegacyVarianceBridge:
    """Legacy variance bridge endpoint must remain unchanged."""

    async def test_legacy_endpoint_still_works(self, client):
        """POST /exports/variance-bridge returns 200 with valid input."""
        resp = await client.post(
            f"/v1/workspaces/{WS}/exports/variance-bridge",
            json={
                "run_a": {
                    "total_impact": 1000.0,
                    "phasing": {"2024": 0.5, "2025": 0.5},
                    "import_shares": {"A": 0.3},
                    "mapping_count": 10,
                    "constraints_active": 2,
                    "model_version": "v1",
                },
                "run_b": {
                    "total_impact": 1200.0,
                    "phasing": {"2024": 0.4, "2025": 0.6},
                    "import_shares": {"A": 0.3},
                    "mapping_count": 12,
                    "constraints_active": 2,
                    "model_version": "v1",
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["start_value"] == 1000.0
        assert data["end_value"] == 1200.0
        assert data["total_variance"] == 200.0
        assert len(data["drivers"]) > 0
