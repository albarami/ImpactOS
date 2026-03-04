"""Tests for portfolio optimization API endpoints — Sprint 21."""

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
    checksum = compute_model_checksum(Z_MATRIX, X_VECTOR, {})
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
        z_matrix_json=Z_MATRIX.tolist(),
        x_vector_json=X_VECTOR.tolist(),
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


async def _seed_metric(session, run_id, workspace_id, metric_type, values):
    """Seed a ResultSet with given metric_type and values dict."""
    result_id = uuid7()
    rs = ResultSetRow(
        result_id=result_id,
        run_id=run_id,
        metric_type=metric_type,
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
    """Seed workspace, model, 3 runs with objective and cost metrics."""
    await _seed_workspace(db_session, WS_ID)
    model_id = await _seed_model(db_session)

    run_ids = []
    for i in range(3):
        run_id = await _seed_run(db_session, model_id, WS_ID)
        # objective_metric = "gdp_impact", cost_metric = "total_cost"
        await _seed_metric(
            db_session,
            run_id,
            WS_ID,
            "gdp_impact",
            {"A": 100.0 * (i + 1), "B": 50.0 * (i + 1), "C": 25.0 * (i + 1)},
        )
        await _seed_metric(
            db_session,
            run_id,
            WS_ID,
            "total_cost",
            {"A": 10.0 * (i + 1), "B": 5.0 * (i + 1), "C": 2.5 * (i + 1)},
        )
        run_ids.append(run_id)

    return {"model_id": model_id, "run_ids": run_ids}


@pytest.fixture
async def seeded_two_workspaces(db_session):
    """Seed two workspaces with separate runs for isolation tests."""
    await _seed_workspace(db_session, WS_ID)
    await _seed_workspace(db_session, OTHER_WS_ID)
    model_id = await _seed_model(db_session)

    # Workspace 1 runs
    run_ids = []
    for i in range(2):
        run_id = await _seed_run(db_session, model_id, WS_ID)
        await _seed_metric(
            db_session,
            run_id,
            WS_ID,
            "gdp_impact",
            {"A": 100.0 * (i + 1)},
        )
        await _seed_metric(
            db_session,
            run_id,
            WS_ID,
            "total_cost",
            {"A": 10.0 * (i + 1)},
        )
        run_ids.append(run_id)

    # Workspace 2 runs
    other_run_id = await _seed_run(db_session, model_id, OTHER_WS_ID)
    await _seed_metric(
        db_session,
        other_run_id,
        OTHER_WS_ID,
        "gdp_impact",
        {"A": 100.0},
    )
    await _seed_metric(
        db_session,
        other_run_id,
        OTHER_WS_ID,
        "total_cost",
        {"A": 10.0},
    )

    return {
        "model_id": model_id,
        "run_ids": run_ids,
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


def _make_payload(run_ids, **overrides):
    """Build a valid POST payload from a list of run_ids."""
    base = {
        "objective_metric": "gdp_impact",
        "cost_metric": "total_cost",
        "candidate_run_ids": [str(r) for r in run_ids],
        "budget": 1000.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


async def test_post_creates_201(client, seeded, db_session):
    """Full happy path -- POST creates portfolio and returns 201."""
    payload = _make_payload(seeded["run_ids"])
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "portfolio_id" in body
    assert body["workspace_id"] == str(WS_ID)
    assert body["optimization_version"] == "portfolio_v1"
    assert body["config"]["objective_metric"] == "gdp_impact"
    assert body["config"]["cost_metric"] == "total_cost"
    assert len(body["config"]["candidate_run_ids"]) == 3
    assert body["config"]["budget"] == 1000.0
    assert "selected_run_ids" in body
    assert "total_objective" in body
    assert "total_cost" in body
    assert "solver_method" in body
    assert "result_checksum" in body
    assert "created_at" in body


async def test_post_idempotent_200(client, seeded, db_session):
    """Second POST with same config returns 200 with same portfolio_id."""
    payload = _make_payload(seeded["run_ids"])
    r1 = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert r1.status_code == 201
    pid1 = r1.json()["portfolio_id"]

    r2 = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert r2.status_code == 200
    assert r2.json()["portfolio_id"] == pid1


async def test_get_by_id_200(client, seeded, db_session):
    """Create then GET by ID returns 200."""
    payload = _make_payload(seeded["run_ids"])
    r1 = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert r1.status_code == 201
    pid = r1.json()["portfolio_id"]

    r2 = await client.get(f"/v1/workspaces/{WS_ID}/portfolio/{pid}")
    assert r2.status_code == 200
    assert r2.json()["portfolio_id"] == pid


async def test_list_200(client, seeded, db_session):
    """List returns created portfolios."""
    payload = _make_payload(seeded["run_ids"])
    await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    r = await client.get(f"/v1/workspaces/{WS_ID}/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


async def test_list_pagination(client, seeded, db_session):
    """limit=1 returns 1 item when 2 exist."""
    # Create two different portfolios with different budgets
    p1 = _make_payload(seeded["run_ids"], budget=1000.0)
    p2 = _make_payload(seeded["run_ids"], budget=500.0)
    r1 = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=p1,
    )
    assert r1.status_code == 201
    r2 = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=p2,
    )
    assert r2.status_code == 201

    r = await client.get(
        f"/v1/workspaces/{WS_ID}/portfolio",
        params={"limit": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1


# ---------------------------------------------------------------------------
# Error precedence
# ---------------------------------------------------------------------------


async def test_post_no_candidates_422(client, seeded, db_session):
    """Empty candidate list -> 422 PORTFOLIO_NO_CANDIDATES."""
    payload = _make_payload([])
    # Override to empty list (bypass _make_payload min_length)
    payload["candidate_run_ids"] = []
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "PORTFOLIO_NO_CANDIDATES"


async def test_post_duplicate_candidates_422(client, seeded, db_session):
    """Duplicate candidate_run_ids -> 422 PORTFOLIO_DUPLICATE_CANDIDATES."""
    dup_id = str(seeded["run_ids"][0])
    payload = _make_payload(seeded["run_ids"])
    payload["candidate_run_ids"] = [dup_id, dup_id, str(seeded["run_ids"][1])]
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "PORTFOLIO_DUPLICATE_CANDIDATES"


async def test_post_run_not_found_404(client, seeded, db_session):
    """Nonexistent run_id -> 404 PORTFOLIO_RUN_NOT_FOUND."""
    payload = _make_payload(seeded["run_ids"])
    payload["candidate_run_ids"].append(str(uuid7()))
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["reason_code"] == "PORTFOLIO_RUN_NOT_FOUND"


async def test_post_model_mismatch_422(client, db_session):
    """Candidates from different models -> 422 PORTFOLIO_MODEL_MISMATCH."""
    await _seed_workspace(db_session, WS_ID)
    model_id_1 = await _seed_model(db_session)
    model_id_2 = await _seed_model(db_session)

    run_1 = await _seed_run(db_session, model_id_1, WS_ID)
    await _seed_metric(db_session, run_1, WS_ID, "gdp_impact", {"A": 100.0})
    await _seed_metric(db_session, run_1, WS_ID, "total_cost", {"A": 10.0})

    run_2 = await _seed_run(db_session, model_id_2, WS_ID)
    await _seed_metric(db_session, run_2, WS_ID, "gdp_impact", {"A": 200.0})
    await _seed_metric(db_session, run_2, WS_ID, "total_cost", {"A": 20.0})

    payload = _make_payload([run_1, run_2])
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "PORTFOLIO_MODEL_MISMATCH"


async def test_post_metric_not_found_422(client, db_session):
    """Missing metric for a candidate -> 422 PORTFOLIO_METRIC_NOT_FOUND."""
    await _seed_workspace(db_session, WS_ID)
    model_id = await _seed_model(db_session)

    run_1 = await _seed_run(db_session, model_id, WS_ID)
    await _seed_metric(db_session, run_1, WS_ID, "gdp_impact", {"A": 100.0})
    await _seed_metric(db_session, run_1, WS_ID, "total_cost", {"A": 10.0})

    # run_2 has gdp_impact but NOT total_cost
    run_2 = await _seed_run(db_session, model_id, WS_ID)
    await _seed_metric(db_session, run_2, WS_ID, "gdp_impact", {"A": 200.0})

    payload = _make_payload([run_1, run_2])
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "PORTFOLIO_METRIC_NOT_FOUND"


async def test_post_invalid_budget_422(client, seeded, db_session):
    """budget <= 0 -> 422 PORTFOLIO_INVALID_CONFIG."""
    payload = _make_payload(seeded["run_ids"], budget=-5.0)
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "PORTFOLIO_INVALID_CONFIG"


async def test_post_candidate_limit_422(client, db_session):
    """More than 25 candidates -> 422 PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED."""
    await _seed_workspace(db_session, WS_ID)
    model_id = await _seed_model(db_session)

    run_ids = []
    for i in range(26):
        run_id = await _seed_run(db_session, model_id, WS_ID)
        await _seed_metric(
            db_session,
            run_id,
            WS_ID,
            "gdp_impact",
            {"A": float(100 * (i + 1))},
        )
        await _seed_metric(
            db_session,
            run_id,
            WS_ID,
            "total_cost",
            {"A": float(10 * (i + 1))},
        )
        run_ids.append(run_id)

    payload = _make_payload(run_ids)
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED"


async def test_post_empty_objective_metric_422(client, seeded, db_session):
    """Empty objective_metric -> 422 PORTFOLIO_INVALID_CONFIG."""
    payload = _make_payload(seeded["run_ids"], objective_metric="")
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "PORTFOLIO_INVALID_CONFIG"


async def test_post_empty_cost_metric_422(client, seeded, db_session):
    """Empty cost_metric -> 422 PORTFOLIO_INVALID_CONFIG."""
    payload = _make_payload(seeded["run_ids"], cost_metric="")
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "PORTFOLIO_INVALID_CONFIG"


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


async def test_get_wrong_workspace_404(client, seeded_two_workspaces, db_session):
    """Portfolio exists but wrong workspace -> 404."""
    payload = _make_payload(seeded_two_workspaces["run_ids"])
    r1 = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert r1.status_code == 201
    pid = r1.json()["portfolio_id"]

    r2 = await client.get(f"/v1/workspaces/{OTHER_WS_ID}/portfolio/{pid}")
    assert r2.status_code == 404
    assert r2.json()["detail"]["reason_code"] == "PORTFOLIO_NOT_FOUND"


async def test_list_workspace_isolation(client, seeded_two_workspaces, db_session):
    """Portfolio in workspace A not visible from workspace B list."""
    payload = _make_payload(seeded_two_workspaces["run_ids"])
    await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )

    r = await client.get(f"/v1/workspaces/{OTHER_WS_ID}/portfolio")
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert len(r.json()["items"]) == 0


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_unauthenticated_401(unauthed_client, db_session):
    """No auth header -> 401."""
    await _seed_workspace(db_session, WS_ID)
    resp = await unauthed_client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json={
            "objective_metric": "x",
            "cost_metric": "y",
            "candidate_run_ids": [str(uuid7())],
            "budget": 100.0,
        },
    )
    assert resp.status_code == 401


async def test_unauthenticated_get_401(unauthed_client, db_session):
    """No auth header on GET -> 401."""
    await _seed_workspace(db_session, WS_ID)
    resp = await unauthed_client.get(
        f"/v1/workspaces/{WS_ID}/portfolio/{uuid7()}",
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Response content
# ---------------------------------------------------------------------------


async def test_response_contains_model_version_id(client, seeded, db_session):
    """Response includes model_version_id shared by all candidates."""
    payload = _make_payload(seeded["run_ids"])
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["model_version_id"] == str(seeded["model_id"])


async def test_response_contains_solver_method(client, seeded, db_session):
    """Response includes solver_method from the engine."""
    payload = _make_payload(seeded["run_ids"])
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 201
    assert resp.json()["solver_method"] == "exact_binary_knapsack_v1"


async def test_response_selected_run_ids_sorted(client, seeded, db_session):
    """selected_run_ids are sorted ASC (string order)."""
    payload = _make_payload(seeded["run_ids"])
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 201
    selected = resp.json()["selected_run_ids"]
    assert selected == sorted(selected)


async def test_post_infeasible_422(client, db_session):
    """Budget too small for any single candidate -> 422 PORTFOLIO_INFEASIBLE."""
    await _seed_workspace(db_session, WS_ID)
    model_id = await _seed_model(db_session)

    run_id = await _seed_run(db_session, model_id, WS_ID)
    # Cost is 1000 but budget will be 1
    await _seed_metric(db_session, run_id, WS_ID, "gdp_impact", {"A": 100.0})
    await _seed_metric(db_session, run_id, WS_ID, "total_cost", {"A": 1000.0})

    payload = _make_payload([run_id], budget=1.0)
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/portfolio/optimize",
        json=payload,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "PORTFOLIO_INFEASIBLE"
