"""Tests for DepthSuiteExecutionService (Step 2).

TDD: Failing tests first, then implementation.
Tests prove that run_depth_suite on the chat path actually executes
SuiteRun entries via BatchRunner and returns real run results.
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from src.models.common import new_uuid7

pytestmark = pytest.mark.anyio


class TestDepthSuiteExecutionService:
    """Step 2: DepthSuiteExecutionService converts a ScenarioSuitePlan
    into real BatchRunner executions and persists results."""

    async def test_service_exists_and_is_importable(self):
        """DepthSuiteExecutionService must be importable."""
        from src.services.depth_suite_execution import DepthSuiteExecutionService
        svc = DepthSuiteExecutionService()
        assert svc is not None

    async def test_execute_plan_returns_run_ids(self):
        """execute_plan should return run_ids for each SuiteRun executed."""
        from src.services.depth_suite_execution import (
            DepthSuiteExecutionService,
            DepthSuiteExecutionInput,
        )
        from src.models.depth import ScenarioSuitePlan, SuiteRun

        ws_id = new_uuid7()
        mv_id = new_uuid7()
        scenario_id = new_uuid7()

        # Build a minimal ScenarioSuitePlan with 2 runs
        plan = ScenarioSuitePlan(
            workspace_id=ws_id,
            runs=[
                SuiteRun(
                    name="Run: Construction growth",
                    direction_id=new_uuid7(),
                    executable_levers=[{
                        "type": "FINAL_DEMAND_SHOCK",
                        "sector_code": "F",
                        "amount_real_base_year": 1_000_000_000,
                        "domestic_share": 0.85,
                    }],
                    sensitivity_multipliers=[1.0],
                ),
                SuiteRun(
                    name="Run: Tourism expansion",
                    direction_id=new_uuid7(),
                    executable_levers=[{
                        "type": "FINAL_DEMAND_SHOCK",
                        "sector_code": "I",
                        "amount_real_base_year": 500_000_000,
                        "domestic_share": 0.70,
                    }],
                    sensitivity_multipliers=[0.8, 1.0, 1.2],
                ),
            ],
            rationale="Two scenarios for deep-dive analysis",
        )

        # Mock model with 3 sectors
        mock_loaded = MagicMock()
        mock_loaded.sector_codes = ["A", "F", "I"]
        mock_loaded.model_version.model_version_id = mv_id
        mock_loaded.model_version.model_denomination = "SAR_MILLIONS"
        mock_loaded.n = 3

        # Mock BatchRunner result
        from src.engine.batch import SingleRunResult
        from src.models.run import RunSnapshot

        mock_results = []
        for i in range(4):  # 1 run + 3 sensitivity variants
            rid = new_uuid7()
            mock_sr = MagicMock(spec=SingleRunResult)
            mock_sr.snapshot = MagicMock(spec=RunSnapshot)
            mock_sr.snapshot.run_id = rid
            mock_sr.result_sets = []
            mock_results.append(mock_sr)

        mock_batch_result = MagicMock()
        mock_batch_result.run_results = mock_results

        svc = DepthSuiteExecutionService()

        inp = DepthSuiteExecutionInput(
            workspace_id=ws_id,
            model_version_id=mv_id,
            base_year=2023,
            scenario_spec_id=scenario_id,
        )

        with patch.object(svc, "_get_loaded_model", return_value=mock_loaded), \
             patch.object(svc, "_run_batch", return_value=mock_batch_result):
            result = await svc.execute_plan(plan, inp)

        assert result.status == "COMPLETED"
        assert len(result.run_ids) == 4  # 1 + 3 sensitivity variants
        assert result.suite_id == plan.suite_id

    async def test_execute_plan_converts_levers_to_shocks(self):
        """execute_plan must convert SuiteRun.executable_levers to
        BatchRunner.ScenarioInput.annual_shocks."""
        from src.services.depth_suite_execution import (
            DepthSuiteExecutionService,
            DepthSuiteExecutionInput,
        )
        from src.models.depth import ScenarioSuitePlan, SuiteRun

        ws_id = new_uuid7()
        mv_id = new_uuid7()

        plan = ScenarioSuitePlan(
            workspace_id=ws_id,
            runs=[
                SuiteRun(
                    name="Run: Single sector",
                    direction_id=new_uuid7(),
                    executable_levers=[{
                        "type": "FINAL_DEMAND_SHOCK",
                        "sector_code": "F",
                        "amount_real_base_year": 1_000_000_000,
                        "domestic_share": 0.85,
                    }],
                    sensitivity_multipliers=[1.0],
                ),
            ],
        )

        # Mock model
        mock_loaded = MagicMock()
        mock_loaded.sector_codes = ["A", "F", "I"]
        mock_loaded.model_version.model_version_id = mv_id
        mock_loaded.model_version.model_denomination = "SAR_MILLIONS"
        mock_loaded.n = 3

        mock_batch_result = MagicMock()
        mock_sr = MagicMock()
        mock_sr.snapshot = MagicMock()
        mock_sr.snapshot.run_id = new_uuid7()
        mock_sr.result_sets = []
        mock_batch_result.run_results = [mock_sr]

        svc = DepthSuiteExecutionService()

        inp = DepthSuiteExecutionInput(
            workspace_id=ws_id,
            model_version_id=mv_id,
            base_year=2023,
        )

        captured_request = {}

        def capture_batch(request, **kwargs):
            captured_request["req"] = request
            return mock_batch_result

        with patch.object(svc, "_get_loaded_model", return_value=mock_loaded), \
             patch.object(svc, "_run_batch", side_effect=capture_batch):
            await svc.execute_plan(plan, inp)

        req = captured_request["req"]
        assert len(req.scenarios) == 1
        scenario = req.scenarios[0]
        assert scenario.name == "Run: Single sector"
        assert scenario.sensitivity_multipliers == [1.0]
        # Shock in sector F (index 1) should be 1B * 0.85
        assert 2023 in scenario.annual_shocks
        shock_vec = scenario.annual_shocks[2023]
        assert shock_vec[1] == pytest.approx(1_000_000_000 * 0.85)

    async def test_execute_plan_empty_suite(self):
        """execute_plan with no runs should return COMPLETED with empty results."""
        from src.services.depth_suite_execution import (
            DepthSuiteExecutionService,
            DepthSuiteExecutionInput,
        )
        from src.models.depth import ScenarioSuitePlan

        ws_id = new_uuid7()
        plan = ScenarioSuitePlan(workspace_id=ws_id, runs=[])

        svc = DepthSuiteExecutionService()
        inp = DepthSuiteExecutionInput(
            workspace_id=ws_id,
            model_version_id=new_uuid7(),
            base_year=2023,
        )

        result = await svc.execute_plan(plan, inp)

        assert result.status == "COMPLETED"
        assert len(result.run_ids) == 0


class TestDepthSuiteInChatHandler:
    """Step 2: run_depth_suite chat handler must execute the suite plan
    and return real run_ids in the response."""

    async def test_handler_returns_run_ids_after_execution(self):
        """_handle_run_depth_suite must return run_ids and suite_id
        when the depth plan produces a ScenarioSuitePlan."""
        from src.services.chat_tool_executor import ChatToolExecutor

        session = AsyncMock()
        executor = ChatToolExecutor(
            session=session,
            workspace_id=new_uuid7(),
        )

        plan_id = new_uuid7()
        suite_id = new_uuid7()
        run_ids = [new_uuid7(), new_uuid7()]

        # Mock the depth plan execution
        with patch("src.services.chat_tool_executor.run_depth_plan", return_value="COMPLETED"), \
             patch.object(
                 executor, "_execute_depth_suite_runs",
                 return_value={
                     "suite_id": str(suite_id),
                     "run_ids": [str(r) for r in run_ids],
                     "run_count": 2,
                 },
             ):
            result = await executor._handle_run_depth_suite({
                "key_questions": ["What is the GDP impact?"],
            })

        assert result["status"] == "COMPLETED"
        assert result["plan_id"] is not None
        assert "suite_id" in result
        assert "run_ids" in result
        assert len(result["run_ids"]) == 2
