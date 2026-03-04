"""Tests for path analytics API endpoints — Sprint 20."""

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from uuid_extensions import uuid7

from src.db.session import get_async_session
from src.db.tables import (
    ModelDataRow,
    ModelVersionRow,
    ResultSetRow,
    RunSnapshotRow,
    WorkspaceRow,
)
from src.engine.model_store import compute_model_checksum
from src.models.common import utc_now

pytestmark = pytest.mark.anyio

WS_ID = uuid7()
OTHER_WS_ID = uuid7()

SECTOR_CODES = ["A", "B", "C"]
N = len(SECTOR_CODES)
Z_MATRIX = np.eye(N, dtype=np.float64) * 0.1
X_VECTOR = np.ones(N, dtype=np.float64) * 100.0


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_workspace(session, workspace_id):
    ws = WorkspaceRow(
        workspace_id=workspace_id,
        client_name="Test",
        engagement_code="T-001",
        classification="INTERNAL",
        description="test",
        created_by=uuid7(),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(ws)
    await session.flush()
    return ws


async def _seed_model(session):
    mid = uuid7()
    z = Z_MATRIX
    x = X_VECTOR
    checksum = compute_model_checksum(z, x, {})
    mv = ModelVersionRow(
        model_version_id=mid,
        base_year=2023,
        source="test",
        sector_count=N,
        checksum=checksum,
        provenance_class="curated_real",
        created_at=utc_now(),
    )
    session.add(mv)
    md = ModelDataRow(
        model_version_id=mid,
        z_matrix_json=z.tolist(),
        x_vector_json=x.tolist(),
        sector_codes=SECTOR_CODES,
        storage_format="json",
    )
    session.add(md)
    await session.flush()
    return mid


async def _seed_run(session, model_version_id, workspace_id):
    run_id = uuid7()
    snap = RunSnapshotRow(
        run_id=run_id,
        model_version_id=model_version_id,
        taxonomy_version_id=uuid7(),
        concordance_version_id=uuid7(),
        mapping_library_version_id=uuid7(),
        assumption_library_version_id=uuid7(),
        prompt_pack_version_id=uuid7(),
        workspace_id=workspace_id,
        source_checksums=[],
        created_at=utc_now(),
    )
    session.add(snap)
    await session.flush()
    return run_id


async def _seed_direct_effect(session, run_id, workspace_id):
    values = {"A": 100.0, "B": 0.0, "C": 0.0}
    result_id = uuid7()
    rs = ResultSetRow(
        result_id=result_id,
        run_id=run_id,
        metric_type="direct_effect",
        values=values,
        sector_breakdowns={},
        workspace_id=workspace_id,
        created_at=utc_now(),
    )
    session.add(rs)
    await session.flush()
    return result_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def seeded(db_session):
    """Seed workspace, model, run, and direct_effect for the happy path."""
    await _seed_workspace(db_session, WS_ID)
    model_id = await _seed_model(db_session)
    run_id = await _seed_run(db_session, model_id, WS_ID)
    await _seed_direct_effect(db_session, run_id, WS_ID)
    return {"model_id": model_id, "run_id": run_id}


@pytest.fixture
async def seeded_two_workspaces(db_session):
    """Seed two workspaces with separate runs for isolation tests."""
    await _seed_workspace(db_session, WS_ID)
    await _seed_workspace(db_session, OTHER_WS_ID)
    model_id = await _seed_model(db_session)
    run_id = await _seed_run(db_session, model_id, WS_ID)
    await _seed_direct_effect(db_session, run_id, WS_ID)
    other_run_id = await _seed_run(db_session, model_id, OTHER_WS_ID)
    await _seed_direct_effect(db_session, other_run_id, OTHER_WS_ID)
    return {
        "model_id": model_id,
        "run_id": run_id,
        "other_run_id": other_run_id,
    }


@pytest.fixture
async def unauthed_client(db_session):
    """AsyncClient that does NOT override auth deps (requires real token)."""
    from src.api.main import app

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_async_session] = _override_session
    # Do NOT override auth - let it require real tokens
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


