"""Tests for RunExecutionService (Sprint 28).

TDD: tests written first, then implementation.
Covers dataclass contracts, execute_from_scenario() success/failure paths,
and verification that result_summary comes from persisted DB rows.
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.session import Base
import src.db.tables  # noqa: F401 — ensure all tables registered
from src.db.tables import WorkspaceRow, ModelVersionRow, ModelDataRow
from src.models.common import new_uuid7, utc_now
from src.repositories.engine import (
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.scenarios import ScenarioVersionRepository

pytestmark = pytest.mark.anyio


# ------------------------------------------------------------------
# Dataclass contract tests (Task 2: S28-0a)
# ------------------------------------------------------------------


class TestRunExecutionDataclasses:
    """S28-0a: Verify input/result dataclass contracts."""

    def test_run_from_scenario_input_fields(self):
        from src.services.run_execution import RunFromScenarioInput
        inp = RunFromScenarioInput(
            workspace_id=uuid4(),
            scenario_spec_id=uuid4(),
            scenario_spec_version=2,
        )
        assert inp.scenario_spec_version == 2

    def test_run_from_scenario_input_version_defaults_none(self):
        from src.services.run_execution import RunFromScenarioInput
        inp = RunFromScenarioInput(
            workspace_id=uuid4(),
            scenario_spec_id=uuid4(),
        )
        assert inp.scenario_spec_version is None

    def test_run_from_scenario_input_frozen(self):
        from src.services.run_execution import RunFromScenarioInput
        inp = RunFromScenarioInput(
            workspace_id=uuid4(),
            scenario_spec_id=uuid4(),
        )
        with pytest.raises(AttributeError):
            inp.workspace_id = uuid4()  # type: ignore[misc]

    def test_run_execution_result_completed(self):
        from src.services.run_execution import RunExecutionResult
        r = RunExecutionResult(
            status="COMPLETED",
            run_id=uuid4(),
            model_version_id=uuid4(),
            scenario_spec_id=uuid4(),
            scenario_spec_version=1,
            result_summary={"total_output": {"total": 1000.0}},
        )
        assert r.status == "COMPLETED"
        assert r.error is None

    def test_run_execution_result_failed(self):
        from src.services.run_execution import RunExecutionResult
        r = RunExecutionResult(status="FAILED", error="Model not found")
        assert r.status == "FAILED"
        assert r.run_id is None

    def test_run_execution_result_frozen(self):
        from src.services.run_execution import RunExecutionResult
        r = RunExecutionResult(status="FAILED", error="oops")
        with pytest.raises(AttributeError):
            r.status = "COMPLETED"  # type: ignore[misc]

    def test_run_repositories_bundle(self):
        from src.services.run_execution import RunRepositories
        repos = RunRepositories(
            scenario_repo=MagicMock(),
            mv_repo=MagicMock(),
            md_repo=MagicMock(),
            snap_repo=MagicMock(),
            rs_repo=MagicMock(),
        )
        assert repos.scenario_repo is not None
        assert repos.mv_repo is not None
        assert repos.md_repo is not None
        assert repos.snap_repo is not None
        assert repos.rs_repo is not None


# ------------------------------------------------------------------
# Fixtures for execute_from_scenario tests (Task 3)
# ------------------------------------------------------------------


@pytest.fixture
async def db_env():
    """In-memory DB with workspace, model version, model data, and scenario."""
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
            engagement_code="T-RUN",
            classification="INTERNAL",
            description="test workspace for run execution",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(ws)

        # Register a 3-sector model with curated_real provenance
        mv_id = new_uuid7()
        mv = ModelVersionRow(
            model_version_id=mv_id,
            base_year=2023,
            source="test",
            sector_count=3,
            checksum="sha256:1bb9deeef3696f1d6b544ca7e10a3cd14e0cf9437047501b48fa6bc9a72b65a7",
            provenance_class="curated_real",
            created_at=now,
        )
        session.add(mv)

        z = [[0.1, 0.2, 0.0], [0.0, 0.1, 0.3], [0.1, 0.0, 0.1]]
        x = [100.0, 200.0, 150.0]
        md = ModelDataRow(
            model_version_id=mv_id,
            z_matrix_json=z,
            x_vector_json=x,
            sector_codes=["A", "B", "C"],
        )
        session.add(md)
        await session.flush()

        # Create scenario
        scenario_repo = ScenarioVersionRepository(session)
        scenario_id = new_uuid7()
        await scenario_repo.create(
            scenario_spec_id=scenario_id,
            version=1,
            name="test_scenario",
            workspace_id=ws_id,
            base_model_version_id=mv_id,
            base_year=2023,
            time_horizon={"start_year": 2023, "end_year": 2023},
            shock_items=[],
        )

        yield {
            "session": session,
            "ws_id": ws_id,
            "mv_id": mv_id,
            "scenario_id": scenario_id,
        }
    await engine.dispose()


@pytest.fixture
async def db_env_with_shocks():
    """In-memory DB with a scenario containing real FINAL_DEMAND_SHOCK items."""
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
            engagement_code="T-SHOCK",
            classification="INTERNAL",
            description="test workspace for shock execution",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(ws)

        mv_id = new_uuid7()
        mv = ModelVersionRow(
            model_version_id=mv_id,
            base_year=2023,
            source="test",
            sector_count=3,
            checksum="sha256:1bb9deeef3696f1d6b544ca7e10a3cd14e0cf9437047501b48fa6bc9a72b65a7",
            provenance_class="curated_real",
            created_at=now,
        )
        session.add(mv)

        z = [[0.1, 0.2, 0.0], [0.0, 0.1, 0.3], [0.1, 0.0, 0.1]]
        x = [100.0, 200.0, 150.0]
        md = ModelDataRow(
            model_version_id=mv_id,
            z_matrix_json=z,
            x_vector_json=x,
            sector_codes=["A", "B", "C"],
        )
        session.add(md)
        await session.flush()

        # Create scenario WITH real shock_items
        shock_items = [
            {
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": "B",
                "year": 2023,
                "amount_real_base_year": 500_000_000.0,
                "domestic_share": 0.8,
            },
        ]
        scenario_repo = ScenarioVersionRepository(session)
        scenario_id = new_uuid7()
        await scenario_repo.create(
            scenario_spec_id=scenario_id,
            version=1,
            name="test_scenario_with_shocks",
            workspace_id=ws_id,
            base_model_version_id=mv_id,
            base_year=2023,
            time_horizon={"start_year": 2023, "end_year": 2023},
            shock_items=shock_items,
        )

        yield {
            "session": session,
            "ws_id": ws_id,
            "mv_id": mv_id,
            "scenario_id": scenario_id,
            "shock_items": shock_items,
        }
    await engine.dispose()


def _make_repos(session: AsyncSession) -> "RunRepositories":
    """Build RunRepositories from a session."""
    from src.services.run_execution import RunRepositories
    return RunRepositories(
        scenario_repo=ScenarioVersionRepository(session),
        mv_repo=ModelVersionRepository(session),
        md_repo=ModelDataRepository(session),
        snap_repo=RunSnapshotRepository(session),
        rs_repo=ResultSetRepository(session),
    )


# ------------------------------------------------------------------
# execute_from_scenario() tests (Task 3: S28-0a)
# ------------------------------------------------------------------


class TestRunExecutionServiceFromScenario:
    """S28-0a: Real engine execution from scenario."""

    async def test_execute_from_scenario_success(self, db_env):
        """Happy path: scenario found, model loaded, engine runs, results persisted."""
        from src.services.run_execution import RunExecutionService, RunFromScenarioInput
        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = RunExecutionService()
        inp = RunFromScenarioInput(
            workspace_id=env["ws_id"],
            scenario_spec_id=env["scenario_id"],
            scenario_spec_version=1,
        )

        with patch(
            "src.services.run_execution.load_satellite_coefficients"
        ) as mock_load:
            # Provide synthetic satellite coefficients matching 3 sectors
            from src.engine.satellites import SatelliteCoefficients
            from src.data.workforce.satellite_coeff_loader import (
                LoadedCoefficients,
                CoefficientProvenance,
            )
            mock_coeffs = SatelliteCoefficients(
                jobs_coeff=np.array([0.01, 0.02, 0.015]),
                import_ratio=np.array([0.15, 0.15, 0.15]),
                va_ratio=np.array([0.5, 0.4, 0.6]),
                version_id=new_uuid7(),
            )
            mock_load.return_value = LoadedCoefficients(
                coefficients=mock_coeffs,
                provenance=CoefficientProvenance(
                    employment_coeff_year=2023,
                    io_base_year=2023,
                    import_ratio_year=2023,
                    va_ratio_year=2023,
                ),
            )

            result = await svc.execute_from_scenario(inp, repos)

        assert result.status == "COMPLETED"
        assert result.run_id is not None
        assert result.model_version_id == env["mv_id"]
        assert result.scenario_spec_id == env["scenario_id"]
        assert result.scenario_spec_version == 1
        assert result.result_summary is not None
        assert isinstance(result.result_summary, dict)
        assert result.error is None

    async def test_execute_from_scenario_not_found(self, db_env):
        """Scenario spec ID does not exist -> FAILED."""
        from src.services.run_execution import RunExecutionService, RunFromScenarioInput
        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = RunExecutionService()
        inp = RunFromScenarioInput(
            workspace_id=env["ws_id"],
            scenario_spec_id=uuid4(),  # non-existent
        )

        result = await svc.execute_from_scenario(inp, repos)

        assert result.status == "FAILED"
        assert "not found" in (result.error or "").lower()
        assert result.run_id is None

    async def test_execute_from_scenario_cross_workspace(self, db_env):
        """Scenario exists but in a different workspace -> FAILED."""
        from src.services.run_execution import RunExecutionService, RunFromScenarioInput
        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = RunExecutionService()
        inp = RunFromScenarioInput(
            workspace_id=uuid4(),  # different workspace
            scenario_spec_id=env["scenario_id"],
            scenario_spec_version=1,
        )

        result = await svc.execute_from_scenario(inp, repos)

        assert result.status == "FAILED"
        # Should be a workspace mismatch or not-found error
        assert result.run_id is None

    async def test_result_summary_from_persisted_rows(self, db_env):
        """result_summary must come from persisted ResultSet rows, not in-memory."""
        from src.services.run_execution import RunExecutionService, RunFromScenarioInput
        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = RunExecutionService()
        inp = RunFromScenarioInput(
            workspace_id=env["ws_id"],
            scenario_spec_id=env["scenario_id"],
            scenario_spec_version=1,
        )

        with patch(
            "src.services.run_execution.load_satellite_coefficients"
        ) as mock_load:
            from src.engine.satellites import SatelliteCoefficients
            from src.data.workforce.satellite_coeff_loader import (
                LoadedCoefficients,
                CoefficientProvenance,
            )
            mock_coeffs = SatelliteCoefficients(
                jobs_coeff=np.array([0.01, 0.02, 0.015]),
                import_ratio=np.array([0.15, 0.15, 0.15]),
                va_ratio=np.array([0.5, 0.4, 0.6]),
                version_id=new_uuid7(),
            )
            mock_load.return_value = LoadedCoefficients(
                coefficients=mock_coeffs,
                provenance=CoefficientProvenance(
                    employment_coeff_year=2023,
                    io_base_year=2023,
                    import_ratio_year=2023,
                    va_ratio_year=2023,
                ),
            )

            result = await svc.execute_from_scenario(inp, repos)

        assert result.status == "COMPLETED"
        assert result.run_id is not None

        # Verify run_id points to a real persisted snapshot
        snap = await repos.snap_repo.get(result.run_id)
        assert snap is not None
        assert snap.workspace_id == env["ws_id"]

        # Verify result sets exist in the DB
        rs_rows = await repos.rs_repo.get_by_run(result.run_id)
        assert len(rs_rows) > 0

        # Verify result_summary keys match persisted cumulative metric types
        persisted_cumulative_types = {
            r.metric_type for r in rs_rows if r.series_kind is None
        }
        assert set(result.result_summary.keys()) == persisted_cumulative_types

    async def test_run_snapshot_exists_for_returned_run_id(self, db_env):
        """Returned run_id must be backed by a persisted RunSnapshot."""
        from src.services.run_execution import RunExecutionService, RunFromScenarioInput
        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = RunExecutionService()
        inp = RunFromScenarioInput(
            workspace_id=env["ws_id"],
            scenario_spec_id=env["scenario_id"],
            scenario_spec_version=1,
        )

        with patch(
            "src.services.run_execution.load_satellite_coefficients"
        ) as mock_load:
            from src.engine.satellites import SatelliteCoefficients
            from src.data.workforce.satellite_coeff_loader import (
                LoadedCoefficients,
                CoefficientProvenance,
            )
            mock_coeffs = SatelliteCoefficients(
                jobs_coeff=np.array([0.01, 0.02, 0.015]),
                import_ratio=np.array([0.15, 0.15, 0.15]),
                va_ratio=np.array([0.5, 0.4, 0.6]),
                version_id=new_uuid7(),
            )
            mock_load.return_value = LoadedCoefficients(
                coefficients=mock_coeffs,
                provenance=CoefficientProvenance(
                    employment_coeff_year=2023,
                    io_base_year=2023,
                    import_ratio_year=2023,
                    va_ratio_year=2023,
                ),
            )

            result = await svc.execute_from_scenario(inp, repos)

        assert result.status == "COMPLETED"
        assert result.run_id is not None

        # Must have a real persisted snapshot
        snap = await repos.snap_repo.get(result.run_id)
        assert snap is not None
        assert snap.model_version_id == env["mv_id"]
        assert snap.scenario_spec_id == env["scenario_id"]
        assert snap.scenario_spec_version == 1

    async def test_execute_from_scenario_latest_version(self, db_env):
        """When scenario_spec_version is None, uses latest version."""
        from src.services.run_execution import RunExecutionService, RunFromScenarioInput
        env = db_env
        session = env["session"]
        repos = _make_repos(session)
        svc = RunExecutionService()

        # Input without scenario_spec_version -> should resolve latest
        inp = RunFromScenarioInput(
            workspace_id=env["ws_id"],
            scenario_spec_id=env["scenario_id"],
            # scenario_spec_version is None -> latest
        )

        with patch(
            "src.services.run_execution.load_satellite_coefficients"
        ) as mock_load:
            from src.engine.satellites import SatelliteCoefficients
            from src.data.workforce.satellite_coeff_loader import (
                LoadedCoefficients,
                CoefficientProvenance,
            )
            mock_coeffs = SatelliteCoefficients(
                jobs_coeff=np.array([0.01, 0.02, 0.015]),
                import_ratio=np.array([0.15, 0.15, 0.15]),
                va_ratio=np.array([0.5, 0.4, 0.6]),
                version_id=new_uuid7(),
            )
            mock_load.return_value = LoadedCoefficients(
                coefficients=mock_coeffs,
                provenance=CoefficientProvenance(
                    employment_coeff_year=2023,
                    io_base_year=2023,
                    import_ratio_year=2023,
                    va_ratio_year=2023,
                ),
            )

            result = await svc.execute_from_scenario(inp, repos)

        assert result.status == "COMPLETED"
        assert result.scenario_spec_version == 1  # only version 1 exists


# ------------------------------------------------------------------
# Finding 1 regression: _build_annual_shocks must parse real shocks
# ------------------------------------------------------------------


class TestBuildAnnualShocksRegression:
    """Finding 1: _build_annual_shocks must produce non-zero vectors from shock_items."""

    def test_single_final_demand_shock(self):
        """A single FINAL_DEMAND_SHOCK should produce a non-zero delta vector."""
        from src.services.run_execution import RunExecutionService

        svc = RunExecutionService()
        shock_items = [
            {
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": "B",
                "year": 2023,
                "amount_real_base_year": 500_000_000.0,
                "domestic_share": 0.8,
            },
        ]
        result = svc._build_annual_shocks(shock_items, base_year=2023, sector_codes=["A", "B", "C"])

        assert 2023 in result
        delta = result[2023]
        assert delta[0] == 0.0  # sector A: no shock
        assert delta[1] == pytest.approx(400_000_000.0)  # 500M * 0.8
        assert delta[2] == 0.0  # sector C: no shock

    def test_multiple_shocks_same_year(self):
        """Multiple shocks on different sectors in the same year accumulate."""
        from src.services.run_execution import RunExecutionService

        svc = RunExecutionService()
        shock_items = [
            {
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": "A",
                "year": 2023,
                "amount_real_base_year": 100_000_000.0,
                "domestic_share": 1.0,
            },
            {
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": "C",
                "year": 2023,
                "amount_real_base_year": 200_000_000.0,
                "domestic_share": 0.5,
            },
        ]
        result = svc._build_annual_shocks(shock_items, base_year=2023, sector_codes=["A", "B", "C"])

        delta = result[2023]
        assert delta[0] == pytest.approx(100_000_000.0)
        assert delta[1] == 0.0
        assert delta[2] == pytest.approx(100_000_000.0)  # 200M * 0.5

    def test_multi_year_shocks(self):
        """Shocks in different years produce separate delta vectors."""
        from src.services.run_execution import RunExecutionService

        svc = RunExecutionService()
        shock_items = [
            {
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": "A",
                "year": 2023,
                "amount_real_base_year": 100.0,
                "domestic_share": 1.0,
            },
            {
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": "A",
                "year": 2024,
                "amount_real_base_year": 200.0,
                "domestic_share": 1.0,
            },
        ]
        result = svc._build_annual_shocks(shock_items, base_year=2023, sector_codes=["A", "B"])

        assert 2023 in result
        assert 2024 in result
        assert result[2023][0] == pytest.approx(100.0)
        assert result[2024][0] == pytest.approx(200.0)

    def test_non_final_demand_shocks_ignored(self):
        """Non-FINAL_DEMAND_SHOCK types should not contribute to delta vectors."""
        from src.services.run_execution import RunExecutionService

        svc = RunExecutionService()
        shock_items = [
            {
                "type": "IMPORT_SUBSTITUTION",
                "sector_code": "A",
                "year": 2023,
                "delta_import_share": -0.1,
            },
            {
                "type": "LOCAL_CONTENT",
                "sector_code": "B",
                "year": 2023,
                "target_domestic_share": 0.7,
            },
        ]
        result = svc._build_annual_shocks(shock_items, base_year=2023, sector_codes=["A", "B"])

        # Only base_year fallback with zero vector
        assert 2023 in result
        assert np.all(result[2023] == 0.0)

    def test_unknown_sector_code_skipped(self):
        """Shocks with unknown sector codes should be skipped, not crash."""
        from src.services.run_execution import RunExecutionService

        svc = RunExecutionService()
        shock_items = [
            {
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": "Z",  # not in model
                "year": 2023,
                "amount_real_base_year": 100.0,
                "domestic_share": 1.0,
            },
        ]
        result = svc._build_annual_shocks(shock_items, base_year=2023, sector_codes=["A", "B"])

        assert 2023 in result
        assert np.all(result[2023] == 0.0)

    def test_empty_shocks_returns_zero_delta(self):
        """Empty shock_items should return a zero delta at base_year."""
        from src.services.run_execution import RunExecutionService

        svc = RunExecutionService()
        result = svc._build_annual_shocks([], base_year=2023, sector_codes=["A", "B", "C"])

        assert 2023 in result
        assert np.all(result[2023] == 0.0)
        assert result[2023].shape == (3,)

    def test_domestic_share_defaults_to_one(self):
        """If domestic_share is omitted, default to 1.0 (full amount)."""
        from src.services.run_execution import RunExecutionService

        svc = RunExecutionService()
        shock_items = [
            {
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": "A",
                "year": 2023,
                "amount_real_base_year": 1000.0,
                # domestic_share omitted -> should default to 1.0
            },
        ]
        result = svc._build_annual_shocks(shock_items, base_year=2023, sector_codes=["A", "B"])

        assert result[2023][0] == pytest.approx(1000.0)

    def test_same_sector_accumulates(self):
        """Multiple shocks on the same sector in the same year should accumulate."""
        from src.services.run_execution import RunExecutionService

        svc = RunExecutionService()
        shock_items = [
            {
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": "A",
                "year": 2023,
                "amount_real_base_year": 100.0,
                "domestic_share": 1.0,
            },
            {
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": "A",
                "year": 2023,
                "amount_real_base_year": 50.0,
                "domestic_share": 1.0,
            },
        ]
        result = svc._build_annual_shocks(shock_items, base_year=2023, sector_codes=["A"])

        assert result[2023][0] == pytest.approx(150.0)


class TestExecuteFromScenarioWithRealShocks:
    """Finding 1 integration: execute_from_scenario with real shock_items
    must produce non-zero impacts (not an identity run)."""

    async def test_non_identity_run_with_shocks(self, db_env_with_shocks):
        """Scenario with FINAL_DEMAND_SHOCK must produce non-zero result_summary."""
        from src.services.run_execution import RunExecutionService, RunFromScenarioInput

        env = db_env_with_shocks
        session = env["session"]
        repos = _make_repos(session)
        svc = RunExecutionService()
        inp = RunFromScenarioInput(
            workspace_id=env["ws_id"],
            scenario_spec_id=env["scenario_id"],
            scenario_spec_version=1,
        )

        with patch(
            "src.services.run_execution.load_satellite_coefficients"
        ) as mock_load:
            from src.engine.satellites import SatelliteCoefficients
            from src.data.workforce.satellite_coeff_loader import (
                LoadedCoefficients,
                CoefficientProvenance,
            )
            mock_coeffs = SatelliteCoefficients(
                jobs_coeff=np.array([0.01, 0.02, 0.015]),
                import_ratio=np.array([0.15, 0.15, 0.15]),
                va_ratio=np.array([0.5, 0.4, 0.6]),
                version_id=new_uuid7(),
            )
            mock_load.return_value = LoadedCoefficients(
                coefficients=mock_coeffs,
                provenance=CoefficientProvenance(
                    employment_coeff_year=2023,
                    io_base_year=2023,
                    import_ratio_year=2023,
                    va_ratio_year=2023,
                ),
            )

            result = await svc.execute_from_scenario(inp, repos)

        assert result.status == "COMPLETED"
        assert result.run_id is not None
        assert result.result_summary is not None

        # Critical: the result_summary should contain non-zero values
        # because we applied a 400M SAR shock to sector B
        # (500M * 0.8 domestic_share)
        has_nonzero = False
        for metric_type, values in result.result_summary.items():
            if isinstance(values, dict):
                for v in values.values():
                    if isinstance(v, (int, float)) and v != 0:
                        has_nonzero = True
                        break
            if has_nonzero:
                break
        assert has_nonzero, (
            "Finding 1 regression: result_summary is all zeros — "
            "_build_annual_shocks is not applying shocks"
        )
