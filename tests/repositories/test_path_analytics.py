"""Tests for PathAnalysisRepository — workspace scoping, CRUD, pagination, idempotency."""

import pytest
from sqlalchemy.exc import IntegrityError
from uuid_extensions import uuid7

from src.db.tables import PathAnalysisRow, RunSnapshotRow, WorkspaceRow
from src.models.common import utc_now
from src.repositories.path_analytics import PathAnalysisRepository

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_workspace(session, workspace_id=None) -> WorkspaceRow:
    """Create a minimal workspace row."""
    now = utc_now()
    ws = WorkspaceRow(
        workspace_id=workspace_id or uuid7(),
        client_name="Test Client",
        engagement_code="ENG-001",
        classification="INTERNAL",
        description="Test workspace",
        created_by=uuid7(),
        created_at=now,
        updated_at=now,
    )
    session.add(ws)
    await session.flush()
    return ws


async def _create_run_snapshot(session, workspace_id) -> RunSnapshotRow:
    """Create a minimal run snapshot row with required FK columns."""
    rs = RunSnapshotRow(
        run_id=uuid7(),
        model_version_id=uuid7(),
        taxonomy_version_id=uuid7(),
        concordance_version_id=uuid7(),
        mapping_library_version_id=uuid7(),
        assumption_library_version_id=uuid7(),
        prompt_pack_version_id=uuid7(),
        workspace_id=workspace_id,
        source_checksums=[],
        created_at=utc_now(),
    )
    session.add(rs)
    await session.flush()
    return rs