async def test_post_creates_analysis_201(client, seeded, db_session):
    """Full happy path — POST creates analysis and returns 201."""
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": str(seeded["run_id"]), "config": {"max_depth": 3, "top_k": 10}},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "analysis_id" in body
    assert body["run_id"] == str(seeded["run_id"])
    assert body["analysis_version"] == "spa_v1"
    assert body["config"]["max_depth"] == 3
    assert body["config"]["top_k"] == 10
    assert "config_hash" in body
    assert "top_paths" in body
    assert "chokepoints" in body
    assert "depth_contributions" in body
    assert "coverage_ratio" in body
    assert "result_checksum" in body
    assert "created_at" in body


async def test_post_idempotent_returns_200(client, seeded, db_session):
    """Second POST with same config returns 200 with same analysis_id."""
    payload = {
        "run_id": str(seeded["run_id"]),
        "config": {"max_depth": 3, "top_k": 10},
    }
    r1 = await client.post(f"/v1/workspaces/{WS_ID}/path-analytics", json=payload)
    assert r1.status_code == 201
    aid1 = r1.json()["analysis_id"]

    r2 = await client.post(f"/v1/workspaces/{WS_ID}/path-analytics", json=payload)
    assert r2.status_code == 200
    assert r2.json()["analysis_id"] == aid1


async def test_get_by_id_200(client, seeded, db_session):
    """Create then GET by ID returns 200."""
    r1 = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": str(seeded["run_id"])},
    )
    assert r1.status_code == 201
    aid = r1.json()["analysis_id"]

    r2 = await client.get(f"/v1/workspaces/{WS_ID}/path-analytics/{aid}")
    assert r2.status_code == 200
    assert r2.json()["analysis_id"] == aid


async def test_list_by_run_200(client, seeded, db_session):
    """Create two analyses with different configs, list returns both."""
    run_id = str(seeded["run_id"])
    r1 = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": run_id, "config": {"max_depth": 2, "top_k": 5}},
    )
    assert r1.status_code == 201

    r2 = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": run_id, "config": {"max_depth": 4, "top_k": 10}},
    )
    assert r2.status_code == 201

    r3 = await client.get(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        params={"run_id": run_id},
    )
    assert r3.status_code == 200
    body = r3.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


