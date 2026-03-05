"""Tests for ExportRepository — TDD for exports rewiring."""

import pytest
from uuid_extensions import uuid7

from src.repositories.exports import ExportRepository


@pytest.fixture
def repo(db_session):
    return ExportRepository(db_session)


class TestExportRepository:
    """ExportRepository CRUD operations."""

    @pytest.mark.anyio
    async def test_create_and_get(self, repo: ExportRepository) -> None:
        eid = uuid7()
        rid = uuid7()
        row = await repo.create(
            export_id=eid,
            run_id=rid,
            mode="SANDBOX",
            status="COMPLETED",
            checksums_json={"excel": "sha256:abc123"},
            blocked_reasons=[],
        )
        assert row.export_id == eid
        assert row.run_id == rid
        assert row.status == "COMPLETED"

        fetched = await repo.get(eid)
        assert fetched is not None
        assert fetched.export_id == eid

    @pytest.mark.anyio
    async def test_get_nonexistent_returns_none(self, repo: ExportRepository) -> None:
        result = await repo.get(uuid7())
        assert result is None

    @pytest.mark.anyio
    async def test_list_all(self, repo: ExportRepository) -> None:
        for _ in range(3):
            await repo.create(
                export_id=uuid7(),
                run_id=uuid7(),
                mode="SANDBOX",
                status="COMPLETED",
            )
        rows = await repo.list_all()
        assert len(rows) == 3

    @pytest.mark.anyio
    async def test_update_status(self, repo: ExportRepository) -> None:
        eid = uuid7()
        await repo.create(
            export_id=eid,
            run_id=uuid7(),
            mode="SANDBOX",
            status="PENDING",
        )
        updated = await repo.update_status(eid, "COMPLETED")
        assert updated is not None
        assert updated.status == "COMPLETED"

    @pytest.mark.anyio
    async def test_checksums_persisted(self, repo: ExportRepository) -> None:
        eid = uuid7()
        checksums = {"excel": "sha256:aaa", "pptx": "sha256:bbb"}
        await repo.create(
            export_id=eid,
            run_id=uuid7(),
            mode="SANDBOX",
            status="COMPLETED",
            checksums_json=checksums,
        )
        fetched = await repo.get(eid)
        assert fetched is not None
        assert fetched.checksums_json == checksums

    @pytest.mark.anyio
    async def test_blocked_reasons_persisted(self, repo: ExportRepository) -> None:
        eid = uuid7()
        reasons = ["Unresolved claim C1", "Missing assumption A2"]
        await repo.create(
            export_id=eid,
            run_id=uuid7(),
            mode="GOVERNED",
            status="BLOCKED",
            blocked_reasons=reasons,
        )
        fetched = await repo.get(eid)
        assert fetched is not None
        assert fetched.blocked_reasons == reasons


# ---------------------------------------------------------------------------
# S23-2: Variance Bridge Analysis Repository
# ---------------------------------------------------------------------------

import hashlib
from uuid import uuid4

from src.repositories.exports import VarianceBridgeRepository


_WS_ID = uuid4()


def _make_bridge_analysis(*, workspace_id, config_hash=None, run_a_id=None, run_b_id=None):
    """Build a VarianceBridgeAnalysis for testing."""
    from src.models.export import VarianceBridgeAnalysis

    ch = config_hash or "sha256:" + hashlib.sha256(str(uuid4()).encode()).hexdigest()
    return VarianceBridgeAnalysis(
        workspace_id=workspace_id,
        run_a_id=run_a_id or uuid4(),
        run_b_id=run_b_id or uuid4(),
        metric_type="total_output",
        config_hash=ch,
        config_json={"run_a_id": "test", "run_b_id": "test"},
        result_json={"drivers": []},
        result_checksum="sha256:" + "b" * 64,
    )


class TestVarianceBridgeRepository:
    """S23-2: Workspace-scoped bridge analytics persistence."""

    @pytest.fixture
    def bridge_repo(self, db_session):
        return VarianceBridgeRepository(db_session)

    @pytest.mark.anyio
    async def test_create_and_get(self, bridge_repo):
        """Round-trip create and get."""
        analysis = _make_bridge_analysis(workspace_id=_WS_ID)
        created = await bridge_repo.create(analysis)
        assert created.analysis_id == analysis.analysis_id
        fetched = await bridge_repo.get(_WS_ID, analysis.analysis_id)
        assert fetched is not None
        assert fetched.config_hash == analysis.config_hash

    @pytest.mark.anyio
    async def test_get_returns_none_for_wrong_workspace(self, bridge_repo):
        """Cross-workspace access returns None (surfaced as 404)."""
        analysis = _make_bridge_analysis(workspace_id=_WS_ID)
        await bridge_repo.create(analysis)
        other_ws = uuid4()
        fetched = await bridge_repo.get(other_ws, analysis.analysis_id)
        assert fetched is None

    @pytest.mark.anyio
    async def test_idempotent_create_by_config_hash(self, bridge_repo):
        """Duplicate config_hash returns existing record."""
        ch = "sha256:" + "a" * 64
        a1 = _make_bridge_analysis(workspace_id=_WS_ID, config_hash=ch)
        a2 = _make_bridge_analysis(workspace_id=_WS_ID, config_hash=ch)
        created1 = await bridge_repo.create(a1)
        created2 = await bridge_repo.create(a2)
        assert created1.analysis_id == created2.analysis_id

    @pytest.mark.anyio
    async def test_list_for_workspace(self, bridge_repo):
        """List returns only workspace-scoped records."""
        ws2 = uuid4()
        a1 = _make_bridge_analysis(workspace_id=_WS_ID)
        a2 = _make_bridge_analysis(workspace_id=_WS_ID)
        a3 = _make_bridge_analysis(workspace_id=ws2)
        await bridge_repo.create(a1)
        await bridge_repo.create(a2)
        await bridge_repo.create(a3)
        results = await bridge_repo.list_for_workspace(_WS_ID)
        assert len(results) == 2

    @pytest.mark.anyio
    async def test_get_by_config_hash(self, bridge_repo):
        """Lookup by config_hash + workspace_id."""
        ch = "sha256:" + "c" * 64
        analysis = _make_bridge_analysis(workspace_id=_WS_ID, config_hash=ch)
        await bridge_repo.create(analysis)
        fetched = await bridge_repo.get_by_config_hash(_WS_ID, ch)
        assert fetched is not None
        assert fetched.analysis_id == analysis.analysis_id
