"""Tests for the persisted DepthSuiteExecutionService and chat wiring."""

from uuid import uuid4
from unittest.mock import patch

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.session import Base
import src.db.tables  # noqa: F401
from src.db.tables import (
    BatchRow,
    ClaimRow,
    DepthArtifactRow,
    DepthPlanRow,
    ModelDataRow,
    ModelVersionRow,
    ResultSetRow,
    RunSnapshotRow,
    ScenarioSpecRow,
    WorkspaceRow,
    WorkforceResultRow,
)
from src.models.common import DisclosureTier, new_uuid7, utc_now
from src.models.depth import (
    QualitativeRisk,
    ScenarioSuitePlan,
    SuitePlanningOutput,
    SuiteRun,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
async def suite_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        ws_id = new_uuid7()
        mv_id = new_uuid7()
        plan_id = new_uuid7()
        now = utc_now()

        session.add(WorkspaceRow(
            workspace_id=ws_id,
            client_name="Depth Suite Client",
            engagement_code="DEPTH-001",
            classification="INTERNAL",
            description="depth suite execution test",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        ))
        session.add(ModelVersionRow(
            model_version_id=mv_id,
            base_year=2023,
            source="test",
            sector_count=3,
            checksum="sha256:1bb9deeef3696f1d6b544ca7e10a3cd14e0cf9437047501b48fa6bc9a72b65a7",
            provenance_class="curated_real",
            model_denomination="SAR_THOUSANDS",
            created_at=now,
        ))
        session.add(ModelDataRow(
            model_version_id=mv_id,
            z_matrix_json=[[0.1, 0.2, 0.0], [0.0, 0.1, 0.3], [0.1, 0.0, 0.1]],
            x_vector_json=[100.0, 200.0, 150.0],
            sector_codes=["A", "F", "I"],
        ))
        session.add(DepthPlanRow(
            plan_id=plan_id,
            workspace_id=ws_id,
            scenario_spec_id=None,
            engagement_id=None,
            status="COMPLETED",
            current_step="SUITE_PLANNING",
            degraded_steps=[],
            step_errors={},
            step_metadata=[
                {
                    "step": 1,
                    "step_name": "KHAWATIR",
                    "provider": "anthropic",
                    "model": "claude-test",
                    "generation_mode": "LLM",
                    "duration_ms": 10,
                    "input_tokens": 1,
                    "output_tokens": 1,
                }
            ],
            error_message=None,
            created_at=now,
            updated_at=now,
        ))

        suite_plan = ScenarioSuitePlan(
            workspace_id=ws_id,
            runs=[
                SuiteRun(
                    name="Base contraction",
                    direction_id=new_uuid7(),
                    executable_levers=[{
                        "type": "FINAL_DEMAND_SHOCK",
                        "sector_code": "F",
                        "amount_real_base_year": -500_000_000.0,
                        "domestic_share": 0.8,
                        "year": 2023,
                    }],
                    mode="GOVERNED",
                    sensitivities=["volume"],
                    sensitivity_multipliers=[0.8, 1.0, 1.2],
                ),
                SuiteRun(
                    name="Contrarian offset",
                    direction_id=new_uuid7(),
                    executable_levers=[{
                        "type": "FINAL_DEMAND_SHOCK",
                        "sector_code": "I",
                        "amount_real_base_year": 100_000_000.0,
                        "domestic_share": 0.7,
                        "year": 2023,
                    }],
                    mode="SANDBOX",
                    is_contrarian=True,
                    sensitivity_multipliers=[1.0],
                ),
            ],
            qualitative_risks=[
                QualitativeRisk(
                    label="Border congestion",
                    description="Throughput loss not represented in IO coefficients.",
                    disclosure_tier=DisclosureTier.TIER1,
                    affected_sectors=["F", "I"],
                    trigger_conditions=["visa rule enforced mid-season"],
                    expected_direction="negative",
                )
            ],
            rationale="Depth suite rationale",
            export_mode="SANDBOX",
            disclosure_tier=DisclosureTier.TIER1,
        )
        session.add(DepthArtifactRow(
            artifact_id=new_uuid7(),
            plan_id=plan_id,
            step="SUITE_PLANNING",
            payload=SuitePlanningOutput(suite_plan=suite_plan).model_dump(mode="json"),
            disclosure_tier="TIER1",
            metadata_json={},
            created_at=now,
        ))
        await session.flush()

        yield {
            "session": session,
            "workspace_id": ws_id,
            "model_version_id": mv_id,
            "plan_id": plan_id,
        }
    await engine.dispose()


class TestDepthSuiteExecutionService:
    async def test_service_is_importable(self, suite_env):
        from src.services.depth_suite_execution import DepthSuiteExecutionService

        svc = DepthSuiteExecutionService(suite_env["session"])
        assert svc is not None

    async def test_execute_materializes_scenarios_runs_claims_and_workforce(self, suite_env):
        from src.data.workforce.satellite_coeff_loader import (
            CoefficientProvenance,
            LoadedCoefficients,
        )
        from src.engine.satellites import SatelliteCoefficients
        from src.services.depth_suite_execution import (
            DepthSuiteExecutionInput,
            DepthSuiteExecutionService,
        )

        session = suite_env["session"]
        svc = DepthSuiteExecutionService(session)
        inp = DepthSuiteExecutionInput(
            workspace_id=suite_env["workspace_id"],
            model_version_id=suite_env["model_version_id"],
            base_year=2023,
        )

        mock_coeffs = SatelliteCoefficients(
            jobs_coeff=np.array([0.01, 0.02, 0.015]),
            import_ratio=np.array([0.10, 0.20, 0.30]),
            va_ratio=np.array([0.5, 0.4, 0.6]),
            version_id=new_uuid7(),
        )

        with patch("src.services.run_execution.load_satellite_coefficients") as mock_load:
            mock_load.return_value = LoadedCoefficients(
                coefficients=mock_coeffs,
                provenance=CoefficientProvenance(
                    employment_coeff_year=2023,
                    io_base_year=2023,
                    import_ratio_year=2023,
                    va_ratio_year=2023,
                ),
            )
            result = await svc.execute(suite_env["plan_id"], inp)

        assert result.status == "COMPLETED"
        assert result.batch_id is not None
        assert result.total_scenarios == 4
        assert len(result.scenario_spec_ids) == 4
        assert len(result.run_ids) == 4
        assert result.completed == 4
        assert result.failed == 0

        scenarios = list((await session.execute(select(ScenarioSpecRow))).scalars().all())
        snapshots = list((await session.execute(select(RunSnapshotRow))).scalars().all())
        result_sets = list((await session.execute(select(ResultSetRow))).scalars().all())
        claims = list((await session.execute(select(ClaimRow))).scalars().all())
        batches = list((await session.execute(select(BatchRow))).scalars().all())
        workforce_rows = list((await session.execute(select(WorkforceResultRow))).scalars().all())
        suite_artifacts = list((await session.execute(
            select(DepthArtifactRow).where(DepthArtifactRow.step == "SUITE_EXECUTION")
        )).scalars().all())

        assert len(scenarios) == 4
        assert len(snapshots) == 4
        assert len(result_sets) >= 4
        assert len(claims) >= 4
        assert len(batches) == 1
        assert len(workforce_rows) == 4
        assert len(suite_artifacts) == 1
        assert suite_artifacts[0].payload["run_ids"]

    async def test_chat_executor_suite_execution_returns_ids(self, suite_env):
        from src.data.workforce.satellite_coeff_loader import (
            CoefficientProvenance,
            LoadedCoefficients,
        )
        from src.engine.satellites import SatelliteCoefficients
        from src.services.chat_tool_executor import ChatToolExecutor

        executor = ChatToolExecutor(
            session=suite_env["session"],
            workspace_id=suite_env["workspace_id"],
        )
        mock_coeffs = SatelliteCoefficients(
            jobs_coeff=np.array([0.01, 0.02, 0.015]),
            import_ratio=np.array([0.10, 0.20, 0.30]),
            va_ratio=np.array([0.5, 0.4, 0.6]),
            version_id=new_uuid7(),
        )

        with patch("src.services.run_execution.load_satellite_coefficients") as mock_load:
            mock_load.return_value = LoadedCoefficients(
                coefficients=mock_coeffs,
                provenance=CoefficientProvenance(
                    employment_coeff_year=2023,
                    io_base_year=2023,
                    import_ratio_year=2023,
                    va_ratio_year=2023,
                ),
            )
            result = await executor._execute_depth_suite_runs(
                plan_id=suite_env["plan_id"],
                base_year=2023,
                model_version_id=str(suite_env["model_version_id"]),
            )

        assert result is not None
        assert result["batch_id"]
        assert len(result["scenario_spec_ids"]) == 4
        assert len(result["run_ids"]) == 4
        assert result["completed"] == 4
        assert result["failed"] == 0