async def _create_path_analysis(
    session,
    repo: PathAnalysisRepository,
    run_id,
    workspace_id,
    *,
    config_hash: str = "sha256:abc123",
) -> PathAnalysisRow:
    """Create a path analysis row through the repository."""
    return await repo.create(
        analysis_id=uuid7(),
        run_id=run_id,
        workspace_id=workspace_id,
        analysis_version="1.0.0",
        config_json={"max_depth": 4, "top_k": 10},
        config_hash=config_hash,
        max_depth=4,
        top_k=10,
        top_paths_json=[{"path": ["A", "B"], "contribution": 0.5}],
        chokepoints_json=[{"sector": "A", "betweenness": 0.8}],
        depth_contributions_json={"1": 0.4, "2": 0.3, "3": 0.2, "4": 0.1},
        coverage_ratio=0.85,
        result_checksum="sha256:result_abc",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_create_and_get_roundtrip(db_session):
    """Create -> get -> verify all fields match."""
    ws = await _create_workspace(db_session)
    rs = await _create_run_snapshot(db_session, ws.workspace_id)
    repo = PathAnalysisRepository(db_session)

    analysis_id = uuid7()
    config_json = {"max_depth": 4, "top_k": 10, "extra": "param"}
    top_paths = [{"path": ["S1", "S2", "S3"], "contribution": 0.45}]
    chokepoints = [{"sector": "S2", "betweenness": 0.9}]
    depth_contribs = {"1": 0.5, "2": 0.3, "3": 0.15, "4": 0.05}

    row = await repo.create(
        analysis_id=analysis_id,
        run_id=rs.run_id,
        workspace_id=ws.workspace_id,
        analysis_version="1.0.0",
        config_json=config_json,
        config_hash="sha256:deadbeef",
        max_depth=4,
        top_k=10,
        top_paths_json=top_paths,
        chokepoints_json=chokepoints,
        depth_contributions_json=depth_contribs,
        coverage_ratio=0.92,
        result_checksum="sha256:result123",
    )

    fetched = await repo.get(analysis_id)
    assert fetched is not None
    assert fetched.analysis_id == analysis_id
    assert fetched.run_id == rs.run_id
    assert fetched.workspace_id == ws.workspace_id
    assert fetched.analysis_version == "1.0.0"
    assert fetched.config_hash == "sha256:deadbeef"
    assert fetched.max_depth == 4
    assert fetched.top_k == 10
    assert fetched.coverage_ratio == pytest.approx(0.92)
    assert fetched.result_checksum == "sha256:result123"
    assert fetched.created_at is not None


async def test_get_returns_none_for_missing(db_session):
    """Unknown UUID returns None."""
    repo = PathAnalysisRepository(db_session)
    result = await repo.get(uuid7())
    assert result is None


async def test_get_for_workspace_hit(db_session):
    """Correct workspace returns the row."""
    ws = await _create_workspace(db_session)
    rs = await _create_run_snapshot(db_session, ws.workspace_id)
    repo = PathAnalysisRepository(db_session)

    row = await _create_path_analysis(
        db_session,
        repo,
        rs.run_id,
        ws.workspace_id,
    )

    result = await repo.get_for_workspace(row.analysis_id, ws.workspace_id)
    assert result is not None
    assert result.analysis_id == row.analysis_id


async def test_get_for_workspace_wrong_workspace(db_session):
    """Wrong workspace_id returns None."""
    ws_a = await _create_workspace(db_session)
    ws_b = await _create_workspace(db_session)
    rs = await _create_run_snapshot(db_session, ws_a.workspace_id)
    repo = PathAnalysisRepository(db_session)

    row = await _create_path_analysis(
        db_session,
        repo,
        rs.run_id,
        ws_a.workspace_id,
    )

    result = await repo.get_for_workspace(row.analysis_id, ws_b.workspace_id)
    assert result is None


async def test_get_by_run_and_config_for_workspace_hit(db_session):
    """Exact match on (run_id, config_hash, workspace_id) returns the row."""
    ws = await _create_workspace(db_session)
    rs = await _create_run_snapshot(db_session, ws.workspace_id)
    repo = PathAnalysisRepository(db_session)

    row = await _create_path_analysis(
        db_session,
        repo,
        rs.run_id,
        ws.workspace_id,
        config_hash="sha256:unique_config",
    )

    result = await repo.get_by_run_and_config_for_workspace(
        rs.run_id,
        "sha256:unique_config",
        ws.workspace_id,
    )
    assert result is not None
    assert result.analysis_id == row.analysis_id


async def test_get_by_run_and_config_for_workspace_miss(db_session):
    """Wrong config_hash returns None."""
    ws = await _create_workspace(db_session)
    rs = await _create_run_snapshot(db_session, ws.workspace_id)
    repo = PathAnalysisRepository(db_session)

    await _create_path_analysis(
        db_session,
        repo,
        rs.run_id,
        ws.workspace_id,
        config_hash="sha256:actual_config",
    )

    result = await repo.get_by_run_and_config_for_workspace(
        rs.run_id,
        "sha256:wrong_config",
        ws.workspace_id,
    )
    assert result is None


async def test_list_by_run_multiple_configs(db_session):
    """Two analyses for same run with different configs, ordered by created_at DESC."""
    ws = await _create_workspace(db_session)
    rs = await _create_run_snapshot(db_session, ws.workspace_id)
    repo = PathAnalysisRepository(db_session)

    row1 = await _create_path_analysis(
        db_session,
        repo,
        rs.run_id,
        ws.workspace_id,
        config_hash="sha256:config_a",
    )
    row2 = await _create_path_analysis(
        db_session,
        repo,
        rs.run_id,
        ws.workspace_id,
        config_hash="sha256:config_b",
    )

    rows, total = await repo.list_by_run(rs.run_id, ws.workspace_id)
    assert total == 2
    assert len(rows) == 2
    # Ordered by created_at DESC — row2 was created after row1
    assert rows[0].analysis_id == row2.analysis_id
    assert rows[1].analysis_id == row1.analysis_id


async def test_list_by_run_pagination(db_session):
    """Limit/offset work correctly and total is accurate."""
    ws = await _create_workspace(db_session)
    rs = await _create_run_snapshot(db_session, ws.workspace_id)
    repo = PathAnalysisRepository(db_session)

    # Create 5 analyses with distinct config hashes
    for i in range(5):
        await _create_path_analysis(
            db_session,
            repo,
            rs.run_id,
            ws.workspace_id,
            config_hash=f"sha256:config_{i:03d}",
        )

    page1, total1 = await repo.list_by_run(
        rs.run_id,
        ws.workspace_id,
        limit=2,
        offset=0,
    )
    assert total1 == 5
    assert len(page1) == 2

    page2, total2 = await repo.list_by_run(
        rs.run_id,
        ws.workspace_id,
        limit=2,
        offset=2,
    )
    assert total2 == 5
    assert len(page2) == 2

    page3, total3 = await repo.list_by_run(
        rs.run_id,
        ws.workspace_id,
        limit=2,
        offset=4,
    )
    assert total3 == 5
    assert len(page3) == 1

    # No overlap between pages
    all_ids = [r.analysis_id for r in page1 + page2 + page3]
    assert len(set(all_ids)) == 5


async def test_list_by_run_workspace_isolation(db_session):
    """Analysis from workspace A does not appear in workspace B listing."""
    ws_a = await _create_workspace(db_session)
    ws_b = await _create_workspace(db_session)
    rs_a = await _create_run_snapshot(db_session, ws_a.workspace_id)
    rs_b = await _create_run_snapshot(db_session, ws_b.workspace_id)
    repo = PathAnalysisRepository(db_session)

    await _create_path_analysis(
        db_session,
        repo,
        rs_a.run_id,
        ws_a.workspace_id,
        config_hash="sha256:config_a",
    )
    await _create_path_analysis(
        db_session,
        repo,
        rs_b.run_id,
        ws_b.workspace_id,
        config_hash="sha256:config_b",
    )

    rows_a, total_a = await repo.list_by_run(rs_a.run_id, ws_a.workspace_id)
    assert total_a == 1
    assert rows_a[0].workspace_id == ws_a.workspace_id

    rows_b, total_b = await repo.list_by_run(rs_b.run_id, ws_b.workspace_id)
    assert total_b == 1
    assert rows_b[0].workspace_id == ws_b.workspace_id

    # Cross-workspace: run A in workspace B returns nothing
    rows_cross, total_cross = await repo.list_by_run(
        rs_a.run_id,
        ws_b.workspace_id,
    )
    assert total_cross == 0
    assert len(rows_cross) == 0


async def test_idempotency_same_config_hash(db_session):
    """Second create with same (run_id, config_hash) raises IntegrityError."""
    ws = await _create_workspace(db_session)
    rs = await _create_run_snapshot(db_session, ws.workspace_id)
    repo = PathAnalysisRepository(db_session)

    await _create_path_analysis(
        db_session,
        repo,
        rs.run_id,
        ws.workspace_id,
        config_hash="sha256:duplicate",
    )

    with pytest.raises(IntegrityError):
        await repo.create(
            analysis_id=uuid7(),
            run_id=rs.run_id,
            workspace_id=ws.workspace_id,
            analysis_version="1.0.0",
            config_json={"max_depth": 4, "top_k": 10},
            config_hash="sha256:duplicate",
            max_depth=4,
            top_k=10,
            top_paths_json=[],
            chokepoints_json=[],
            depth_contributions_json={},
            coverage_ratio=0.5,
            result_checksum="sha256:different_result",
        )
