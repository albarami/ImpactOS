"""DepthSuiteExecutionService — Step 2: Execute ScenarioSuitePlan runs.

Converts a ScenarioSuitePlan (produced by the Al-Muhāsibī depth engine)
into real BatchRunner executions. Each SuiteRun's executable_levers are
converted to annual_shocks, and sensitivity_multipliers are passed through
to BatchRunner for variant generation.

Deterministic — no LLM calls. Delegates all computation to the engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

import numpy as np

from src.engine.batch import BatchRequest, BatchResult, ScenarioInput
from src.models.common import new_uuid7
from src.models.depth import ScenarioSuitePlan, SuiteRun

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DepthSuiteExecutionInput:
    """Input for depth suite execution."""

    workspace_id: UUID
    model_version_id: UUID
    base_year: int
    scenario_spec_id: UUID | None = None


@dataclass(frozen=True)
class DepthSuiteExecutionResult:
    """Result of executing a ScenarioSuitePlan."""

    status: str  # "COMPLETED" or "FAILED"
    suite_id: UUID | None = None
    run_ids: list[UUID] = field(default_factory=list)
    run_count: int = 0
    error: str | None = None


class DepthSuiteExecutionService:
    """Execute ScenarioSuitePlan runs via BatchRunner.

    Step 2: Bridges the depth engine output (ScenarioSuitePlan) to the
    deterministic engine (BatchRunner). Each SuiteRun becomes a
    ScenarioInput with annual_shocks built from executable_levers.
    """

    async def execute_plan(
        self,
        plan: ScenarioSuitePlan,
        inp: DepthSuiteExecutionInput,
    ) -> DepthSuiteExecutionResult:
        """Execute all SuiteRun entries in the plan.

        1. Load the model.
        2. Convert each SuiteRun → ScenarioInput.
        3. Build a BatchRequest with all scenarios.
        4. Execute via BatchRunner.
        5. Return run IDs and status.
        """
        if not plan.runs:
            return DepthSuiteExecutionResult(
                status="COMPLETED",
                suite_id=plan.suite_id,
                run_ids=[],
                run_count=0,
            )

        try:
            loaded = self._get_loaded_model(inp.model_version_id)
        except Exception as exc:
            return DepthSuiteExecutionResult(
                status="FAILED",
                suite_id=plan.suite_id,
                error=f"Failed to load model: {str(exc)[:200]}",
            )

        sector_codes = loaded.sector_codes

        # Convert SuiteRuns → ScenarioInputs
        scenarios: list[ScenarioInput] = []
        for suite_run in plan.runs:
            annual_shocks = self._build_annual_shocks(
                suite_run.executable_levers,
                inp.base_year,
                sector_codes,
            )
            scenario = ScenarioInput(
                scenario_spec_id=inp.scenario_spec_id or new_uuid7(),
                scenario_spec_version=1,
                name=suite_run.name,
                annual_shocks=annual_shocks,
                base_year=inp.base_year,
                sensitivity_multipliers=suite_run.sensitivity_multipliers or None,
            )
            scenarios.append(scenario)

        # Build BatchRequest
        from src.data.workforce.satellite_coeff_loader import load_satellite_coefficients

        try:
            coeffs = load_satellite_coefficients(
                year=inp.base_year,
                sector_codes=sector_codes,
            )
        except Exception:
            from src.engine.satellites import SatelliteCoefficients
            coeffs = SatelliteCoefficients(
                jobs_coeff=np.zeros(len(sector_codes)),
                import_ratio=np.full(len(sector_codes), 0.15),
                va_ratio=np.full(len(sector_codes), 0.50),
                version_id=new_uuid7(),
            )

        version_refs = self._make_version_refs()

        request = BatchRequest(
            scenarios=scenarios,
            model_version_id=inp.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=version_refs,
        )

        try:
            batch_result = self._run_batch(request)
        except Exception as exc:
            return DepthSuiteExecutionResult(
                status="FAILED",
                suite_id=plan.suite_id,
                error=f"BatchRunner execution failed: {str(exc)[:200]}",
            )

        run_ids = [
            sr.snapshot.run_id for sr in batch_result.run_results
        ]

        _logger.info(
            "Step 2: Executed %d runs from depth suite %s",
            len(run_ids), plan.suite_id,
        )

        return DepthSuiteExecutionResult(
            status="COMPLETED",
            suite_id=plan.suite_id,
            run_ids=run_ids,
            run_count=len(run_ids),
        )

    def _get_loaded_model(self, model_version_id: UUID):
        """Load model from the global model store."""
        from src.services.run_execution import _model_store
        return _model_store.get(model_version_id)

    def _run_batch(self, request: BatchRequest, **kwargs) -> BatchResult:
        """Execute batch via BatchRunner."""
        from src.engine.batch import BatchRunner
        from src.config.settings import get_settings

        settings = get_settings()
        runner = BatchRunner(
            model_store=None,  # Not needed — model already in request
            environment=settings.ENVIRONMENT.value,
        )
        return runner.run(request)

    def _build_annual_shocks(
        self,
        shock_items: list[dict],
        base_year: int,
        sector_codes: list[str],
    ) -> dict[int, np.ndarray]:
        """Convert executable_levers → annual_shocks for BatchRunner.

        Same logic as RunExecutionService._build_annual_shocks().
        """
        sector_index = {code: i for i, code in enumerate(sector_codes)}
        n = len(sector_codes)
        year_shocks: dict[int, np.ndarray] = {}

        for item in shock_items:
            if item.get("type") != "FINAL_DEMAND_SHOCK":
                continue
            year = item.get("year", base_year)
            code = item.get("sector_code")
            amount = item.get("amount_real_base_year", 0.0)
            domestic_share = item.get("domestic_share", 1.0)

            if code not in sector_index:
                _logger.warning(
                    "Shock sector_code %r not in model sector_codes, skipping",
                    code,
                )
                continue

            if year not in year_shocks:
                year_shocks[year] = np.zeros(n, dtype=np.float64)

            year_shocks[year][sector_index[code]] += amount * domestic_share

        if not year_shocks:
            year_shocks[base_year] = np.zeros(n, dtype=np.float64)

        return year_shocks

    def _make_version_refs(self) -> dict[str, UUID]:
        """Generate placeholder version refs for engine run."""
        return {
            "taxonomy_version_id": new_uuid7(),
            "concordance_version_id": new_uuid7(),
            "mapping_library_version_id": new_uuid7(),
            "assumption_library_version_id": new_uuid7(),
            "prompt_pack_version_id": new_uuid7(),
        }
