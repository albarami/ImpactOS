"""Tests for GET /v1/workspaces/{ws}/engine/runs — list runs endpoint."""

import pytest
from uuid import UUID
from uuid_extensions import uuid7

from src.db.tables import RunSnapshotRow, WorkspaceRow
from src.models.common import utc_now

pytestmark = pytest.mark.anyio

WS = "00000000-0000-7000-8000-000000000099"


async def _seed_ws(session, ws_id=WS):
    """Seed a workspace row."""
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
            engagement_code="E-LIST",
            classification="INTERNAL",
            description="",
            created_by=uuid7(),
            created_at=now,
            updated_at=now,
        ))
        await session.flush()


async def _create_run_snapshot(session, workspace_id=WS):
    """Create a minimal RunSnapshotRow."""
    run_id = uuid7()
    row = RunSnapshotRow(
        run_id=run_id,
        model_version_id=uuid7(),
        taxonomy_version_id=uuid7(),
        concordance_version_id=uuid7(),
        mapping_library_version_id=uuid7(),
        assumption_library_version_id=uuid7(),
        prompt_pack_version_id=uuid7(),
        source_checksums=[],
        workspace_id=UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id,
        created_at=utc_now(),
    )
    session.add(row)
    await session.flush()
    return run_id


class TestListRuns:
    async def test_list_runs_empty(self, client, db_session):
        """Empty workspace returns empty list."""
        await _seed_ws(db_session)
        resp = await client.get(f"/v1/workspaces/{WS}/engine/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []

    async def test_list_runs_returns_workspace_runs(self, client, db_session):
        """Returns runs belonging to the workspace."""
        await _seed_ws(db_session)
        ids = []
        for _ in range(3):
            rid = await _create_run_snapshot(db_session, WS)
            ids.append(str(rid))

        resp = await client.get(f"/v1/workspaces/{WS}/engine/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 3
        returned_ids = {r["run_id"] for r in data["runs"]}
        assert returned_ids == set(ids)

    async def test_list_runs_pagination_limit(self, client, db_session):
        """Respects limit parameter."""
        await _seed_ws(db_session)
        for _ in range(5):
            await _create_run_snapshot(db_session, WS)

        resp = await client.get(f"/v1/workspaces/{WS}/engine/runs?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 2

    async def test_list_runs_pagination_offset(self, client, db_session):
        """Respects offset parameter."""
        await _seed_ws(db_session)
        for _ in range(5):
            await _create_run_snapshot(db_session, WS)

        resp = await client.get(f"/v1/workspaces/{WS}/engine/runs?limit=50&offset=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 2  # 5 total, skip 3, get 2

    async def test_list_runs_response_shape(self, client, db_session):
        """Each run has run_id, model_version_id, created_at."""
        await _seed_ws(db_session)
        await _create_run_snapshot(db_session, WS)

        resp = await client.get(f"/v1/workspaces/{WS}/engine/runs")
        data = resp.json()
        run = data["runs"][0]
        assert "run_id" in run
        assert "model_version_id" in run
        assert "created_at" in run

    async def test_list_runs_excludes_other_workspace(self, client, db_session):
        """Does not return runs from a different workspace."""
        await _seed_ws(db_session)
        other_ws = str(uuid7())
        await _seed_ws(db_session, other_ws)
        await _create_run_snapshot(db_session, WS)
        await _create_run_snapshot(db_session, other_ws)

        resp = await client.get(f"/v1/workspaces/{WS}/engine/runs")
        data = resp.json()
        assert len(data["runs"]) == 1
