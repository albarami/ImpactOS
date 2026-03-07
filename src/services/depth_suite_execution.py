"""Persisted depth suite execution service.

Bridges a persisted depth plan into the normal scenario -> run execution path.
No in-memory fake suite execution and no parallel engine path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.compiler.scenario_compiler import CompilationInput, draft_compilation_assumptions
from src.models.common import new_uuid7
from src.models.depth import MuhasabaOutput, ScenarioSuitePlan, SuitePlanningOutput, SuiteRun
from src.models.scenario import TimeHorizon
from src.repositories.depth import DepthArtifactRepository, DepthPlanRepository
from src.repositories.engine import (
    BatchRepository,
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.feasibility import ConstraintSetRepository
from src.repositories.governance import AssumptionRepository, ClaimRepository
from src.repositories.scenarios import ScenarioVersionRepository
from src.repositories.workforce import WorkforceResultRepository
from src.services.run_execution import RunExecutionService, RunFromScenarioInput, RunRepositories

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DepthSuiteExecutionInput:
    workspace_id: UUID
    model_version_id: UUID | None = None
    base_year: int | None = None


@dataclass(frozen=True)
class DepthSuiteExecutionResult:
    status: str
    plan_id: UUID
    suite_id: UUID | None = None
    batch_id: UUID | None = None
    scenario_spec_ids: list[UUID] = field(default_factory=list)
    run_ids: list[UUID] = field(default_factory=list)
    total_scenarios: int = 0
    completed: int = 0
    failed: int = 0
    error: str | None = None


class DepthSuiteExecutionService:
    """Materialize a persisted suite plan into real scenarios and runs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def execute(
        self,
        plan_id: UUID,
        inp: DepthSuiteExecutionInput,
    ) -> DepthSuiteExecutionResult:
        plan_repo = DepthPlanRepository(self._session)
        artifact_repo = DepthArtifactRepository(self._session)
        scenario_repo = ScenarioVersionRepository(self._session)
        assumption_repo = AssumptionRepository(self._session)
        batch_repo = BatchRepository(self._session)
        mv_repo = ModelVersionRepository(self._session)
        md_repo = ModelDataRepository(self._session)
        snap_repo = RunSnapshotRepository(self._session)
        rs_repo = ResultSetRepository(self._session)
        claim_repo = ClaimRepository(self._session)
        constraint_repo = ConstraintSetRepository(self._session)
        workforce_result_repo = WorkforceResultRepository(self._session)

        plan_row = await plan_repo.get(plan_id)
        if plan_row is None or plan_row.workspace_id != inp.workspace_id:
            return DepthSuiteExecutionResult(
                status="FAILED",
                plan_id=plan_id,
                error=f"Depth plan {plan_id} not found in workspace",
            )

        suite_artifact = await artifact_repo.get_by_plan_and_step(plan_id, "SUITE_PLANNING")
        if suite_artifact is None:
            return DepthSuiteExecutionResult(
                status="FAILED",
                plan_id=plan_id,
                error=f"Depth plan {plan_id} has no SUITE_PLANNING artifact",
            )

        suite_output = SuitePlanningOutput.model_validate(suite_artifact.payload)
        suite_plan = suite_output.suite_plan
        model_version_id, base_year = await self._resolve_runtime_context(
            plan_row=plan_row,
            inp=inp,
            scenario_repo=scenario_repo,
            mv_repo=mv_repo,
        )

        muhasaba_status = await self._load_muhasaba_status(plan_id, artifact_repo)
        run_service = RunExecutionService()
        run_repos = RunRepositories(
            scenario_repo=scenario_repo,
            mv_repo=mv_repo,
            md_repo=md_repo,
            snap_repo=snap_repo,
            rs_repo=rs_repo,
            claim_repo=claim_repo,
            constraint_repo=constraint_repo,
            workforce_result_repo=workforce_result_repo,
        )

        scenario_spec_ids: list[UUID] = []
        run_ids: list[UUID] = []
        suite_run_rows: list[dict] = []
        sensitivity_rows: list[dict] = []
        failed = 0

        for suite_run in suite_plan.runs:
            variants = suite_run.sensitivity_multipliers or [1.0]
            for multiplier in variants:
                materialized = self._materialize_shock_items(
                    suite_run=suite_run,
                    base_year=base_year,
                    multiplier=multiplier,
                )
                if not materialized:
                    failed += 1
                    continue

                scenario_spec_id = new_uuid7()
                assumption_ids = await self._create_scenario_assumptions(
                    assumption_repo=assumption_repo,
                    workspace_id=inp.workspace_id,
                    scenario_spec_id=scenario_spec_id,
                    name=suite_run.name,
                    model_version_id=model_version_id,
                    base_year=base_year,
                )
                scenario_name = self._variant_name(suite_run.name, multiplier, variants)

                scenario_row = await scenario_repo.create(
                    scenario_spec_id=scenario_spec_id,
                    version=1,
                    name=scenario_name,
                    workspace_id=inp.workspace_id,
                    base_model_version_id=model_version_id,
                    base_year=base_year,
                    time_horizon={"start_year": base_year, "end_year": base_year},
                    shock_items=materialized,
                    assumption_ids=[str(aid) for aid in assumption_ids],
                    data_quality_summary={
                        "depth_plan_id": str(plan_id),
                        "suite_id": str(suite_plan.suite_id),
                        "direction_id": str(suite_run.direction_id),
                        "suite_run_name": suite_run.name,
                        "sensitivity_multiplier": multiplier,
                        "mode": suite_run.mode,
                        "is_contrarian": suite_run.is_contrarian,
                        "muhasaba_status": muhasaba_status.get(
                            str(suite_run.direction_id), "SURVIVED",
                        ),
                    },
                )
                scenario_spec_ids.append(scenario_row.scenario_spec_id)

                run_result = await run_service.execute_from_scenario(
                    RunFromScenarioInput(
                        workspace_id=inp.workspace_id,
                        scenario_spec_id=scenario_row.scenario_spec_id,
                        scenario_spec_version=scenario_row.version,
                    ),
                    run_repos,
                )
                if run_result.status != "COMPLETED" or run_result.run_id is None:
                    failed += 1
                    continue

                run_ids.append(run_result.run_id)
                total_output = self._aggregate_metric(run_result.result_summary, "total_output")
                employment = self._aggregate_metric(run_result.result_summary, "employment")
                muhasaba_row_status = muhasaba_status.get(
                    str(suite_run.direction_id), "SURVIVED",
                )
                row_summary = {
                    "scenario_spec_id": str(scenario_row.scenario_spec_id),
                    "scenario_spec_version": scenario_row.version,
                    "run_id": str(run_result.run_id),
                    "direction_id": str(suite_run.direction_id),
                    "name": scenario_name,
                    "mode": suite_run.mode,
                    "is_contrarian": suite_run.is_contrarian,
                    "multiplier": multiplier,
                    "headline_output": total_output,
                    "employment": employment,
                    "muhasaba_status": muhasaba_row_status,
                    "sensitivities": suite_run.sensitivities,
                }
                suite_run_rows.append(row_summary)
                if len(variants) > 1:
                    sensitivity_rows.append(row_summary)

        batch_id = new_uuid7()
        status = "COMPLETED" if failed == 0 else ("PARTIAL" if run_ids else "FAILED")
        await batch_repo.create(
            batch_id=batch_id,
            run_ids=[str(run_id) for run_id in run_ids],
            status=status,
            workspace_id=inp.workspace_id,
        )

        await artifact_repo.create(
            artifact_id=new_uuid7(),
            plan_id=plan_id,
            step="SUITE_EXECUTION",
            payload={
                "plan_id": str(plan_id),
                "suite_id": str(suite_plan.suite_id),
                "batch_id": str(batch_id),
                "scenario_spec_ids": [str(sid) for sid in scenario_spec_ids],
                "run_ids": [str(rid) for rid in run_ids],
                "total_scenarios": len(suite_run_rows) + failed,
                "completed": len(run_ids),
                "failed": failed,
                "suite_rationale": suite_plan.rationale,
                "suite_runs": suite_run_rows,
                "sensitivity_runs": sensitivity_rows,
                "qualitative_risks": [
                    risk.model_dump(mode="json") for risk in suite_plan.qualitative_risks
                ],
            },
            disclosure_tier=suite_artifact.disclosure_tier,
            metadata_json={"status": status},
        )

        return DepthSuiteExecutionResult(
            status=status,
            plan_id=plan_id,
            suite_id=suite_plan.suite_id,
            batch_id=batch_id,
            scenario_spec_ids=scenario_spec_ids,
            run_ids=run_ids,
            total_scenarios=len(suite_run_rows) + failed,
            completed=len(run_ids),
            failed=failed,
        )

    async def _resolve_runtime_context(
        self,
        *,
        plan_row,
        inp: DepthSuiteExecutionInput,
        scenario_repo: ScenarioVersionRepository,
        mv_repo: ModelVersionRepository,
    ) -> tuple[UUID, int]:
        if inp.model_version_id is not None:
            mv_row = await mv_repo.get(inp.model_version_id)
            if mv_row is not None:
                return inp.model_version_id, inp.base_year or mv_row.base_year

        if plan_row.scenario_spec_id is not None:
            scenario_row = await scenario_repo.get_latest_by_workspace(
                plan_row.scenario_spec_id, inp.workspace_id,
            )
            if scenario_row is not None:
                return scenario_row.base_model_version_id, inp.base_year or scenario_row.base_year

        mv_rows = await mv_repo.list_all()
        if not mv_rows:
            raise ValueError("No model versions available for depth suite execution")
        mv_row = mv_rows[0]
        return mv_row.model_version_id, inp.base_year or mv_row.base_year

    async def _load_muhasaba_status(
        self,
        plan_id: UUID,
        artifact_repo: DepthArtifactRepository,
    ) -> dict[str, str]:
        artifact = await artifact_repo.get_by_plan_and_step(plan_id, "MUHASABA")
        if artifact is None:
            return {}
        try:
            output = MuhasabaOutput.model_validate(artifact.payload)
        except Exception:
            return {}
        status_map: dict[str, str] = {}
        for scored in output.scored:
            status_map[str(scored.direction_id)] = "SURVIVED" if scored.accepted else "REJECTED"
        return status_map

    async def _create_scenario_assumptions(
        self,
        *,
        assumption_repo: AssumptionRepository,
        workspace_id: UUID,
        scenario_spec_id: UUID,
        name: str,
        model_version_id: UUID,
        base_year: int,
    ) -> list[UUID]:
        assumptions = draft_compilation_assumptions(
            CompilationInput(
                workspace_id=workspace_id,
                scenario_name=name,
                base_model_version_id=model_version_id,
                base_year=base_year,
                time_horizon=TimeHorizon(start_year=base_year, end_year=base_year),
                line_items=[],
                decisions=[],
                default_domestic_share=0.65,
                default_import_share=0.35,
            )
        )
        assumption_ids: list[UUID] = []
        for assumption in assumptions:
            assumption_ids.append(assumption.assumption_id)
            await assumption_repo.create(
                assumption_id=assumption.assumption_id,
                type=assumption.type.value,
                value=assumption.value,
                units=assumption.units,
                justification=assumption.justification,
                status=assumption.status.value,
                workspace_id=workspace_id,
            )
            await assumption_repo.link(
                assumption.assumption_id,
                scenario_spec_id,
                link_type="scenario",
            )
        return assumption_ids

    def _materialize_shock_items(
        self,
        *,
        suite_run: SuiteRun,
        base_year: int,
        multiplier: float,
    ) -> list[dict]:
        shock_items: list[dict] = []

        for lever in suite_run.executable_levers:
            lever_type = lever.get("type")
            if lever_type != "FINAL_DEMAND_SHOCK":
                continue
            sector_code = lever.get("sector_code") or lever.get("sector")
            amount = lever.get("amount_real_base_year", lever.get("value"))
            if sector_code is None or amount is None:
                continue
            shock_items.append({
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": sector_code,
                "year": int(lever.get("year", base_year)),
                "amount_real_base_year": float(amount) * float(multiplier),
                "domestic_share": float(lever.get("domestic_share", 1.0)),
            })

        if shock_items:
            return shock_items

        for shock in suite_run.proposed_shock_specs:
            shock_items.append({
                "type": "FINAL_DEMAND_SHOCK",
                "sector_code": shock.sector_code,
                "year": int(shock.shock_year or base_year),
                "amount_real_base_year": float(shock.shock_value) * float(multiplier),
                "domestic_share": float(1.0 - (shock.import_share_override or 0.0)),
            })
        return shock_items

    @staticmethod
    def _variant_name(name: str, multiplier: float, variants: list[float]) -> str:
        if len(variants) == 1 and abs(multiplier - 1.0) < 1e-9:
            return name
        return f"{name} x{multiplier:g}"

    @staticmethod
    def _aggregate_metric(result_summary: dict | None, metric_type: str) -> float | None:
        if not result_summary or metric_type not in result_summary:
            return None
        values = result_summary[metric_type]
        if not isinstance(values, dict):
            return None
        return float(sum(float(v) for v in values.values()))
