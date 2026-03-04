"""Tests for Sprint 19 scenario comparison dashboard API."""

import pytest
from uuid_extensions import uuid7

from src.db.tables import ResultSetRow, RunSnapshotRow, WorkspaceRow
from src.models.common import utc_now

pytestmark = pytest.mark.anyio

WS = "00000000-0000-7000-8000-000000000010"

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
    from uuid import UUID
    from sqlalchemy import select
    result = await session.execute(
        select(WorkspaceRow).where(WorkspaceRow.workspace_id == UUID(ws_id))
    )
    if result.scalar_one_or_none() is None:
        now = utc_now()
        session.add(WorkspaceRow(
            workspace_id=UUID(ws_id), client_name="Test", engagement_code="E",
            classification="INTERNAL", description="",
            created_by=uuid7(), created_at=now, updated_at=now,
        ))
        await session.flush()


async def _create_run(session, model_version_id=None, workspace_id=WS):
    from uuid import UUID
    run_id = uuid7()
    mv_id = model_version_id or uuid7()
    row = RunSnapshotRow(
        run_id=run_id,
        model_version_id=mv_id if isinstance(mv_id, UUID) else UUID(mv_id),
        taxonomy_version_id=UUID(_DUMMY_IDS["taxonomy_version_id"]),
        concordance_version_id=UUID(_DUMMY_IDS["concordance_version_id"]),
        mapping_library_version_id=UUID(_DUMMY_IDS["mapping_library_version_id"]),
        assumption_library_version_id=UUID(_DUMMY_IDS["assumption_library_version_id"]),
        prompt_pack_version_id=UUID(_DUMMY_IDS["prompt_pack_version_id"]),
        source_checksums=[],
        workspace_id=UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id,
        created_at=utc_now(),
    )
    session.add(row)
    await session.flush()
    return run_id, mv_id


async def _add_result(session, run_id, metric_type, values, series_kind=None, year=None):
    row = ResultSetRow(
        result_id=uuid7(), run_id=run_id, metric_type=metric_type,
        values=values, sector_breakdowns={},
        year=year, series_kind=series_kind,
        created_at=utc_now(),
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

async def test_compare_runs_happy_path(client, db_session):
    """Two runs with same model, same metrics -> correct deltas."""
    await _seed_ws(db_session)
    mv = uuid7()
    run_a, _ = await _create_run(db_session, model_version_id=mv)
    run_b, _ = await _create_run(db_session, model_version_id=mv)

    await _add_result(db_session, run_a, "total_output", {"_total": 1000.0, "S1": 600.0, "S2": 400.0})
    await _add_result(db_session, run_b, "total_output", {"_total": 1200.0, "S1": 700.0, "S2": 500.0})

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id_a"] == str(run_a)
    assert data["run_id_b"] == str(run_b)
    assert len(data["metrics"]) == 1
    m = data["metrics"][0]
    assert m["metric_type"] == "total_output"
    assert m["value_a"] == 1000.0
    assert m["value_b"] == 1200.0
    assert m["delta"] == 200.0


async def test_compare_runs_pct_change_correct(client, db_session):
    """Verify pct_change = delta / value_a * 100."""
    await _seed_ws(db_session)
    mv = uuid7()
    run_a, _ = await _create_run(db_session, model_version_id=mv)
    run_b, _ = await _create_run(db_session, model_version_id=mv)

    await _add_result(db_session, run_a, "total_output", {"_total": 1000.0})
    await _add_result(db_session, run_b, "total_output", {"_total": 1200.0})

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b)},
    )
    data = resp.json()
    assert data["metrics"][0]["pct_change"] == pytest.approx(20.0)


async def test_compare_runs_pct_change_none_when_zero(client, db_session):
    """value_a=0 -> pct_change=None."""
    await _seed_ws(db_session)
    mv = uuid7()
    run_a, _ = await _create_run(db_session, model_version_id=mv)
    run_b, _ = await _create_run(db_session, model_version_id=mv)

    await _add_result(db_session, run_a, "total_output", {"_total": 0.0})
    await _add_result(db_session, run_b, "total_output", {"_total": 500.0})

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b)},
    )
    data = resp.json()
    assert data["metrics"][0]["pct_change"] is None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

async def test_compare_run_not_found_404(client, db_session):
    """Nonexistent run_id -> 404."""
    await _seed_ws(db_session)
    fake = uuid7()
    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(fake), "run_id_b": str(uuid7())},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["reason_code"] == "COMPARE_RUN_NOT_FOUND"


async def test_compare_run_wrong_workspace_404(client, db_session):
    """Run exists but in different workspace -> 404."""
    await _seed_ws(db_session)
    other_ws = uuid7()
    await _seed_ws(db_session, ws_id=str(other_ws))
    mv = uuid7()
    run_a, _ = await _create_run(db_session, model_version_id=mv, workspace_id=WS)
    run_b, _ = await _create_run(db_session, model_version_id=mv, workspace_id=str(other_ws))

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b)},
    )
    assert resp.status_code == 404


async def test_compare_no_results_422(client, db_session):
    """Run with no ResultSet rows -> 422."""
    await _seed_ws(db_session)
    mv = uuid7()
    run_a, _ = await _create_run(db_session, model_version_id=mv)
    run_b, _ = await _create_run(db_session, model_version_id=mv)
    # No results added for run_a
    await _add_result(db_session, run_b, "total_output", {"_total": 100.0})

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b)},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "COMPARE_NO_RESULTS"


async def test_compare_model_mismatch_422(client, db_session):
    """Different model_version_id -> 422."""
    await _seed_ws(db_session)
    run_a, _ = await _create_run(db_session, model_version_id=uuid7())
    run_b, _ = await _create_run(db_session, model_version_id=uuid7())

    await _add_result(db_session, run_a, "total_output", {"_total": 100.0})
    await _add_result(db_session, run_b, "total_output", {"_total": 200.0})

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b)},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "COMPARE_MODEL_MISMATCH"


