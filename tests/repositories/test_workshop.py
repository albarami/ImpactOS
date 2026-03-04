"""Tests for workshop session repository — Sprint 22."""

import pytest
from uuid_extensions import uuid7

from src.db.tables import RunSnapshotRow, WorkspaceRow
from src.models.common import utc_now
from src.repositories.workshop import WorkshopSessionRepository

pytestmark = pytest.mark.anyio

WS_ID = uuid7()
OTHER_WS_ID = uuid7()


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


async def _seed_run(session, workspace_id):
    run_id = uuid7()
    snap = RunSnapshotRow(
        run_id=run_id,
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
    session.add(snap)
    await session.flush()
    return run_id


@pytest.fixture
async def seeded(db_session):
    await _seed_workspace(db_session, WS_ID)
    await _seed_workspace(db_session, OTHER_WS_ID)
    run_id = await _seed_run(db_session, WS_ID)
    return {"run_id": run_id, "session": db_session}


class TestWorkshopSessionRepository:
    async def test_create_and_get(self, seeded):
        repo = WorkshopSessionRepository(seeded["session"])
        sid = uuid7()
        row = await repo.create(
            session_id=sid,
            workspace_id=WS_ID,
            baseline_run_id=seeded["run_id"],
            base_shocks_json={"2025": [100.0, 200.0]},
            slider_config_json=[{"sector_code": "A", "pct_delta": 10.0}],
            transformed_shocks_json={"2025": [110.0, 200.0]},
            config_hash="sha256:abc123",
        )
        assert row.session_id == sid
        assert row.status == "draft"
        assert row.committed_run_id is None

        fetched = await repo.get(sid)
        assert fetched is not None
        assert fetched.workspace_id == WS_ID

    async def test_get_for_workspace_scoped(self, seeded):
        repo = WorkshopSessionRepository(seeded["session"])
        sid = uuid7()
        await repo.create(
            session_id=sid,
            workspace_id=WS_ID,
            baseline_run_id=seeded["run_id"],
            base_shocks_json={"2025": [100.0]},
            slider_config_json=[],
            transformed_shocks_json={"2025": [100.0]},
            config_hash="sha256:ws-scope-test",
        )
        assert await repo.get_for_workspace(sid, WS_ID) is not None
        assert await repo.get_for_workspace(sid, OTHER_WS_ID) is None

    async def test_get_by_config_hash(self, seeded):
        repo = WorkshopSessionRepository(seeded["session"])
        ch = "sha256:idempotent-hash"
        await repo.create(
            session_id=uuid7(),
            workspace_id=WS_ID,
            baseline_run_id=seeded["run_id"],
            base_shocks_json={"2025": [100.0]},
            slider_config_json=[],
            transformed_shocks_json={"2025": [100.0]},
            config_hash=ch,
        )
        found = await repo.get_by_config_for_workspace(WS_ID, ch)
        assert found is not None
        assert found.config_hash == ch
        not_found = await repo.get_by_config_for_workspace(OTHER_WS_ID, ch)
        assert not_found is None

    async def test_update_status_to_committed(self, seeded):
        repo = WorkshopSessionRepository(seeded["session"])
        sid = uuid7()
        await repo.create(
            session_id=sid,
            workspace_id=WS_ID,
            baseline_run_id=seeded["run_id"],
            base_shocks_json={"2025": [100.0]},
            slider_config_json=[],
            transformed_shocks_json={"2025": [100.0]},
            config_hash="sha256:commit-test",
        )
        committed_run = uuid7()
        updated = await repo.update_status(
            sid, status="committed", committed_run_id=committed_run,
        )
        assert updated is not None
        assert updated.status == "committed"
        assert updated.committed_run_id == committed_run

    async def test_update_nonexistent_returns_none(self, seeded):
        repo = WorkshopSessionRepository(seeded["session"])
        result = await repo.update_status(uuid7(), status="committed")
        assert result is None

    async def test_list_for_workspace_pagination(self, seeded):
        repo = WorkshopSessionRepository(seeded["session"])
        for i in range(3):
            await repo.create(
                session_id=uuid7(),
                workspace_id=WS_ID,
                baseline_run_id=seeded["run_id"],
                base_shocks_json={"2025": [float(i)]},
                slider_config_json=[],
                transformed_shocks_json={"2025": [float(i)]},
                config_hash=f"sha256:list-test-{i}",
            )
        rows, total = await repo.list_for_workspace(WS_ID, limit=2, offset=0)
        assert total == 3
        assert len(rows) == 2

        rows2, total2 = await repo.list_for_workspace(WS_ID, limit=2, offset=2)
        assert total2 == 3
        assert len(rows2) == 1

    async def test_list_for_workspace_empty(self, seeded):
        repo = WorkshopSessionRepository(seeded["session"])
        rows, total = await repo.list_for_workspace(OTHER_WS_ID)
        assert total == 0
        assert rows == []

    async def test_update_preview_summary(self, seeded):
        repo = WorkshopSessionRepository(seeded["session"])
        sid = uuid7()
        await repo.create(
            session_id=sid,
            workspace_id=WS_ID,
            baseline_run_id=seeded["run_id"],
            base_shocks_json={"2025": [100.0]},
            slider_config_json=[],
            transformed_shocks_json={"2025": [100.0]},
            config_hash="sha256:preview-test",
        )
        summary = {"gdp_output": 1500000.0, "employment": 5000}
        updated = await repo.update_preview_summary(sid, summary)
        assert updated is not None
        assert updated.preview_summary_json == summary
