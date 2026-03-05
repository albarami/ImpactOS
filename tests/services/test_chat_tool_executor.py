"""Tests for ChatToolExecutor (Sprint 27).

Verifies ToolExecutionResult model, safety caps, latency tracking,
error handling, and real tool handler logic.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.session import Base
import src.db.tables  # noqa: F401
from src.db.tables import WorkspaceRow, RunSnapshotRow, ResultSetRow, ExportRow
from src.models.chat import ToolCall, ToolExecutionResult
from src.models.common import new_uuid7, utc_now
from src.repositories.scenarios import ScenarioVersionRepository
from src.repositories.engine import ResultSetRepository
from src.repositories.exports import ExportRepository
from src.services.chat_tool_executor import (
    ChatToolExecutor,
    MAX_TOOL_CALLS_PER_TURN,
    _MAX_RUN_ENGINE_PER_TURN,
    _MAX_CREATE_EXPORT_PER_TURN,
)

pytestmark = pytest.mark.anyio


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
async def db_session():
    """Create in-memory SQLite session with workspace."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        ws_id = uuid4()
        now = utc_now()
        ws = WorkspaceRow(
            workspace_id=ws_id,
            client_name="Test Client",
            engagement_code="T-EXEC",
            classification="INTERNAL",
            description="test workspace",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(ws)
        await session.flush()
        yield session, ws_id
    await engine.dispose()


@pytest.fixture
def executor(db_session):
    """ChatToolExecutor wired to in-memory DB."""
    session, ws_id = db_session
    return ChatToolExecutor(session=session, workspace_id=ws_id)


# ------------------------------------------------------------------
# ToolExecutionResult model tests (unchanged from S27-1a)
# ------------------------------------------------------------------


class TestToolExecutionResult:
    """S27-1a: ToolExecutionResult model validation."""

    def test_success_result(self):
        r = ToolExecutionResult(
            tool_name="lookup_data",
            status="success",
            latency_ms=42,
            result={"data": [1, 2, 3]},
        )
        assert r.status == "success"
        assert r.tool_name == "lookup_data"
        assert r.latency_ms == 42
        assert r.result == {"data": [1, 2, 3]}
        assert r.error_summary is None
        assert r.retryable is False

    def test_error_result(self):
        r = ToolExecutionResult(
            tool_name="run_engine",
            status="error",
            reason_code="handler_exception",
            retryable=True,
            error_summary="Connection timeout",
        )
        assert r.status == "error"
        assert r.reason_code == "handler_exception"
        assert r.retryable is True
        assert r.error_summary == "Connection timeout"
        assert r.result is None

    def test_blocked_result(self):
        r = ToolExecutionResult(
            tool_name="run_engine",
            status="blocked",
            reason_code="max_run_engine_exceeded",
        )
        assert r.status == "blocked"
        assert r.reason_code == "max_run_engine_exceeded"
        assert r.latency_ms == 0


# ------------------------------------------------------------------
# Executor basics (safety caps, unknown tools, latency, exceptions)
# ------------------------------------------------------------------


class TestChatToolExecutorBasics:
    """S27-1a: ChatToolExecutor skeleton behavior."""

    def test_max_tool_calls_constant(self):
        assert MAX_TOOL_CALLS_PER_TURN == 5

    def test_max_run_engine_constant(self):
        assert _MAX_RUN_ENGINE_PER_TURN == 1

    def test_max_create_export_constant(self):
        assert _MAX_CREATE_EXPORT_PER_TURN == 1

    async def test_unknown_tool_returns_error(self, executor):
        tc = ToolCall(tool_name="nonexistent_tool", arguments={})
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "unknown_tool"
        assert "nonexistent_tool" in (result.error_summary or "")

    async def test_known_tool_returns_success(self, executor):
        tc = ToolCall(tool_name="lookup_data", arguments={"query": "GDP"})
        result = await executor.execute(tc)
        assert result.status == "success"
        assert result.result is not None

    async def test_execute_all_respects_cap(self, executor):
        # Create more tool calls than the cap allows
        calls = [
            ToolCall(tool_name="lookup_data", arguments={"i": i})
            for i in range(MAX_TOOL_CALLS_PER_TURN + 3)
        ]
        results = await executor.execute_all(calls)
        assert len(results) == MAX_TOOL_CALLS_PER_TURN + 3

        executed = [r for r in results if r.status == "success"]
        blocked = [r for r in results if r.status == "blocked"]
        assert len(executed) == MAX_TOOL_CALLS_PER_TURN
        assert len(blocked) == 3
        for b in blocked:
            assert b.reason_code == "max_tool_calls_exceeded"

    async def test_execute_all_caps_run_engine_to_one(self, db_session):
        """run_engine per-turn cap: second call is blocked."""
        session, ws_id = db_session

        # Create a scenario so run_engine can validate it
        repo = ScenarioVersionRepository(session)
        spec_id = new_uuid7()
        mv_id = new_uuid7()
        await repo.create(
            scenario_spec_id=spec_id, version=1, name="Cap Test",
            workspace_id=ws_id, base_model_version_id=mv_id,
            base_year=2023, time_horizon={"start_year": 2023, "end_year": 2023},
        )

        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        calls = [
            ToolCall(tool_name="run_engine", arguments={"scenario_spec_id": str(spec_id)}),
            ToolCall(tool_name="run_engine", arguments={"scenario_spec_id": str(spec_id)}),
            ToolCall(tool_name="lookup_data", arguments={}),
        ]
        results = await executor.execute_all(calls)
        assert len(results) == 3

        # First run_engine should succeed
        assert results[0].status == "success"
        assert results[0].tool_name == "run_engine"

        # Second run_engine should be blocked
        assert results[1].status == "blocked"
        assert results[1].reason_code == "max_run_engine_exceeded"

        # lookup_data should still succeed
        assert results[2].status == "success"
        assert results[2].tool_name == "lookup_data"

    async def test_execute_all_caps_create_export_to_one(self, db_session):
        """create_export per-turn cap: second call is blocked."""
        session, ws_id = db_session

        # Create RunSnapshotRow so export can reference it
        run_id = new_uuid7()
        now = utc_now()
        snap = RunSnapshotRow(
            run_id=run_id,
            model_version_id=new_uuid7(),
            taxonomy_version_id=new_uuid7(),
            concordance_version_id=new_uuid7(),
            mapping_library_version_id=new_uuid7(),
            assumption_library_version_id=new_uuid7(),
            prompt_pack_version_id=new_uuid7(),
            source_checksums=[],
            workspace_id=ws_id,
            created_at=now,
        )
        session.add(snap)
        await session.flush()

        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        args = {
            "run_id": str(run_id),
            "mode": "SANDBOX",
            "export_formats": ["pptx"],
            "pack_data": {},
        }
        calls = [
            ToolCall(tool_name="create_export", arguments=args),
            ToolCall(tool_name="create_export", arguments=args),
        ]
        results = await executor.execute_all(calls)
        assert results[0].status == "success"
        assert results[1].status == "blocked"
        assert results[1].reason_code == "max_create_export_exceeded"

    async def test_execute_measures_latency(self, executor):
        tc = ToolCall(tool_name="lookup_data", arguments={})
        result = await executor.execute(tc)
        assert result.status == "success"
        # Latency should be non-negative (stubs are fast, so >= 0)
        assert result.latency_ms >= 0

    async def test_execute_catches_exceptions(self, executor):
        tc = ToolCall(tool_name="lookup_data", arguments={})

        # Patch the handler to raise
        original = executor._handle_lookup_data

        async def _failing_handler(args):
            raise RuntimeError("simulated failure")

        executor._handler_map["lookup_data"] = _failing_handler
        try:
            result = await executor.execute(tc)
        finally:
            executor._handler_map["lookup_data"] = original

        assert result.status == "error"
        assert result.reason_code == "handler_exception"
        assert result.retryable is True
        assert "simulated failure" in (result.error_summary or "")
        assert result.latency_ms >= 0

    async def test_execute_all_empty_list(self, executor):
        results = await executor.execute_all([])
        assert results == []

    async def test_get_handler_returns_none_for_unknown(self, executor):
        assert executor._get_handler("unknown") is None

    async def test_get_handler_returns_callable_for_known(self, executor):
        handler = executor._get_handler("lookup_data")
        assert handler is not None
        assert callable(handler)


# ------------------------------------------------------------------
# Handler tests: lookup_data
# ------------------------------------------------------------------


class TestLookupDataHandler:
    """S27-1b: lookup_data MVP stub returns dataset metadata."""

    async def test_basic_success(self, executor):
        tc = ToolCall(tool_name="lookup_data", arguments={"dataset_id": "io_tables"})
        result = await executor.execute(tc)
        assert result.status == "success"
        assert result.result["reason_code"] == "datasets_listed"
        assert isinstance(result.result["datasets"], list)
        assert len(result.result["datasets"]) > 0
        # Each dataset should have dataset_id and description
        ds = result.result["datasets"][0]
        assert "dataset_id" in ds
        assert "description" in ds


# ------------------------------------------------------------------
# Handler tests: build_scenario
# ------------------------------------------------------------------


class TestBuildScenarioHandler:
    """S27-1b: build_scenario handler creates a ScenarioSpec in the DB."""

    async def test_success(self, db_session):
        session, ws_id = db_session
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        mv_id = str(new_uuid7())

        tc = ToolCall(tool_name="build_scenario", arguments={
            "name": "Tourism Impact Scenario",
            "base_year": 2023,
            "base_model_version_id": mv_id,
            "start_year": 2023,
            "end_year": 2025,
        })
        result = await executor.execute(tc)
        assert result.status == "success"
        assert result.result is not None
        assert "scenario_spec_id" in result.result
        assert result.result["version"] == 1
        assert result.result["name"] == "Tourism Impact Scenario"

        # Verify scenario was actually persisted
        repo = ScenarioVersionRepository(session)
        row = await repo.get_latest(UUID(result.result["scenario_spec_id"]))
        assert row is not None
        assert row.name == "Tourism Impact Scenario"
        assert row.base_year == 2023

    async def test_missing_name_returns_invalid_args(self, executor):
        tc = ToolCall(tool_name="build_scenario", arguments={
            "base_year": 2023,
            "base_model_version_id": str(new_uuid7()),
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"

    async def test_missing_base_year_returns_invalid_args(self, executor):
        tc = ToolCall(tool_name="build_scenario", arguments={
            "name": "Test",
            "base_model_version_id": str(new_uuid7()),
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"

    async def test_missing_base_model_version_id_returns_invalid_args(self, executor):
        tc = ToolCall(tool_name="build_scenario", arguments={
            "name": "Test",
            "base_year": 2023,
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"


# ------------------------------------------------------------------
# Handler tests: run_engine
# ------------------------------------------------------------------


class TestRunEngineHandler:
    """S27-1b: run_engine validates scenario and returns structured success."""

    async def test_success_validated_scenario(self, db_session):
        session, ws_id = db_session

        # Create a scenario in the DB
        repo = ScenarioVersionRepository(session)
        spec_id = new_uuid7()
        mv_id = new_uuid7()
        await repo.create(
            scenario_spec_id=spec_id, version=1, name="Engine Test",
            workspace_id=ws_id, base_model_version_id=mv_id,
            base_year=2023, time_horizon={"start_year": 2023, "end_year": 2023},
        )

        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="run_engine", arguments={
            "scenario_spec_id": str(spec_id),
            "scenario_spec_version": 1,
        })
        result = await executor.execute(tc)
        assert result.status == "success"
        data = result.result
        assert data["reason_code"] == "scenario_validated_dry_run"
        assert data["status"] == "success"
        assert data["scenario_spec_id"] == str(spec_id)
        assert data["scenario_spec_version"] == 1
        assert data["model_version_id"] == str(mv_id)
        # run_id should be a valid UUID
        UUID(data["run_id"])

    async def test_invalid_scenario_spec_id(self, executor):
        tc = ToolCall(tool_name="run_engine", arguments={
            "scenario_spec_id": "not-a-uuid",
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"

    async def test_missing_scenario_spec_id(self, executor):
        tc = ToolCall(tool_name="run_engine", arguments={})
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"

    async def test_scenario_not_found(self, executor):
        tc = ToolCall(tool_name="run_engine", arguments={
            "scenario_spec_id": str(new_uuid7()),
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "scenario_not_found"

    async def test_version_omitted_falls_back_to_latest(self, db_session):
        """When scenario_spec_version is not provided, run_engine uses latest version."""
        session, ws_id = db_session
        repo = ScenarioVersionRepository(session)
        spec_id = new_uuid7()
        mv_id = new_uuid7()

        # Create two versions
        await repo.create(
            scenario_spec_id=spec_id, version=1, name="V1",
            workspace_id=ws_id, base_model_version_id=mv_id,
            base_year=2023, time_horizon={"start_year": 2023, "end_year": 2023},
        )
        mv_id_v2 = new_uuid7()
        await repo.create(
            scenario_spec_id=spec_id, version=2, name="V2",
            workspace_id=ws_id, base_model_version_id=mv_id_v2,
            base_year=2024, time_horizon={"start_year": 2024, "end_year": 2024},
        )

        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="run_engine", arguments={
            "scenario_spec_id": str(spec_id),
            # No scenario_spec_version — should fall back to latest (v2)
        })
        result = await executor.execute(tc)
        assert result.status == "success"
        assert result.result["scenario_spec_version"] == 2
        assert result.result["model_version_id"] == str(mv_id_v2)

    async def test_version_pinning_wrong_version(self, db_session):
        """run_engine returns scenario_not_found when requested version doesn't exist."""
        session, ws_id = db_session
        repo = ScenarioVersionRepository(session)
        spec_id = new_uuid7()
        await repo.create(
            scenario_spec_id=spec_id, version=1, name="Only V1",
            workspace_id=ws_id, base_model_version_id=new_uuid7(),
            base_year=2023, time_horizon={"start_year": 2023, "end_year": 2023},
        )

        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="run_engine", arguments={
            "scenario_spec_id": str(spec_id),
            "scenario_spec_version": 99,  # Version 99 doesn't exist
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "scenario_not_found"
        assert "v99" in result.error_summary

    async def test_version_pinning_cross_workspace_rejected(self, db_session):
        """run_engine rejects version-pinned scenario from another workspace."""
        session, ws_id = db_session
        other_ws_id = uuid4()
        now = utc_now()
        other_ws = WorkspaceRow(
            workspace_id=other_ws_id,
            client_name="Other",
            engagement_code="T-OTHER",
            classification="INTERNAL",
            description="other workspace",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(other_ws)
        await session.flush()

        # Create scenario in OTHER workspace
        repo = ScenarioVersionRepository(session)
        spec_id = new_uuid7()
        await repo.create(
            scenario_spec_id=spec_id, version=1, name="Other WS",
            workspace_id=other_ws_id, base_model_version_id=new_uuid7(),
            base_year=2023, time_horizon={"start_year": 2023, "end_year": 2023},
        )

        # Executor scoped to original workspace — version-pinned lookup should reject
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="run_engine", arguments={
            "scenario_spec_id": str(spec_id),
            "scenario_spec_version": 1,  # Exists in other workspace, not ours
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "scenario_not_found"


# ------------------------------------------------------------------
# Handler tests: narrate_results
# ------------------------------------------------------------------


class TestNarrateResultsHandler:
    """S27-1b: narrate_results reads ResultSet rows and returns structured data."""

    async def test_success_with_results(self, db_session):
        session, ws_id = db_session

        # Create a run snapshot first (FK target)
        run_id = new_uuid7()
        now = utc_now()
        snap = RunSnapshotRow(
            run_id=run_id,
            model_version_id=new_uuid7(),
            taxonomy_version_id=new_uuid7(),
            concordance_version_id=new_uuid7(),
            mapping_library_version_id=new_uuid7(),
            assumption_library_version_id=new_uuid7(),
            prompt_pack_version_id=new_uuid7(),
            source_checksums=[],
            workspace_id=ws_id,
            created_at=now,
        )
        session.add(snap)
        await session.flush()

        # Create ResultSet rows
        repo = ResultSetRepository(session)
        await repo.create(
            result_id=new_uuid7(), run_id=run_id,
            metric_type="gdp_impact", values={"total": 1200000000, "direct": 800000000},
            workspace_id=ws_id,
        )
        await repo.create(
            result_id=new_uuid7(), run_id=run_id,
            metric_type="employment_impact", values={"total_jobs": 5000},
            workspace_id=ws_id,
        )

        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="narrate_results", arguments={"run_id": str(run_id)})
        result = await executor.execute(tc)
        assert result.status == "success"
        data = result.result
        assert data["reason_code"] == "results_found"
        assert data["run_id"] == str(run_id)
        assert "gdp_impact" in data["result"]
        assert "employment_impact" in data["result"]
        assert data["result"]["gdp_impact"]["total"] == 1200000000

    async def test_no_results_returns_empty(self, db_session):
        """narrate_results returns no_results when run exists but has no ResultSets."""
        session, ws_id = db_session

        # Create a RunSnapshot (so workspace guard passes) but no ResultSets
        run_id = new_uuid7()
        now = utc_now()
        snap = RunSnapshotRow(
            run_id=run_id,
            model_version_id=new_uuid7(),
            taxonomy_version_id=new_uuid7(),
            concordance_version_id=new_uuid7(),
            mapping_library_version_id=new_uuid7(),
            assumption_library_version_id=new_uuid7(),
            prompt_pack_version_id=new_uuid7(),
            source_checksums=[],
            workspace_id=ws_id,
            created_at=now,
        )
        session.add(snap)
        await session.flush()

        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="narrate_results", arguments={
            "run_id": str(run_id),
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "no_results"
        assert result.result["result"] == {}

    async def test_run_not_found_returns_error(self, executor):
        """narrate_results rejects run_ids with no RunSnapshot."""
        tc = ToolCall(tool_name="narrate_results", arguments={
            "run_id": str(new_uuid7()),
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "run_not_found"

    async def test_invalid_run_id_format(self, executor):
        tc = ToolCall(tool_name="narrate_results", arguments={
            "run_id": "not-a-uuid",
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"

    async def test_missing_run_id(self, executor):
        tc = ToolCall(tool_name="narrate_results", arguments={})
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"


# ------------------------------------------------------------------
# Handler tests: create_export
# ------------------------------------------------------------------


class TestCreateExportHandler:
    """S27-1b: create_export handler creates an export record."""

    async def test_success(self, db_session):
        session, ws_id = db_session

        # Create a RunSnapshot so export can be created
        run_id = new_uuid7()
        now = utc_now()
        snap = RunSnapshotRow(
            run_id=run_id,
            model_version_id=new_uuid7(),
            taxonomy_version_id=new_uuid7(),
            concordance_version_id=new_uuid7(),
            mapping_library_version_id=new_uuid7(),
            assumption_library_version_id=new_uuid7(),
            prompt_pack_version_id=new_uuid7(),
            source_checksums=[],
            workspace_id=ws_id,
            created_at=now,
        )
        session.add(snap)
        await session.flush()

        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="create_export", arguments={
            "run_id": str(run_id),
            "mode": "SANDBOX",
            "export_formats": ["pptx", "xlsx"],
            "pack_data": {"title": "Tourism Impact Report"},
        })
        result = await executor.execute(tc)
        assert result.status == "success"
        data = result.result
        assert "export_id" in data
        assert data["status"] == "PENDING"

        # Verify persisted
        repo = ExportRepository(session)
        row = await repo.get(UUID(data["export_id"]))
        assert row is not None
        assert row.mode == "SANDBOX"
        assert row.status == "PENDING"

    async def test_missing_run_id_returns_invalid_args(self, executor):
        tc = ToolCall(tool_name="create_export", arguments={
            "mode": "SANDBOX",
            "export_formats": ["pptx"],
            "pack_data": {},
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"

    async def test_missing_mode_returns_invalid_args(self, executor):
        tc = ToolCall(tool_name="create_export", arguments={
            "run_id": str(new_uuid7()),
            "export_formats": ["pptx"],
            "pack_data": {},
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"

    async def test_invalid_mode_returns_invalid_args(self, db_session):
        session, ws_id = db_session
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="create_export", arguments={
            "run_id": str(new_uuid7()),
            "mode": "INVALID",
            "export_formats": ["pptx"],
            "pack_data": {},
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"
        assert "SANDBOX or GOVERNED" in result.error_summary

    async def test_missing_pack_data_returns_invalid_args(self, executor):
        tc = ToolCall(tool_name="create_export", arguments={
            "run_id": str(new_uuid7()),
            "mode": "SANDBOX",
            "export_formats": ["pptx"],
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"

    async def test_missing_run_snapshot_returns_run_not_found(self, db_session):
        """create_export rejects run_ids with no persisted RunSnapshot."""
        session, ws_id = db_session
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)

        # Use a synthetic run_id that has no RunSnapshotRow
        tc = ToolCall(tool_name="create_export", arguments={
            "run_id": str(new_uuid7()),
            "mode": "SANDBOX",
            "export_formats": ["pptx"],
            "pack_data": {"title": "Report"},
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "run_not_found"

    async def test_cross_workspace_run_rejected(self, db_session):
        """create_export rejects RunSnapshot from a different workspace."""
        session, ws_id = db_session
        other_ws_id = uuid4()

        # Create RunSnapshot in OTHER workspace
        run_id = new_uuid7()
        now = utc_now()
        other_ws = WorkspaceRow(
            workspace_id=other_ws_id,
            client_name="Other",
            engagement_code="T-OTHER",
            classification="INTERNAL",
            description="other workspace",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(other_ws)
        snap = RunSnapshotRow(
            run_id=run_id,
            model_version_id=new_uuid7(),
            taxonomy_version_id=new_uuid7(),
            concordance_version_id=new_uuid7(),
            mapping_library_version_id=new_uuid7(),
            assumption_library_version_id=new_uuid7(),
            prompt_pack_version_id=new_uuid7(),
            source_checksums=[],
            workspace_id=other_ws_id,
            created_at=now,
        )
        session.add(snap)
        await session.flush()

        # Executor scoped to original workspace — should reject
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="create_export", arguments={
            "run_id": str(run_id),
            "mode": "SANDBOX",
            "export_formats": ["pptx"],
            "pack_data": {"title": "Report"},
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "run_not_found"


# ------------------------------------------------------------------
# Workspace isolation tests
# ------------------------------------------------------------------


class TestWorkspaceIsolation:
    """Handlers must reject resources from other workspaces."""

    async def test_run_engine_rejects_cross_workspace_scenario(self, db_session):
        """run_engine returns scenario_not_found for scenario in another workspace."""
        session, ws_id = db_session
        other_ws_id = uuid4()
        now = utc_now()
        other_ws = WorkspaceRow(
            workspace_id=other_ws_id,
            client_name="Other",
            engagement_code="T-OTHER",
            classification="INTERNAL",
            description="other workspace",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(other_ws)
        await session.flush()

        # Create scenario in OTHER workspace
        repo = ScenarioVersionRepository(session)
        spec_id = new_uuid7()
        await repo.create(
            scenario_spec_id=spec_id, version=1, name="Other WS Scenario",
            workspace_id=other_ws_id, base_model_version_id=new_uuid7(),
            base_year=2023, time_horizon={"start_year": 2023, "end_year": 2023},
        )

        # Executor scoped to original workspace — should reject
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="run_engine", arguments={
            "scenario_spec_id": str(spec_id),
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "scenario_not_found"

    async def test_narrate_results_rejects_cross_workspace_run(self, db_session):
        """narrate_results returns run_not_found for run in another workspace."""
        session, ws_id = db_session
        other_ws_id = uuid4()
        now = utc_now()
        other_ws = WorkspaceRow(
            workspace_id=other_ws_id,
            client_name="Other",
            engagement_code="T-OTHER",
            classification="INTERNAL",
            description="other workspace",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(other_ws)

        # Create RunSnapshot in OTHER workspace
        run_id = new_uuid7()
        snap = RunSnapshotRow(
            run_id=run_id,
            model_version_id=new_uuid7(),
            taxonomy_version_id=new_uuid7(),
            concordance_version_id=new_uuid7(),
            mapping_library_version_id=new_uuid7(),
            assumption_library_version_id=new_uuid7(),
            prompt_pack_version_id=new_uuid7(),
            source_checksums=[],
            workspace_id=other_ws_id,
            created_at=now,
        )
        session.add(snap)
        await session.flush()

        # Executor scoped to original workspace — should reject
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="narrate_results", arguments={
            "run_id": str(run_id),
        })
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "run_not_found"
