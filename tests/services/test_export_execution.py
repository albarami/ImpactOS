"""Tests for ExportExecutionService (Sprint 28, Task 4: S28-0b).

TDD: tests written first, then implementation.
Covers dataclass contracts, execute() success/blocked/failed paths,
cross-workspace rejection, and persistence of export records.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.session import Base
import src.db.tables  # noqa: F401 -- ensure all tables registered
from src.db.tables import (
    ModelVersionRow,
    RunSnapshotRow,
    WorkspaceRow,
)
from src.models.common import ExportMode, new_uuid7, utc_now

pytestmark = pytest.mark.anyio


# ------------------------------------------------------------------
# Dataclass contract tests (S28-0b)
# ------------------------------------------------------------------


class TestExportExecutionDataclasses:
    """S28-0b: Verify input/result/repositories dataclass contracts."""

    def test_export_execution_input_fields(self):
        from src.services.export_execution import ExportExecutionInput

        inp = ExportExecutionInput(
            workspace_id=uuid4(),
            run_id=uuid4(),
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={"title": "Test Report"},
        )
        assert inp.mode == ExportMode.SANDBOX
        assert inp.export_formats == ["excel"]
        assert inp.pack_data == {"title": "Test Report"}

    def test_export_execution_input_frozen(self):
        from src.services.export_execution import ExportExecutionInput

        inp = ExportExecutionInput(
            workspace_id=uuid4(),
            run_id=uuid4(),
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={},
        )
        with pytest.raises(AttributeError):
            inp.workspace_id = uuid4()  # type: ignore[misc]

    def test_export_execution_result_completed(self):
        from src.services.export_execution import ExportExecutionResult

        r = ExportExecutionResult(
            status="COMPLETED",
            export_id=uuid4(),
            checksums={"excel": "sha256:abc123"},
            artifact_refs={"excel": "exports/123/excel.xlsx"},
        )
        assert r.status == "COMPLETED"
        assert r.error is None
        assert r.blocking_reasons == []

    def test_export_execution_result_blocked(self):
        from src.services.export_execution import ExportExecutionResult

        r = ExportExecutionResult(
            status="BLOCKED",
            export_id=uuid4(),
            blocking_reasons=["NFF gate failed"],
        )
        assert r.status == "BLOCKED"
        assert len(r.blocking_reasons) == 1
        assert r.checksums == {}

    def test_export_execution_result_failed(self):
        from src.services.export_execution import ExportExecutionResult

        r = ExportExecutionResult(
            status="FAILED",
            error="Run not found",
        )
        assert r.status == "FAILED"
        assert r.export_id is None
        assert r.error == "Run not found"

    def test_export_execution_result_frozen(self):
        from src.services.export_execution import ExportExecutionResult

        r = ExportExecutionResult(status="FAILED", error="oops")
        with pytest.raises(AttributeError):
            r.status = "COMPLETED"  # type: ignore[misc]

    def test_export_repositories_bundle(self):
        from src.services.export_execution import ExportRepositories

        repos = ExportRepositories(
            export_repo=MagicMock(),
            claim_repo=MagicMock(),
            quality_repo=MagicMock(),
            snap_repo=MagicMock(),
            mv_repo=MagicMock(),
            artifact_store=MagicMock(),
        )
        assert repos.export_repo is not None
        assert repos.claim_repo is not None
        assert repos.quality_repo is not None
        assert repos.snap_repo is not None
        assert repos.mv_repo is not None
        assert repos.artifact_store is not None


# ------------------------------------------------------------------
# Fixtures for execute() tests
# ------------------------------------------------------------------


@pytest.fixture
async def db_env():
    """In-memory DB with workspace, model version, and run snapshot."""
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
            engagement_code="T-EXPORT",
            classification="INTERNAL",
            description="test workspace for export execution",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(ws)

        # Register a model with curated_real provenance
        mv_id = new_uuid7()
        mv = ModelVersionRow(
            model_version_id=mv_id,
            base_year=2023,
            source="test",
            sector_count=3,
            checksum="sha256:abc123",
            provenance_class="curated_real",
            created_at=now,
        )
        session.add(mv)

        # Create a run snapshot belonging to the workspace
        run_id = new_uuid7()
        snap = RunSnapshotRow(
            run_id=run_id,
            model_version_id=mv_id,
            taxonomy_version_id=new_uuid7(),
            concordance_version_id=new_uuid7(),
            mapping_library_version_id=new_uuid7(),
            assumption_library_version_id=new_uuid7(),
            prompt_pack_version_id=new_uuid7(),
            workspace_id=ws_id,
            source_checksums=[],
            created_at=now,
        )
        session.add(snap)
        await session.flush()

        yield {
            "session": session,
            "ws_id": ws_id,
            "mv_id": mv_id,
            "run_id": run_id,
        }
    await engine.dispose()


def _make_repos(session: AsyncSession) -> "ExportRepositories":
    """Build ExportRepositories from a session."""
    from src.services.export_execution import ExportRepositories
    from src.repositories.exports import ExportRepository
    from src.repositories.governance import ClaimRepository
    from src.repositories.data_quality import DataQualityRepository
    from src.repositories.engine import RunSnapshotRepository, ModelVersionRepository
    from src.export.artifact_storage import ExportArtifactStorage

    return ExportRepositories(
        export_repo=ExportRepository(session),
        claim_repo=ClaimRepository(session),
        quality_repo=DataQualityRepository(session),
        snap_repo=RunSnapshotRepository(session),
        mv_repo=ModelVersionRepository(session),
        artifact_store=ExportArtifactStorage(storage_root="/tmp/test-export-artifacts"),
    )


# ------------------------------------------------------------------
# execute() tests (S28-0b)
# ------------------------------------------------------------------


class TestExportExecutionServiceExecute:
    """S28-0b: ExportExecutionService.execute() test cases."""

    async def test_execute_success_sandbox(self, db_env):
        """Happy path: sandbox export completes with checksums."""
        from src.services.export_execution import (
            ExportExecutionInput,
            ExportExecutionService,
        )

        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = ExportExecutionService()

        inp = ExportExecutionInput(
            workspace_id=env["ws_id"],
            run_id=env["run_id"],
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={"title": "Test"},
        )

        # Provide a quality assessment so the export is not blocked
        from src.quality.models import RunQualityAssessment, QualityGrade
        from src.models.common import new_uuid7

        quality_payload = RunQualityAssessment(
            assessment_id=new_uuid7(),
            assessment_version=1,
            run_id=env["run_id"],
            composite_score=0.9,
            grade=QualityGrade.A,
            used_synthetic_fallback=False,
        )

        # Seed quality in DB
        from src.repositories.data_quality import DataQualityRepository

        quality_repo = DataQualityRepository(session)
        await quality_repo.save_summary(
            summary_id=new_uuid7(),
            run_id=env["run_id"],
            workspace_id=env["ws_id"],
            overall_run_score=0.9,
            overall_run_grade="A",
            coverage_pct=1.0,
            publication_gate_pass=True,
            publication_gate_mode="SANDBOX",
            payload=quality_payload.model_dump(mode="json"),
        )

        result = await svc.execute(inp, repos)

        assert result.status == "COMPLETED"
        assert result.export_id is not None
        assert result.checksums  # should have at least one checksum
        assert result.error is None
        assert result.blocking_reasons == []

    async def test_execute_blocked_missing_quality(self, db_env):
        """No quality assessment -> BLOCKED."""
        from src.services.export_execution import (
            ExportExecutionInput,
            ExportExecutionService,
        )

        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = ExportExecutionService()

        inp = ExportExecutionInput(
            workspace_id=env["ws_id"],
            run_id=env["run_id"],
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={"title": "Test"},
        )

        # No quality assessment seeded in DB -> blocked

        result = await svc.execute(inp, repos)

        assert result.status == "BLOCKED"
        assert result.export_id is not None
        assert len(result.blocking_reasons) > 0
        assert any("quality" in r.lower() for r in result.blocking_reasons)

    async def test_execute_run_not_found(self, db_env):
        """Run ID does not exist -> FAILED."""
        from src.services.export_execution import (
            ExportExecutionInput,
            ExportExecutionService,
        )

        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = ExportExecutionService()

        inp = ExportExecutionInput(
            workspace_id=env["ws_id"],
            run_id=uuid4(),  # non-existent
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={},
        )

        result = await svc.execute(inp, repos)

        assert result.status == "FAILED"
        assert result.export_id is None
        assert "not found" in (result.error or "").lower()

    async def test_execute_cross_workspace_rejection(self, db_env):
        """Run exists but in a different workspace -> FAILED."""
        from src.services.export_execution import (
            ExportExecutionInput,
            ExportExecutionService,
        )

        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = ExportExecutionService()

        inp = ExportExecutionInput(
            workspace_id=uuid4(),  # different workspace
            run_id=env["run_id"],
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={},
        )

        result = await svc.execute(inp, repos)

        assert result.status == "FAILED"
        assert result.export_id is None
        assert result.error is not None

    async def test_execute_returns_blocking_reasons_list(self, db_env):
        """When blocked, blocking_reasons list is populated."""
        from src.services.export_execution import (
            ExportExecutionInput,
            ExportExecutionService,
        )

        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = ExportExecutionService()

        # Seed quality with synthetic fallback -> should be blocked
        from src.quality.models import RunQualityAssessment, QualityGrade
        from src.repositories.data_quality import DataQualityRepository

        quality_payload = RunQualityAssessment(
            assessment_id=new_uuid7(),
            assessment_version=1,
            run_id=env["run_id"],
            composite_score=0.5,
            grade=QualityGrade.D,
            used_synthetic_fallback=True,
        )
        quality_repo = DataQualityRepository(session)
        await quality_repo.save_summary(
            summary_id=new_uuid7(),
            run_id=env["run_id"],
            workspace_id=env["ws_id"],
            overall_run_score=0.5,
            overall_run_grade="D",
            coverage_pct=0.5,
            publication_gate_pass=False,
            publication_gate_mode="SANDBOX",
            payload=quality_payload.model_dump(mode="json"),
        )

        inp = ExportExecutionInput(
            workspace_id=env["ws_id"],
            run_id=env["run_id"],
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={"title": "Test"},
        )

        result = await svc.execute(inp, repos)

        assert result.status == "BLOCKED"
        assert isinstance(result.blocking_reasons, list)
        assert len(result.blocking_reasons) >= 1
        assert any("synthetic" in r.lower() for r in result.blocking_reasons)

    async def test_execute_persists_export_record(self, db_env):
        """Export record should be persisted in DB after execution."""
        from src.services.export_execution import (
            ExportExecutionInput,
            ExportExecutionService,
        )
        from src.repositories.exports import ExportRepository

        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = ExportExecutionService()

        # Seed quality for a successful export
        from src.quality.models import RunQualityAssessment, QualityGrade
        from src.repositories.data_quality import DataQualityRepository

        quality_payload = RunQualityAssessment(
            assessment_id=new_uuid7(),
            assessment_version=1,
            run_id=env["run_id"],
            composite_score=0.9,
            grade=QualityGrade.A,
            used_synthetic_fallback=False,
        )
        quality_repo = DataQualityRepository(session)
        await quality_repo.save_summary(
            summary_id=new_uuid7(),
            run_id=env["run_id"],
            workspace_id=env["ws_id"],
            overall_run_score=0.9,
            overall_run_grade="A",
            coverage_pct=1.0,
            publication_gate_pass=True,
            publication_gate_mode="SANDBOX",
            payload=quality_payload.model_dump(mode="json"),
        )

        inp = ExportExecutionInput(
            workspace_id=env["ws_id"],
            run_id=env["run_id"],
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={"title": "Persisted Export"},
        )

        result = await svc.execute(inp, repos)

        assert result.status == "COMPLETED"
        assert result.export_id is not None

        # Verify DB persistence
        export_repo = ExportRepository(session)
        row = await export_repo.get(result.export_id)
        assert row is not None
        assert row.status == "COMPLETED"
        assert row.run_id == env["run_id"]
        assert row.mode == ExportMode.SANDBOX.value
        assert row.checksums_json is not None
        assert len(row.checksums_json) > 0

    async def test_execute_blocked_persists_export_record(self, db_env):
        """Even blocked exports should be persisted in DB."""
        from src.services.export_execution import (
            ExportExecutionInput,
            ExportExecutionService,
        )
        from src.repositories.exports import ExportRepository

        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = ExportExecutionService()

        # No quality assessment -> blocked
        inp = ExportExecutionInput(
            workspace_id=env["ws_id"],
            run_id=env["run_id"],
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={},
        )

        result = await svc.execute(inp, repos)

        assert result.status == "BLOCKED"
        assert result.export_id is not None

        # Verify DB persistence even for blocked
        export_repo = ExportRepository(session)
        row = await export_repo.get(result.export_id)
        assert row is not None
        assert row.status == "BLOCKED"
        assert row.blocked_reasons is not None
        assert len(row.blocked_reasons) > 0


# ------------------------------------------------------------------
# Finding 4 regression: artifact storage / DB persistence failures
# ------------------------------------------------------------------


class TestExportExecutionPersistenceFailures:
    """Finding 4: Failures in artifact storage and DB persistence
    must return FAILED, not bubble into handler_exception."""

    async def test_artifact_storage_failure_returns_failed(self, db_env):
        """When artifact_store.store() raises, result should be FAILED."""
        from src.services.export_execution import (
            ExportExecutionInput,
            ExportExecutionService,
            ExportRepositories,
        )
        from src.repositories.exports import ExportRepository
        from src.repositories.governance import ClaimRepository
        from src.repositories.data_quality import DataQualityRepository
        from src.repositories.engine import RunSnapshotRepository, ModelVersionRepository

        env = db_env
        session = env["session"]

        # Create a mock artifact store that raises on store()
        failing_store = MagicMock()
        failing_store.store.side_effect = OSError("Disk full")

        repos = ExportRepositories(
            export_repo=ExportRepository(session),
            claim_repo=ClaimRepository(session),
            quality_repo=DataQualityRepository(session),
            snap_repo=RunSnapshotRepository(session),
            mv_repo=ModelVersionRepository(session),
            artifact_store=failing_store,
        )

        # Seed quality for a COMPLETED export (so artifacts are generated)
        from src.quality.models import RunQualityAssessment, QualityGrade
        from src.models.common import new_uuid7

        quality_payload = RunQualityAssessment(
            assessment_id=new_uuid7(),
            assessment_version=1,
            run_id=env["run_id"],
            composite_score=0.9,
            grade=QualityGrade.A,
            used_synthetic_fallback=False,
        )
        quality_repo = DataQualityRepository(session)
        await quality_repo.save_summary(
            summary_id=new_uuid7(),
            run_id=env["run_id"],
            workspace_id=env["ws_id"],
            overall_run_score=0.9,
            overall_run_grade="A",
            coverage_pct=1.0,
            publication_gate_pass=True,
            publication_gate_mode="SANDBOX",
            payload=quality_payload.model_dump(mode="json"),
        )

        svc = ExportExecutionService()
        inp = ExportExecutionInput(
            workspace_id=env["ws_id"],
            run_id=env["run_id"],
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={"title": "Disk Full Test"},
        )

        result = await svc.execute(inp, repos)

        # Must return FAILED, not raise an exception
        assert result.status == "FAILED"
        assert result.export_id is not None
        assert "persistence failed" in (result.error or "").lower()

    async def test_db_persistence_failure_returns_failed(self, db_env):
        """When export_repo.create() raises, result should be FAILED."""
        from src.services.export_execution import (
            ExportExecutionInput,
            ExportExecutionService,
            ExportRepositories,
        )
        from src.repositories.governance import ClaimRepository
        from src.repositories.data_quality import DataQualityRepository
        from src.repositories.engine import RunSnapshotRepository, ModelVersionRepository
        from src.export.artifact_storage import ExportArtifactStorage

        env = db_env
        session = env["session"]

        # Create a mock export repo that raises on create()
        failing_export_repo = MagicMock()
        failing_export_repo.create = AsyncMock(
            side_effect=Exception("DB connection lost")
        )

        repos = ExportRepositories(
            export_repo=failing_export_repo,
            claim_repo=ClaimRepository(session),
            quality_repo=DataQualityRepository(session),
            snap_repo=RunSnapshotRepository(session),
            mv_repo=ModelVersionRepository(session),
            artifact_store=ExportArtifactStorage(
                storage_root="/tmp/test-export-artifacts"
            ),
        )

        # Seed quality for a COMPLETED export
        from src.quality.models import RunQualityAssessment, QualityGrade
        from src.models.common import new_uuid7

        quality_payload = RunQualityAssessment(
            assessment_id=new_uuid7(),
            assessment_version=1,
            run_id=env["run_id"],
            composite_score=0.9,
            grade=QualityGrade.A,
            used_synthetic_fallback=False,
        )
        quality_repo = DataQualityRepository(session)
        await quality_repo.save_summary(
            summary_id=new_uuid7(),
            run_id=env["run_id"],
            workspace_id=env["ws_id"],
            overall_run_score=0.9,
            overall_run_grade="A",
            coverage_pct=1.0,
            publication_gate_pass=True,
            publication_gate_mode="SANDBOX",
            payload=quality_payload.model_dump(mode="json"),
        )

        svc = ExportExecutionService()
        inp = ExportExecutionInput(
            workspace_id=env["ws_id"],
            run_id=env["run_id"],
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={"title": "DB Down Test"},
        )

        result = await svc.execute(inp, repos)

        # Must return FAILED, not raise an exception
        assert result.status == "FAILED"
        assert result.export_id is not None
        assert "persistence failed" in (result.error or "").lower()