async def test_compare_metric_set_mismatch_422(client, db_session):
    """run_a has {total_output, employment}, run_b has {total_output} -> 422."""
    await _seed_ws(db_session)
    mv = uuid7()
    run_a, _ = await _create_run(db_session, model_version_id=mv)
    run_b, _ = await _create_run(db_session, model_version_id=mv)

    await _add_result(db_session, run_a, "total_output", {"_total": 100.0})
    await _add_result(db_session, run_a, "employment", {"_total": 50.0})
    await _add_result(db_session, run_b, "total_output", {"_total": 200.0})

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b)},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "COMPARE_METRIC_SET_MISMATCH"


# ---------------------------------------------------------------------------
# Annual
# ---------------------------------------------------------------------------

async def test_compare_annual_happy_path(client, db_session):
    """include_annual=True -> year-by-year deltas."""
    await _seed_ws(db_session)
    mv = uuid7()
    run_a, _ = await _create_run(db_session, model_version_id=mv)
    run_b, _ = await _create_run(db_session, model_version_id=mv)

    # Cumulative results (required)
    await _add_result(db_session, run_a, "total_output", {"_total": 1000.0})
    await _add_result(db_session, run_b, "total_output", {"_total": 1200.0})

    # Annual results
    await _add_result(db_session, run_a, "total_output", {"_total": 500.0}, series_kind="annual", year=2026)
    await _add_result(db_session, run_a, "total_output", {"_total": 500.0}, series_kind="annual", year=2027)
    await _add_result(db_session, run_b, "total_output", {"_total": 600.0}, series_kind="annual", year=2026)
    await _add_result(db_session, run_b, "total_output", {"_total": 600.0}, series_kind="annual", year=2027)

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b), "include_annual": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["annual"] is not None
    assert len(data["annual"]) == 2
    assert data["annual"][0]["year"] == 2026
    assert data["annual"][0]["metrics"][0]["delta"] == 100.0


async def test_compare_annual_unavailable_422(client, db_session):
    """include_annual=True but no annual rows -> 422."""
    await _seed_ws(db_session)
    mv = uuid7()
    run_a, _ = await _create_run(db_session, model_version_id=mv)
    run_b, _ = await _create_run(db_session, model_version_id=mv)

    await _add_result(db_session, run_a, "total_output", {"_total": 100.0})
    await _add_result(db_session, run_b, "total_output", {"_total": 200.0})

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b), "include_annual": True},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "COMPARE_ANNUAL_UNAVAILABLE"


async def test_compare_annual_year_mismatch_422(client, db_session):
    """Different year sets -> 422."""
    await _seed_ws(db_session)
    mv = uuid7()
    run_a, _ = await _create_run(db_session, model_version_id=mv)
    run_b, _ = await _create_run(db_session, model_version_id=mv)

    await _add_result(db_session, run_a, "total_output", {"_total": 100.0})
    await _add_result(db_session, run_b, "total_output", {"_total": 200.0})

    await _add_result(db_session, run_a, "total_output", {"_total": 50.0}, series_kind="annual", year=2026)
    await _add_result(db_session, run_b, "total_output", {"_total": 100.0}, series_kind="annual", year=2027)

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b), "include_annual": True},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "COMPARE_ANNUAL_YEAR_MISMATCH"


# ---------------------------------------------------------------------------
# Peak
# ---------------------------------------------------------------------------

async def test_compare_peak_happy_path(client, db_session):
    """include_peak=True -> peak comparison."""
    await _seed_ws(db_session)
    mv = uuid7()
    run_a, _ = await _create_run(db_session, model_version_id=mv)
    run_b, _ = await _create_run(db_session, model_version_id=mv)

    await _add_result(db_session, run_a, "total_output", {"_total": 1000.0})
    await _add_result(db_session, run_b, "total_output", {"_total": 1200.0})

    await _add_result(db_session, run_a, "total_output", {"_total": 800.0}, series_kind="peak", year=2028)
    await _add_result(db_session, run_b, "total_output", {"_total": 900.0}, series_kind="peak", year=2029)

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b), "include_peak": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["peak"] is not None
    assert data["peak"]["peak_year_a"] == 2028
    assert data["peak"]["peak_year_b"] == 2029
    assert data["peak"]["metrics"][0]["delta"] == 100.0


async def test_compare_peak_unavailable_422(client, db_session):
    """include_peak=True but no peak rows -> 422."""
    await _seed_ws(db_session)
    mv = uuid7()
    run_a, _ = await _create_run(db_session, model_version_id=mv)
    run_b, _ = await _create_run(db_session, model_version_id=mv)

    await _add_result(db_session, run_a, "total_output", {"_total": 100.0})
    await _add_result(db_session, run_b, "total_output", {"_total": 200.0})

    resp = await client.post(
        f"/v1/workspaces/{WS}/scenarios/compare-runs",
        json={"run_id_a": str(run_a), "run_id_b": str(run_b), "include_peak": True},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason_code"] == "COMPARE_PEAK_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Aggregate extraction (unit tests)
# ---------------------------------------------------------------------------

def test_extract_aggregate_uses_total_key():
    """_extract_aggregate uses _total if present."""
    from src.api.scenarios import _extract_aggregate
    result = _extract_aggregate({"_total": 100.0, "A": 60.0, "B": 40.0})
    assert result == 100.0


def test_extract_aggregate_sums_without_total():
    """_extract_aggregate sums numeric values when no _total."""
    from src.api.scenarios import _extract_aggregate
    result = _extract_aggregate({"A": 60.0, "B": 40.0})
    assert result == 100.0
