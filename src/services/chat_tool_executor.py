"""ChatToolExecutor -- dispatches copilot tool calls to handlers (Sprint 28).

Executes tool calls proposed by the EconomistCopilot, enforcing per-turn
safety caps and measuring latency.  Handlers interact with repositories
to create scenarios, execute engine runs, read results, and create exports.

Agent-to-Math Boundary: this executor dispatches to deterministic engine
endpoints via RunExecutionService -- it never performs economic computations
itself.
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.depth.tasks import run_depth_plan
from src.models.chat import ToolCall, ToolExecutionResult
from src.models.common import ExportMode, new_uuid7

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Safety caps
# ------------------------------------------------------------------
MAX_TOOL_CALLS_PER_TURN = 5
_MAX_RUN_ENGINE_PER_TURN = 1
_MAX_CREATE_EXPORT_PER_TURN = 1

# Tools with per-turn caps (tool_name -> max per turn)
_PER_TOOL_CAPS: dict[str, int] = {
    "run_engine": _MAX_RUN_ENGINE_PER_TURN,
    "create_export": _MAX_CREATE_EXPORT_PER_TURN,
}

# Available dataset types for lookup_data
# Only list datasets with real handlers — do not advertise unimplemented stubs.
# P2-1: removed multipliers, macro_indicators (no handler exists)
# P2-2: employment_coefficients handler implemented (queries EmploymentCoefficientsRepository)
_AVAILABLE_DATASETS = [
    {"dataset_id": "io_tables", "description": "Input-Output tables (KAPSARC)"},
    {"dataset_id": "models", "description": "Available model versions"},
    {"dataset_id": "employment_coefficients", "description": "Employment coefficients by sector (jobs per million SAR)"},
]


# ------------------------------------------------------------------
# Executor
# ------------------------------------------------------------------


class ChatToolExecutor:
    """Dispatches tool calls to handlers with safety caps and latency tracking.

    Each handler receives a DB session and workspace_id for repository access.
    """

    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self._session = session
        self._workspace_id = workspace_id
        self._handler_map = {
            "lookup_data": self._handle_lookup_data,
            "build_scenario": self._handle_build_scenario,
            "run_engine": self._handle_run_engine,
            "narrate_results": self._handle_narrate_results,
            "create_export": self._handle_create_export,
            "run_depth_suite": self._handle_run_depth_suite,
        }

    def _get_handler(self, tool_name: str):
        """Return the handler for a tool, or None if unknown."""
        return self._handler_map.get(tool_name)

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    async def _handle_lookup_data(self, arguments: dict) -> dict:
        """Query curated datasets (P2-2: real data, not stubs).

        Dispatches on dataset_id:
          - (none)    → list available dataset types
          - "models"  → list available model versions
          - "io_tables" → return sector codes, output vector, denomination
                          (requires model_version_id)
        """
        from src.repositories.engine import ModelDataRepository, ModelVersionRepository

        dataset_id = arguments.get("dataset_id")

        # No dataset_id → list available dataset types
        if not dataset_id:
            return {
                "reason_code": "datasets_listed",
                "datasets": _AVAILABLE_DATASETS,
            }

        # "models" → list available model versions
        if dataset_id == "models":
            mv_repo = ModelVersionRepository(self._session)
            rows = await mv_repo.list_all()
            models = [
                {
                    "model_version_id": str(r.model_version_id),
                    "base_year": r.base_year,
                    "source": r.source,
                    "sector_count": r.sector_count,
                    "denomination": getattr(r, "model_denomination", "UNKNOWN"),
                }
                for r in rows
            ]
            return {"reason_code": "models_listed", "models": models}

        # All other datasets require model_version_id
        model_version_id_str = arguments.get("model_version_id")
        if not model_version_id_str:
            return {
                "reason_code": "invalid_args",
                "error": f"dataset_id='{dataset_id}' requires model_version_id",
            }

        try:
            mv_uuid = UUID(str(model_version_id_str))
        except (ValueError, AttributeError):
            return {
                "reason_code": "invalid_args",
                "error": f"Invalid model_version_id format: {model_version_id_str}",
            }

        # Load model data
        mv_repo = ModelVersionRepository(self._session)
        mv_row = await mv_repo.get(mv_uuid)
        if mv_row is None:
            return {
                "reason_code": "model_not_found",
                "error": f"Model version {model_version_id_str} not found",
            }

        md_repo = ModelDataRepository(self._session)
        md_row = await md_repo.get(mv_uuid)
        if md_row is None:
            return {
                "reason_code": "model_not_found",
                "error": f"Model data for {model_version_id_str} not found",
            }

        sector_codes: list[str] = md_row.sector_codes
        x_vector: list[float] = md_row.x_vector_json
        sector_filter = arguments.get("sector_codes")

        if dataset_id == "io_tables":
            # Build sector → output mapping
            output_map: dict[str, float] = {}
            for code, val in zip(sector_codes, x_vector):
                if sector_filter and code not in sector_filter:
                    continue
                output_map[code] = val

            filtered_codes = (
                [c for c in sector_codes if c in sector_filter]
                if sector_filter
                else sector_codes
            )

            return {
                "reason_code": "io_tables_found",
                "model_version_id": str(mv_uuid),
                "base_year": mv_row.base_year,
                "denomination": getattr(mv_row, "model_denomination", "UNKNOWN"),
                "sector_codes": filtered_codes,
                "total_output": output_map,
            }

        if dataset_id == "employment_coefficients":
            # P2-2: Query real employment coefficients from DB
            from src.repositories.workforce import EmploymentCoefficientsRepository

            ec_repo = EmploymentCoefficientsRepository(self._session)
            ec_rows = await ec_repo.get_by_model_version(mv_uuid)

            if not ec_rows:
                return {
                    "reason_code": "employment_coefficients_not_found",
                    "error": f"No employment coefficients found for model {model_version_id_str}",
                }

            # Use the latest version
            latest = ec_rows[0]  # already sorted newest-first by repository
            coefficients: list[dict] = latest.coefficients

            # Apply sector filter if provided
            if sector_filter:
                coefficients = [
                    c for c in coefficients
                    if c.get("sector_code") in sector_filter
                ]

            return {
                "reason_code": "employment_coefficients_found",
                "model_version_id": str(mv_uuid),
                "base_year": latest.base_year,
                "output_unit": latest.output_unit,
                "coefficients": coefficients,
            }

        # Fallback: unknown dataset_id → list available
        return {
            "reason_code": "datasets_listed",
            "datasets": _AVAILABLE_DATASETS,
        }

    async def _handle_build_scenario(self, arguments: dict) -> dict:
        """Create a ScenarioSpec via ScenarioVersionRepository.

        P4-2: Also auto-drafts compilation assumptions (import share, phasing,
        deflators) so NFF governance can track implicit parameters.

        Required args: name, base_year, base_model_version_id
        Optional: start_year, end_year (used for time_horizon)
        """
        from src.compiler.scenario_compiler import (
            CompilationInput,
            draft_compilation_assumptions,
        )
        from src.models.scenario import TimeHorizon
        from src.repositories.governance import AssumptionRepository
        from src.repositories.scenarios import ScenarioVersionRepository

        name = arguments.get("name")
        base_year = arguments.get("base_year")
        base_model_version_id = arguments.get("base_model_version_id")

        if not name or base_year is None or not base_model_version_id:
            return {
                "reason_code": "invalid_args",
                "error": "Missing required fields: name, base_year, base_model_version_id",
            }

        start_year = arguments.get("start_year", base_year)
        end_year = arguments.get("end_year", base_year)

        scenario_spec_id = new_uuid7()
        repo = ScenarioVersionRepository(self._session)
        row = await repo.create(
            scenario_spec_id=scenario_spec_id,
            version=1,
            name=name,
            workspace_id=self._workspace_id,
            base_model_version_id=UUID(str(base_model_version_id)),
            base_year=int(base_year),
            time_horizon={"start_year": int(start_year), "end_year": int(end_year)},
            shock_items=arguments.get("shock_items", []),
        )

        # P4-2: Auto-draft compilation assumptions
        try:
            compilation_inp = CompilationInput(
                workspace_id=self._workspace_id,
                scenario_name=name,
                base_model_version_id=UUID(str(base_model_version_id)),
                base_year=int(base_year),
                time_horizon=TimeHorizon(
                    start_year=int(start_year), end_year=int(end_year),
                ),
                line_items=[],
                decisions=[],
                default_domestic_share=0.65,
                default_import_share=0.35,
            )
            assumptions = draft_compilation_assumptions(compilation_inp)
            assumption_repo = AssumptionRepository(self._session)
            for assumption in assumptions:
                await assumption_repo.create(
                    assumption_id=assumption.assumption_id,
                    type=assumption.type.value,
                    value=assumption.value,
                    units=assumption.units,
                    justification=assumption.justification,
                    status=assumption.status.value,
                    workspace_id=self._workspace_id,
                )
            _logger.info(
                "P4-2: Auto-drafted %d assumptions for scenario %s",
                len(assumptions), scenario_spec_id,
            )
        except Exception:
            _logger.warning(
                "P4-2: Failed to auto-draft assumptions for scenario %s",
                scenario_spec_id,
                exc_info=True,
            )

        return {
            "scenario_spec_id": str(row.scenario_spec_id),
            "version": row.version,
            "name": row.name,
        }

    async def _handle_run_engine(self, arguments: dict) -> dict:
        """Execute engine run via RunExecutionService (Sprint 28).

        Resolves scenario -> model -> satellite coefficients -> BatchRunner.run().
        Persists RunSnapshot + ResultSet rows and returns real run_id.
        """
        from src.repositories.engine import (
            ModelDataRepository, ModelVersionRepository,
            ResultSetRepository, RunSnapshotRepository,
        )
        from src.repositories.governance import ClaimRepository
        from src.repositories.scenarios import ScenarioVersionRepository
        from src.services.run_execution import (
            RunExecutionService, RunFromScenarioInput, RunRepositories,
        )

        scenario_spec_id = arguments.get("scenario_spec_id")
        if not scenario_spec_id:
            return {
                "reason_code": "invalid_args",
                "error": "Missing required field: scenario_spec_id",
            }

        try:
            spec_uuid = UUID(str(scenario_spec_id))
        except (ValueError, AttributeError):
            return {
                "reason_code": "invalid_args",
                "error": f"Invalid scenario_spec_id format: {scenario_spec_id}",
            }

        version = arguments.get("scenario_spec_version")
        svc = RunExecutionService()
        repos = RunRepositories(
            scenario_repo=ScenarioVersionRepository(self._session),
            mv_repo=ModelVersionRepository(self._session),
            md_repo=ModelDataRepository(self._session),
            snap_repo=RunSnapshotRepository(self._session),
            rs_repo=ResultSetRepository(self._session),
            claim_repo=ClaimRepository(self._session),  # P4-1: auto-create claims
        )
        inp = RunFromScenarioInput(
            workspace_id=self._workspace_id,
            scenario_spec_id=spec_uuid,
            scenario_spec_version=int(version) if version is not None else None,
        )

        result = await svc.execute_from_scenario(inp, repos)

        if result.status == "FAILED":
            return {
                "reason_code": "run_failed",
                "error": result.error or "Unknown engine failure",
            }

        return {
            "status": "success",
            "reason_code": "run_completed",
            "run_id": str(result.run_id),
            "scenario_spec_id": str(result.scenario_spec_id),
            "scenario_spec_version": result.scenario_spec_version,
            "model_version_id": str(result.model_version_id),
            "result_summary": result.result_summary,
        }

    async def _handle_narrate_results(self, arguments: dict) -> dict:
        """Read ResultSet rows for a run and return structured result data.

        Workspace-scoped: verifies RunSnapshot belongs to current workspace
        before reading ResultSets.
        """
        from src.db.tables import RunSnapshotRow
        from src.repositories.engine import ResultSetRepository

        run_id = arguments.get("run_id")
        if not run_id:
            return {
                "reason_code": "invalid_args",
                "error": "Missing required field: run_id",
            }

        try:
            run_uuid = UUID(str(run_id))
        except (ValueError, AttributeError):
            return {
                "reason_code": "invalid_args",
                "error": f"Invalid run_id format: {run_id}",
            }

        # Verify run belongs to this workspace
        snap = await self._session.get(RunSnapshotRow, run_uuid)
        if snap is None or snap.workspace_id != self._workspace_id:
            return {
                "reason_code": "run_not_found",
                "error": f"Run {run_id} not found in workspace",
            }

        repo = ResultSetRepository(self._session)
        rows = await repo.get_by_run(run_uuid)

        if not rows:
            return {
                "reason_code": "no_results",
                "run_id": str(run_id),
                "result": {},
            }

        # Structure results: metric_type -> values dict
        result_data: dict[str, dict] = {}
        for row in rows:
            result_data[row.metric_type] = row.values

        return {
            "reason_code": "results_found",
            "run_id": str(run_id),
            "result": result_data,
        }

    async def _handle_create_export(self, arguments: dict) -> dict:
        """Execute a full export via ExportExecutionService (Sprint 28).

        Required args: run_id, mode, export_formats, pack_data
        Guards: RunSnapshot must exist for run_id AND belong to current
        workspace (prevents orphan exports and cross-workspace access).

        Delegates to ExportExecutionService.execute() for governance checks,
        artifact generation, watermarking, and checksum computation.
        """
        from src.services.export_execution import (
            ExportExecutionService, ExportExecutionInput, ExportRepositories,
        )
        from src.repositories.exports import ExportRepository
        from src.repositories.governance import AssumptionRepository, ClaimRepository
        from src.repositories.data_quality import DataQualityRepository
        from src.repositories.engine import RunSnapshotRepository, ModelVersionRepository
        from src.export.artifact_storage import ExportArtifactStorage
        from src.config.settings import get_settings

        run_id = arguments.get("run_id")
        mode = arguments.get("mode")
        export_formats = arguments.get("export_formats")
        pack_data = arguments.get("pack_data")

        if not run_id or not mode or not export_formats or pack_data is None:
            return {
                "reason_code": "invalid_args",
                "error": "Missing required fields: run_id, mode, export_formats, pack_data",
            }

        # Validate mode against ExportMode enum
        try:
            validated_mode = ExportMode(mode)
        except ValueError:
            return {
                "reason_code": "invalid_args",
                "error": f"Invalid mode: {mode}. Must be SANDBOX or GOVERNED.",
            }

        try:
            run_uuid = UUID(str(run_id))
        except (ValueError, AttributeError):
            return {
                "reason_code": "invalid_args",
                "error": f"Invalid run_id format: {run_id}",
            }

        # Guard: RunSnapshot must exist AND belong to this workspace
        # (prevents orphan exports from dry-run IDs and cross-workspace access)
        from src.db.tables import RunSnapshotRow

        snap = await self._session.get(RunSnapshotRow, run_uuid)
        if snap is None or snap.workspace_id != self._workspace_id:
            return {
                "reason_code": "run_not_found",
                "error": f"RunSnapshot {run_id} not found in workspace",
            }

        settings = get_settings()
        artifact_store = ExportArtifactStorage(storage_root=settings.OBJECT_STORAGE_PATH)

        repos = ExportRepositories(
            export_repo=ExportRepository(self._session),
            claim_repo=ClaimRepository(self._session),
            quality_repo=DataQualityRepository(self._session),
            snap_repo=RunSnapshotRepository(self._session),
            mv_repo=ModelVersionRepository(self._session),
            artifact_store=artifact_store,
            assumption_repo=AssumptionRepository(self._session),  # P4-3
        )
        svc = ExportExecutionService()
        inp = ExportExecutionInput(
            workspace_id=self._workspace_id,
            run_id=run_uuid,
            mode=validated_mode,
            export_formats=export_formats,
            pack_data=pack_data,
        )

        result = await svc.execute(inp, repos)

        if result.status == "FAILED":
            return {"reason_code": "export_failed", "error": result.error or "Export failed"}

        response: dict = {
            "export_id": str(result.export_id),
            "status": result.status,
        }
        if result.checksums:
            response["checksums"] = result.checksums
        if result.blocking_reasons:
            response["blocking_reasons"] = result.blocking_reasons

        # Signal BLOCKED to the executor so it maps to status="blocked"
        if result.status == "BLOCKED":
            response["reason_code"] = "export_blocked"

        return response

    async def _handle_run_depth_suite(self, arguments: dict) -> dict:
        """Launch Al-Muhāsibī depth engine for deep-dive analysis (P3-1).

        Creates a DepthPlan row and runs the full depth pipeline inline.
        Mocked in tests via patch("src.services.chat_tool_executor.run_depth_plan").

        Required args: key_questions (list[str])
        Optional: target_sectors (list[str]), base_year (int)
        """
        from src.repositories.depth import DepthPlanRepository

        key_questions = arguments.get("key_questions")
        if not key_questions or not isinstance(key_questions, list):
            return {
                "reason_code": "invalid_args",
                "error": "Missing required field: key_questions (must be a non-empty list)",
            }

        target_sectors = arguments.get("target_sectors", [])
        base_year = arguments.get("base_year")

        # Create a DepthPlan row
        plan_repo = DepthPlanRepository(self._session)
        plan_id = new_uuid7()
        await plan_repo.create(
            plan_id=plan_id,
            workspace_id=self._workspace_id,
            status="PENDING",
        )

        # Build context for the depth engine
        depth_context: dict = {
            "key_questions": key_questions,
            "target_sectors": target_sectors,
        }
        if base_year is not None:
            depth_context["base_year"] = base_year

        # Run the depth pipeline inline
        final_status = await run_depth_plan(
            plan_id=plan_id,
            workspace_id=self._workspace_id,
            context=depth_context,
            classification="INTERNAL",
        )

        return {
            "plan_id": str(plan_id),
            "status": final_status,
        }

    # ------------------------------------------------------------------
    # Execute single / execute all
    # ------------------------------------------------------------------

    async def execute(self, tool_call: ToolCall) -> ToolExecutionResult:
        """Execute a single tool call.

        Returns a ToolExecutionResult with status, latency, and result/error.
        Unknown tools return status='error' with reason_code='unknown_tool'.
        Exceptions are caught and returned as status='error'.
        """
        handler = self._get_handler(tool_call.tool_name)
        if handler is None:
            return ToolExecutionResult(
                tool_name=tool_call.tool_name,
                status="error",
                reason_code="unknown_tool",
                error_summary=f"Unknown tool: {tool_call.tool_name}",
            )

        # Reason codes that indicate handler-level validation failures
        _ERROR_REASON_CODES = frozenset({
            "invalid_args", "scenario_not_found", "no_results", "run_not_found",
            "run_failed", "export_failed", "model_not_found",
            "employment_coefficients_not_found",
        })
        # Reason codes that indicate a governance-blocked result (amber, not red)
        _BLOCKED_REASON_CODES = frozenset({
            "export_blocked",
        })

        start = time.monotonic()
        try:
            result = await handler(tool_call.arguments)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            # Detect handler-level validation errors
            reason_code = result.get("reason_code", "") if isinstance(result, dict) else ""
            if reason_code in _ERROR_REASON_CODES:
                return ToolExecutionResult(
                    tool_name=tool_call.tool_name,
                    status="error",
                    reason_code=reason_code,
                    latency_ms=elapsed_ms,
                    result=result,
                    error_summary=result.get("error", "")[:200] if result.get("error") else None,
                )

            # Detect governance-blocked results (BLOCKED → amber, not red)
            if reason_code in _BLOCKED_REASON_CODES:
                return ToolExecutionResult(
                    tool_name=tool_call.tool_name,
                    status="blocked",
                    reason_code=reason_code,
                    latency_ms=elapsed_ms,
                    result=result,
                )

            return ToolExecutionResult(
                tool_name=tool_call.tool_name,
                status="success",
                latency_ms=elapsed_ms,
                result=result,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            _logger.exception("Tool %s failed", tool_call.tool_name)
            return ToolExecutionResult(
                tool_name=tool_call.tool_name,
                status="error",
                reason_code="handler_exception",
                retryable=True,
                latency_ms=elapsed_ms,
                error_summary=str(exc)[:200],
            )

    # Per-turn cap reason codes (used to distinguish cap-blocked from
    # governance-blocked in execute_all counting).
    _CAP_REASON_CODES = frozenset({
        "max_tool_calls_exceeded",
        "max_run_engine_exceeded",
        "max_create_export_exceeded",
    })

    async def execute_all(
        self, tool_calls: list[ToolCall],
    ) -> list[ToolExecutionResult]:
        """Execute tool calls sequentially, enforcing safety caps.

        - Overall cap: MAX_TOOL_CALLS_PER_TURN
        - Per-tool caps: run_engine (1), create_export (1)
        - Excess calls are returned as status='blocked'
        """
        results: list[ToolExecutionResult] = []
        per_tool_counts: dict[str, int] = {}

        for tool_call in tool_calls:
            # Overall cap — only skip cap-blocked results (not governance-blocked)
            executed_count = sum(
                1 for r in results
                if r.reason_code not in self._CAP_REASON_CODES
            )
            if executed_count >= MAX_TOOL_CALLS_PER_TURN:
                results.append(ToolExecutionResult(
                    tool_name=tool_call.tool_name,
                    status="blocked",
                    reason_code="max_tool_calls_exceeded",
                ))
                continue

            # Per-tool cap
            tool_name = tool_call.tool_name
            cap = _PER_TOOL_CAPS.get(tool_name)
            if cap is not None:
                current = per_tool_counts.get(tool_name, 0)
                if current >= cap:
                    results.append(ToolExecutionResult(
                        tool_name=tool_name,
                        status="blocked",
                        reason_code=f"max_{tool_name}_exceeded",
                    ))
                    continue

            # Execute
            result = await self.execute(tool_call)
            results.append(result)

            # Track per-tool count — governance-blocked still counts as "executed"
            # Only per-turn cap blocks should be excluded from the count
            if result.reason_code not in self._CAP_REASON_CODES:
                per_tool_counts[tool_name] = per_tool_counts.get(tool_name, 0) + 1

        return results