async def test_list_by_run_pagination(client, seeded, db_session):
    """limit=1 returns 1 item with total=2."""
    run_id = str(seeded["run_id"])
    await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": run_id, "config": {"max_depth": 2, "top_k": 5}},
    )
    await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": run_id, "config": {"max_depth": 4, "top_k": 10}},
    )

    r = await client.get(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        params={"run_id": run_id, "limit": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1


# ---------------------------------------------------------------------------
# Error precedence
# ---------------------------------------------------------------------------


async def test_post_wrong_workspace_run_404(client, seeded_two_workspaces, db_session):
    """Run belongs to different workspace -> 404 SPA_RUN_NOT_FOUND."""
    other_run_id = str(seeded_two_workspaces["other_run_id"])
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": other_run_id},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["reason_code"] == "SPA_RUN_NOT_FOUND"


async def test_post_run_not_found_404(client, seeded, db_session):
    """Nonexistent run_id -> 404 SPA_RUN_NOT_FOUND."""
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": str(uuid7())},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["reason_code"] == "SPA_RUN_NOT_FOUND"


async def test_post_no_direct_effect_422(client, db_session):
    """Run exists but no direct_effect ResultSet -> 422 SPA_MISSING_DIRECT_EFFECT."""
    await _seed_workspace(db_session, WS_ID)
    mid = await _seed_model(db_session)
    run_id = await _seed_run(db_session, mid, WS_ID)
    # Seed a non-direct-effect result set instead
    rs = ResultSetRow(
        result_id=uuid7(),
        run_id=run_id,
        metric_type="output_multiplier",
        values={"A": 1.0},
        sector_breakdowns={},
        workspace_id=WS_ID,
        created_at=utc_now(),
    )
    db_session.add(rs)
    await db_session.flush()

    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": str(run_id)},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "SPA_MISSING_DIRECT_EFFECT"


async def test_post_no_results_422(client, db_session):
    """Run exists but zero ResultSets -> 422 SPA_MISSING_DIRECT_EFFECT."""
    await _seed_workspace(db_session, WS_ID)
    mid = await _seed_model(db_session)
    run_id = await _seed_run(db_session, mid, WS_ID)
    # No result sets at all

    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": str(run_id)},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "SPA_MISSING_DIRECT_EFFECT"


async def test_post_model_data_unavailable_422(client, db_session):
    """model_version exists but no model_data row -> 422 SPA_MODEL_DATA_UNAVAILABLE."""
    await _seed_workspace(db_session, WS_ID)
    # Seed model version WITHOUT model data
    mid = uuid7()
    z = Z_MATRIX
    x = X_VECTOR
    checksum = compute_model_checksum(z, x, {})
    mv = ModelVersionRow(
        model_version_id=mid,
        base_year=2023,
        source="test",
        sector_count=N,
        checksum=checksum,
        provenance_class="curated_real",
        created_at=utc_now(),
    )
    db_session.add(mv)
    await db_session.flush()
    # No ModelDataRow

    run_id = await _seed_run(db_session, mid, WS_ID)
    await _seed_direct_effect(db_session, run_id, WS_ID)

    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": str(run_id)},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "SPA_MODEL_DATA_UNAVAILABLE"


async def test_post_invalid_config_max_depth_422(client, seeded, db_session):
    """max_depth=13 -> 422 SPA_INVALID_CONFIG."""
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={
            "run_id": str(seeded["run_id"]),
            "config": {"max_depth": 13, "top_k": 10},
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "SPA_INVALID_CONFIG"


async def test_post_invalid_config_top_k_422(client, seeded, db_session):
    """top_k=0 -> 422 SPA_INVALID_CONFIG."""
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={
            "run_id": str(seeded["run_id"]),
            "config": {"max_depth": 6, "top_k": 0},
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "SPA_INVALID_CONFIG"


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


async def test_get_by_id_wrong_workspace_404(client, seeded_two_workspaces, db_session):
    """Analysis exists but wrong workspace -> 404."""
    run_id = str(seeded_two_workspaces["run_id"])
    r1 = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": run_id},
    )
    assert r1.status_code == 201
    aid = r1.json()["analysis_id"]

    r2 = await client.get(f"/v1/workspaces/{OTHER_WS_ID}/path-analytics/{aid}")
    assert r2.status_code == 404


async def test_list_by_run_wrong_workspace_empty(client, seeded_two_workspaces, db_session):
    """Run in workspace A, list from workspace B -> empty (404 because run not in B)."""
    run_id = str(seeded_two_workspaces["run_id"])
    r1 = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": run_id},
    )
    assert r1.status_code == 201

    # Listing from OTHER workspace for a run that's in WS -> should 404
    r2 = await client.get(
        f"/v1/workspaces/{OTHER_WS_ID}/path-analytics",
        params={"run_id": run_id},
    )
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_post_no_auth_401(unauthed_client, db_session):
    """No auth header -> 401."""
    await _seed_workspace(db_session, WS_ID)
    resp = await unauthed_client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": str(uuid7())},
    )
    assert resp.status_code == 401


async def test_get_no_auth_401(unauthed_client, db_session):
    """No auth header -> 401."""
    await _seed_workspace(db_session, WS_ID)
    resp = await unauthed_client.get(
        f"/v1/workspaces/{WS_ID}/path-analytics/{uuid7()}",
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Response content
# ---------------------------------------------------------------------------


async def test_response_has_sector_codes(client, seeded, db_session):
    """top_paths items have source/target sector codes from the model."""
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": str(seeded["run_id"]), "config": {"max_depth": 3, "top_k": 10}},
    )
    assert resp.status_code == 201
    body = resp.json()
    for path in body["top_paths"]:
        assert path["source_sector_code"] in SECTOR_CODES
        assert path["target_sector_code"] in SECTOR_CODES


async def test_response_coverage_ratio_valid(client, seeded, db_session):
    """coverage_ratio is in [0, 1]."""
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/path-analytics",
        json={"run_id": str(seeded["run_id"]), "config": {"max_depth": 6, "top_k": 20}},
    )
    assert resp.status_code == 201
    assert 0.0 <= resp.json()["coverage_ratio"] <= 1.0
