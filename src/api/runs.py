"""FastAPI engine/run endpoints — MVP-3 Sections 6.2.9, 6.2.10.

POST /v1/engine/models                                       — register (global)
POST /v1/workspaces/{workspace_id}/engine/runs               — single run
GET  /v1/workspaces/{workspace_id}/engine/runs/{run_id}      — get results
POST /v1/workspaces/{workspace_id}/engine/batch              — batch runs
GET  /v1/workspaces/{workspace_id}/engine/batch/{batch_id}   — batch status

S0-4: Workspace-scoped runs/batch. Model registration stays global.
Batch status tracking (PENDING → RUNNING → COMPLETED/FAILED).

S0-1: DB-fallback on ModelStore cache miss (restart survival).
       Checksum verification on rehydrate (Amendment 1).
       Concurrency guard with asyncio.Lock (Amendment 2).
       Workspace scoping in read paths (Amendment 3).

Deterministic only — no LLM calls.
ModelStore kept as in-memory LRU cache for synchronous engine access.
DB repos persist model metadata, run snapshots, result sets, batches.
"""

import asyncio
import logging
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth_deps import (
    AuthPrincipal,
    WorkspaceMember,
    require_global_role,
    require_workspace_member,
)
from src.api.dependencies import (
    get_batch_repo,
    get_constraint_set_repo,
    get_depth_artifact_repo,
    get_depth_plan_repo,
    get_model_data_repo,
    get_model_version_repo,
    get_result_set_repo,
    get_run_snapshot_repo,
    get_scenario_version_repo,
    get_workforce_result_repo,
)
from src.config.settings import get_settings
from src.data.io_loader import (
    ModelArtifactValidationError,
    validate_extended_model_artifacts,
)
from src.engine.batch import (
    BatchRequest,
    BatchRunner,
    ScenarioInput,
    SingleRunResult,
)
from src.engine.feasibility import constraints_to_specs
from src.engine.model_store import LoadedModel, ModelStore, compute_model_checksum
from src.engine.runseries_delta import RunSeriesValidationError
from src.data.workforce.satellite_coeff_loader import load_satellite_coefficients
from src.engine.satellites import SatelliteCoefficients
from src.engine.type_ii_validation import TypeIIValidationError
from src.engine.value_measures_validation import ValueMeasuresValidationError
from src.models.common import new_uuid7
from src.models.feasibility import Constraint
from src.models.model_version import ModelVersion
from src.repositories.engine import (
    BatchRepository,
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.depth import DepthArtifactRepository, DepthPlanRepository
from src.repositories.feasibility import ConstraintSetRepository
from src.repositories.scenarios import ScenarioVersionRepository
from src.repositories.workforce import WorkforceResultRepository

_logger = logging.getLogger(__name__)

# Global model registration router (not workspace-scoped)
models_router = APIRouter(prefix="/v1/engine", tags=["engine"])

# Workspace-scoped engine router for runs/batch
router = APIRouter(prefix="/v1/workspaces", tags=["engine"])

# ---------------------------------------------------------------------------
# In-memory LRU cache for synchronous engine access (BatchRunner needs .get())
# On cache miss, _ensure_model_loaded() rehydrates from DB (S0-1).
# ---------------------------------------------------------------------------

_model_store = ModelStore()

# Per-model locks for concurrent DB-fallback (Amendment 2)
_model_locks: dict[UUID, asyncio.Lock] = {}
_global_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class RegisterModelRequest(BaseModel):
    Z: list[list[float]]
    x: list[float]
    sector_codes: list[str]
    base_year: int
    source: str
    final_demand_f: list[list[float]] | None = Field(
        default=None,
        alias="final_demand_F",
    )
    imports_vector: list[float] | None = None
    compensation_of_employees: list[float] | None = None
    gross_operating_surplus: list[float] | None = None
    taxes_less_subsidies: list[float] | None = None
    household_consumption_shares: list[float] | None = None
    deflator_series: dict[str, float] | None = None


class RegisterModelResponse(BaseModel):
    model_version_id: str
    sector_count: int
    checksum: str


class SatelliteCoeffsPayload(BaseModel):
    jobs_coeff: list[float]
    import_ratio: list[float]
    va_ratio: list[float]


class RunRequest(BaseModel):
    model_version_id: str
    annual_shocks: dict[str, list[float]]
    base_year: int
    satellite_coefficients: SatelliteCoeffsPayload | None = None  # P5-2: optional, auto-loaded from curated data when None
    deflators: dict[str, float] | None = None
    baseline_run_id: str | None = None  # Sprint 17


class ScenarioPayload(BaseModel):
    name: str
    annual_shocks: dict[str, list[float]]
    base_year: int
    deflators: dict[str, float] | None = None
    sensitivity_multipliers: list[float] | None = None
    baseline_run_id: str | None = None  # Sprint 17


class BatchRunRequest(BaseModel):
    model_version_id: str
    scenarios: list[ScenarioPayload]
    satellite_coefficients: SatelliteCoeffsPayload | None = None  # P5-2: optional, auto-loaded when None


# Confidence class derivation by metric_type (no DB schema change)
_ESTIMATED_METRICS = frozenset({
    "gdp_market_price", "gdp_real", "gdp_intensity",
    "balance_of_trade", "non_oil_exports",
    "government_non_oil_revenue", "government_revenue_spending_ratio",
})


class ResultSetResponse(BaseModel):
    result_id: str
    metric_type: str
    values: dict[str, float]
    confidence_class: str = "COMPUTED"
    sector_breakdowns: dict[str, dict[str, float]] | None = None  # P6-4
    # Sprint 17: RunSeries fields
    year: int | None = None
    series_kind: str | None = None
    baseline_run_id: str | None = None


class SnapshotResponse(BaseModel):
    run_id: str
    model_version_id: str
    model_denomination: str = "SAR_MILLIONS"  # P6-3: from ModelVersion metadata


class WorkforceSectorResponse(BaseModel):
    sector_code: str
    total_jobs: float
    saudi_ready_jobs: float = 0.0
    saudi_trainable_jobs: float = 0.0
    expat_reliant_jobs: float = 0.0


class WorkforceResponse(BaseModel):
    total_jobs: float
    total_saudi_ready: float = 0.0
    total_saudi_trainable: float = 0.0
    total_expat_reliant: float = 0.0
    has_saudization_split: bool = False
    per_sector: list[WorkforceSectorResponse] = Field(default_factory=list)


class SuiteRunResponse(BaseModel):
    scenario_spec_id: str
    scenario_spec_version: int = 1
    run_id: str
    direction_id: str
    name: str
    mode: str = "SANDBOX"
    is_contrarian: bool = False
    multiplier: float = 1.0
    headline_output: float | None = None
    employment: float | None = None
    muhasaba_status: str = "SURVIVED"
    sensitivities: list[str | dict] = Field(default_factory=list)


class QualitativeRiskResponse(BaseModel):
    risk_id: str | None = None
    label: str
    description: str
    disclosure_tier: str | None = None
    not_modeled: bool = True
    affected_sectors: list[str] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(default_factory=list)
    expected_direction: str | None = None


class DepthTraceStepResponse(BaseModel):
    step: int
    step_name: str
    provider: str | None = None
    model: str | None = None
    generation_mode: str | None = None
    duration_ms: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    details: dict = Field(default_factory=dict)


class DepthEngineResponse(BaseModel):
    plan_id: str
    suite_id: str | None = None
    batch_id: str | None = None
    suite_rationale: str | None = None
    run_ids: list[str] = Field(default_factory=list)
    suite_runs: list[SuiteRunResponse] = Field(default_factory=list)
    sensitivity_runs: list[SuiteRunResponse] = Field(default_factory=list)
    qualitative_risks: list[QualitativeRiskResponse] = Field(default_factory=list)
    trace_steps: list[DepthTraceStepResponse] = Field(default_factory=list)


class RunResponse(BaseModel):
    run_id: str
    result_sets: list[ResultSetResponse]
    snapshot: SnapshotResponse
    workforce: WorkforceResponse | None = None
    depth_engine: DepthEngineResponse | None = None


class RunSummary(BaseModel):
    run_id: str
    model_version_id: str
    created_at: str


class ListRunsResponse(BaseModel):
    runs: list[RunSummary]


class BatchResponse(BaseModel):
    batch_id: str
    status: str = "COMPLETED"
    results: list[RunResponse]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ensure_model_loaded(
    model_version_id: UUID,
    mv_repo: ModelVersionRepository,
    md_repo: ModelDataRepository,
) -> LoadedModel:
    """Load model from cache, falling back to DB on miss (S0-1).

    Amendment 1: Checksum verification on DB rehydrate.
    Amendment 2: Per-model asyncio.Lock with double-checked locking.
    Amendment 4: Uses cache_prevalidated() to store in ModelStore.
    """
    # Fast path: cache hit (no lock needed)
    try:
        return _model_store.get(model_version_id)
    except KeyError:
        pass

    # Cache miss — acquire per-model lock to prevent thundering herd
    async with _global_lock:
        if model_version_id not in _model_locks:
            _model_locks[model_version_id] = asyncio.Lock()
        lock = _model_locks[model_version_id]

    async with lock:
        # Double-check after acquiring lock (another coroutine may have loaded it)
        try:
            return _model_store.get(model_version_id)
        except KeyError:
            pass

        # Load from DB
        _logger.info("Cache miss for model %s — loading from DB", model_version_id)
        mv_row = await mv_repo.get(model_version_id)
        if mv_row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_version_id} not found.",
            )
        md_row = await md_repo.get(model_version_id)
        if md_row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Model data for {model_version_id} not found.",
            )

        # Reconstruct arrays
        z_matrix = np.array(md_row.z_matrix_json, dtype=np.float64)
        x_vector = np.array(md_row.x_vector_json, dtype=np.float64)

        # Amendment 1: checksum verification includes optional model artifacts.
        artifact_payload = {
            "final_demand_F": md_row.final_demand_f_json,
            "imports_vector": md_row.imports_vector_json,
            "compensation_of_employees": md_row.compensation_of_employees_json,
            "gross_operating_surplus": md_row.gross_operating_surplus_json,
            "taxes_less_subsidies": md_row.taxes_less_subsidies_json,
            "household_consumption_shares": md_row.household_consumption_shares_json,
            "deflator_series": md_row.deflator_series_json,
        }
        recomputed = compute_model_checksum(z_matrix, x_vector, artifact_payload)
        if recomputed != mv_row.checksum:
            _logger.error(
                "Checksum mismatch for model %s: stored=%s recomputed=%s",
                model_version_id,
                mv_row.checksum,
                recomputed,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Data integrity error for model {model_version_id}.",
            )

        # Rehydrate extended artifacts so LoadedModel has Type II prerequisites
        artifact_kwargs: dict[str, object] = {}
        for key in ("compensation_of_employees", "gross_operating_surplus",
                    "taxes_less_subsidies", "household_consumption_shares",
                    "imports_vector", "deflator_series"):
            json_key = f"{key}_json"
            val = getattr(md_row, json_key, None)
            if val is not None:
                artifact_kwargs[key] = val
        fd_val = getattr(md_row, "final_demand_f_json", None)
        if fd_val is not None:
            artifact_kwargs["final_demand_F"] = fd_val

        mv = ModelVersion(
            model_version_id=mv_row.model_version_id,
            base_year=mv_row.base_year,
            source=mv_row.source,
            sector_count=mv_row.sector_count,
            checksum=mv_row.checksum,
            model_denomination=getattr(
                mv_row, "model_denomination", "UNKNOWN",
            ),
            **artifact_kwargs,
        )
        loaded = LoadedModel(
            model_version=mv,
            Z=z_matrix,
            x=x_vector,
            sector_codes=list(md_row.sector_codes),
        )
        _model_store.cache_prevalidated(loaded)
        _logger.info("Rehydrated model %s from DB into cache", model_version_id)
        return loaded


ALLOWED_RUNTIME_PROVENANCE = frozenset({"curated_real"})


async def _enforce_model_provenance(
    model_version_id: UUID,
    mv_repo: ModelVersionRepository,
) -> None:
    """Reject models with non-curated_real provenance at runtime.

    D-5.1: Only curated_real models are permitted in runtime API flows.
    synthetic, unknown, and curated_estimated are all blocked.
    """
    mv_row = await mv_repo.get(model_version_id)
    if mv_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model {model_version_id} not found.",
        )
    prov = getattr(mv_row, "provenance_class", "unknown")
    if prov not in ALLOWED_RUNTIME_PROVENANCE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Model {model_version_id} has provenance_class='{prov}'. "
                f"Runtime execution requires provenance_class "
                f"in {sorted(ALLOWED_RUNTIME_PROVENANCE)}."
            ),
        )


def _make_satellite_coefficients(payload: SatelliteCoeffsPayload) -> SatelliteCoefficients:
    return SatelliteCoefficients(
        jobs_coeff=np.array(payload.jobs_coeff),
        import_ratio=np.array(payload.import_ratio),
        va_ratio=np.array(payload.va_ratio),
        version_id=new_uuid7(),
    )


def _make_version_refs() -> dict[str, UUID]:
    """Generate placeholder version refs for MVP."""
    return {
        "taxonomy_version_id": new_uuid7(),
        "concordance_version_id": new_uuid7(),
        "mapping_library_version_id": new_uuid7(),
        "assumption_library_version_id": new_uuid7(),
        "prompt_pack_version_id": new_uuid7(),
    }


def _annual_shocks_to_numpy(shocks: dict[str, list[float]]) -> dict[int, np.ndarray]:
    return {int(year): np.array(values) for year, values in shocks.items()}


def _deflators_to_dict(deflators: dict[str, float] | None) -> dict[int, float] | None:
    if deflators is None:
        return None
    return {int(year): val for year, val in deflators.items()}


def _sum_metric(values: dict[str, float] | None) -> float | None:
    if not values:
        return None
    return float(sum(float(v) for v in values.values()))


async def _load_workforce_response(
    run_id: UUID,
    workforce_result_repo: WorkforceResultRepository | None,
) -> WorkforceResponse | None:
    if workforce_result_repo is None:
        return None
    rows = await workforce_result_repo.get_by_run(run_id)
    if not rows:
        return None
    latest = rows[0]
    payload = latest.results or {}
    per_sector = [
        WorkforceSectorResponse(**entry)
        for entry in payload.get("per_sector", [])
    ]
    totals = payload.get("totals", {})
    return WorkforceResponse(
        total_jobs=float(totals.get("total_jobs", 0.0)),
        total_saudi_ready=float(totals.get("total_saudi_ready", 0.0)),
        total_saudi_trainable=float(totals.get("total_saudi_trainable", 0.0)),
        total_expat_reliant=float(totals.get("total_expat_reliant", 0.0)),
        has_saudization_split=bool(payload.get("has_saudization_split", False)),
        per_sector=per_sector,
    )


def _artifact_details(step: str, payload: dict) -> dict:
    if step == "KHAWATIR":
        candidates = payload.get("candidates", [])
        labels: dict[str, int] = {}
        for candidate in candidates:
            label = candidate.get("source_type", "unknown")
            labels[label] = labels.get(label, 0) + 1
        return {"candidate_count": len(candidates), "label_counts": labels}
    if step == "MURAQABA":
        entries = payload.get("bias_register", {}).get("entries", [])
        return {
            "bias_count": len(entries),
            "bias_types": [entry.get("bias_type") for entry in entries if entry.get("bias_type")],
        }
    if step == "MUJAHADA":
        contrarians = payload.get("contrarians", [])
        return {
            "contrarian_count": len(contrarians),
            "broken_assumptions": [
                entry.get("broken_assumption") for entry in contrarians if entry.get("broken_assumption")
            ],
        }
    if step == "MUHASABA":
        scored = payload.get("scored", [])
        return {
            "accepted": sum(1 for entry in scored if entry.get("accepted", True)),
            "rejected": sum(1 for entry in scored if not entry.get("accepted", True)),
            "polarity_warning": payload.get("polarity_warning"),
        }
    if step == "SUITE_PLANNING":
        suite = payload.get("suite_plan", payload)
        return {
            "scenario_count": len(suite.get("runs", [])),
            "sensitivity_axes": [
                run.get("sensitivities", []) for run in suite.get("runs", [])
            ],
        }
    if step == "SUITE_EXECUTION":
        return {
            "completed": payload.get("completed", 0),
            "failed": payload.get("failed", 0),
        }
    return {}


async def _load_depth_engine_response(
    snap_row,
    scenario_repo: ScenarioVersionRepository | None,
    depth_plan_repo: DepthPlanRepository | None,
    depth_artifact_repo: DepthArtifactRepository | None,
) -> DepthEngineResponse | None:
    if (
        scenario_repo is None
        or depth_plan_repo is None
        or depth_artifact_repo is None
        or getattr(snap_row, "scenario_spec_id", None) is None
    ):
        return None

    scenario_row = await scenario_repo.get_by_id_and_version(
        snap_row.scenario_spec_id,
        getattr(snap_row, "scenario_spec_version", None) or 1,
    )
    if scenario_row is None:
        return None
    dqs = scenario_row.data_quality_summary or {}
    plan_id_str = dqs.get("depth_plan_id")
    if not plan_id_str:
        return None

    plan_id = UUID(str(plan_id_str))
    plan_row = await depth_plan_repo.get(plan_id)
    artifact_rows = await depth_artifact_repo.get_by_plan(plan_id)
    if plan_row is None or not artifact_rows:
        return None

    suite_exec_artifact = next((row for row in artifact_rows if row.step == "SUITE_EXECUTION"), None)
    suite_planning_artifact = next((row for row in artifact_rows if row.step == "SUITE_PLANNING"), None)

    suite_payload = suite_exec_artifact.payload if suite_exec_artifact is not None else {}
    planning_payload = (
        suite_planning_artifact.payload.get("suite_plan", suite_planning_artifact.payload)
        if suite_planning_artifact is not None
        else {}
    )
    qualitative_risks = suite_payload.get("qualitative_risks", planning_payload.get("qualitative_risks", []))

    trace_steps: list[DepthTraceStepResponse] = []
    step_order = ["KHAWATIR", "MURAQABA", "MUJAHADA", "MUHASABA", "SUITE_PLANNING", "SUITE_EXECUTION"]
    metadata_by_step = {
        str(meta.get("step_name")): meta for meta in (getattr(plan_row, "step_metadata", None) or [])
    }
    for idx, step_name in enumerate(step_order, start=1):
        artifact = next((row for row in artifact_rows if row.step == step_name), None)
        if artifact is None:
            continue
        meta = metadata_by_step.get(step_name, {})
        trace_steps.append(DepthTraceStepResponse(
            step=idx,
            step_name=step_name,
            provider=meta.get("provider"),
            model=meta.get("model"),
            generation_mode=meta.get("generation_mode"),
            duration_ms=meta.get("duration_ms"),
            input_tokens=int(meta.get("input_tokens", 0) or 0),
            output_tokens=int(meta.get("output_tokens", 0) or 0),
            details=_artifact_details(step_name, artifact.payload),
        ))

    return DepthEngineResponse(
        plan_id=str(plan_id),
        suite_id=suite_payload.get("suite_id") or planning_payload.get("suite_id"),
        batch_id=suite_payload.get("batch_id"),
        suite_rationale=suite_payload.get("suite_rationale") or planning_payload.get("rationale"),
        run_ids=list(suite_payload.get("run_ids", [])),
        suite_runs=[SuiteRunResponse(**row) for row in suite_payload.get("suite_runs", [])],
        sensitivity_runs=[SuiteRunResponse(**row) for row in suite_payload.get("sensitivity_runs", [])],
        qualitative_risks=[QualitativeRiskResponse(**row) for row in qualitative_risks],
        trace_steps=trace_steps,
    )


async def _resolve_constraint_specs(
    workspace_id: UUID,
    model_version_id: UUID,
    sector_codes: list[str],
    constraint_repo: ConstraintSetRepository | None,
) -> tuple[list, UUID | None]:
    if constraint_repo is None:
        return [], None
    rows = await constraint_repo.get_by_workspace(workspace_id)
    row = next((entry for entry in rows if entry.model_version_id == model_version_id), None)
    if row is None:
        return [], None
    constraints = [
        Constraint.model_validate(item)
        for item in (row.constraints or [])
    ]
    return constraints_to_specs(constraints, sector_codes), row.constraint_set_id


def _serialize_extended_artifacts(validated: dict[str, object]) -> dict[str, object]:
    """Convert validated artifact payload to JSON-serializable values."""
    out: dict[str, object] = {}
    for key, value in validated.items():
        if isinstance(value, np.ndarray):
            out[key] = value.tolist()
        elif key == "deflator_series" and isinstance(value, dict):
            out[key] = {str(k): float(v) for k, v in value.items()}
        else:
            out[key] = value
    return out


def _register_model_error_detail(exc: Exception) -> dict[str, str]:
    """Convert validation exceptions to stable API detail payload."""
    if isinstance(exc, ModelArtifactValidationError):
        return {
            "reason_code": exc.reason_code,
            "message": exc.message,
        }
    return {
        "reason_code": "MODEL_VALIDATION_ERROR",
        "message": str(exc),
    }


def _single_run_to_response(
    sr: SingleRunResult,
    *,
    include_series: bool = False,
    model_denomination: str = "SAR_MILLIONS",
    workforce: WorkforceResponse | None = None,
    depth_engine: DepthEngineResponse | None = None,
) -> RunResponse:
    rows = sr.result_sets
    if not include_series:
        rows = [r for r in rows if r.series_kind is None]
    return RunResponse(
        run_id=str(sr.snapshot.run_id),
        result_sets=[
            ResultSetResponse(
                result_id=str(rs.result_id),
                metric_type=rs.metric_type,
                values=rs.values,
                confidence_class=(
                    "ESTIMATED" if (
                        rs.metric_type in _ESTIMATED_METRICS
                        or rs.series_kind == "delta"
                    ) else "COMPUTED"
                ),
                sector_breakdowns=rs.sector_breakdowns or None,  # P6-4
                year=rs.year,
                series_kind=rs.series_kind,
                baseline_run_id=str(rs.baseline_run_id) if rs.baseline_run_id else None,
            )
            for rs in rows
        ],
        snapshot=SnapshotResponse(
            run_id=str(sr.snapshot.run_id),
            model_version_id=str(sr.snapshot.model_version_id),
            model_denomination=model_denomination,
        ),
        workforce=workforce,
        depth_engine=depth_engine,
    )


async def _persist_run_result(
    sr: SingleRunResult,
    snap_repo: RunSnapshotRepository,
    rs_repo: ResultSetRepository,
    workspace_id: UUID | None = None,
    scenario_spec_id: UUID | None = None,
    scenario_spec_version: int | None = None,
    model_denomination: str = "UNKNOWN",
    constraint_set_version_id: UUID | None = None,
) -> None:
    """Persist a SingleRunResult to DB (snapshot + result sets).

    P6-3: model_denomination is persisted on the RunSnapshot row so that
    GET endpoints can return it without re-querying the ModelVersion.
    """
    snap = sr.snapshot
    await snap_repo.create(
        run_id=snap.run_id,
        model_version_id=snap.model_version_id,
        taxonomy_version_id=snap.taxonomy_version_id,
        concordance_version_id=snap.concordance_version_id,
        mapping_library_version_id=snap.mapping_library_version_id,
        assumption_library_version_id=snap.assumption_library_version_id,
        prompt_pack_version_id=snap.prompt_pack_version_id,
        constraint_set_version_id=constraint_set_version_id,
        workspace_id=workspace_id,
        scenario_spec_id=scenario_spec_id,
        scenario_spec_version=scenario_spec_version,
        model_denomination=model_denomination,
    )
    for rs in sr.result_sets:
        await rs_repo.create(
            result_id=rs.result_id,
            run_id=rs.run_id,
            metric_type=rs.metric_type,
            values=rs.values,
            sector_breakdowns=rs.sector_breakdowns,
            workspace_id=workspace_id,
            year=rs.year,
            series_kind=rs.series_kind,
            baseline_run_id=rs.baseline_run_id,
        )


async def _load_run_response(
    run_id: UUID,
    snap_repo: RunSnapshotRepository,
    rs_repo: ResultSetRepository,
    workforce_result_repo: WorkforceResultRepository | None = None,
    scenario_repo: ScenarioVersionRepository | None = None,
    depth_plan_repo: DepthPlanRepository | None = None,
    depth_artifact_repo: DepthArtifactRepository | None = None,
    workspace_id: UUID | None = None,
    include_series: bool = False,
) -> RunResponse | None:
    """Load a RunResponse from DB.

    Amendment 3: If workspace_id is provided, verifies the snapshot belongs
    to that workspace (returns None if mismatched).
    Sprint 17: include_series=False filters out series rows for backward compat.
    """
    snap_row = await snap_repo.get(run_id)
    if snap_row is None:
        return None
    # Amendment 3: workspace scoping enforcement
    if workspace_id is not None and hasattr(snap_row, "workspace_id"):
        if snap_row.workspace_id is not None and snap_row.workspace_id != workspace_id:
            return None
    rs_rows = await rs_repo.get_by_run(run_id)
    if not include_series:
        rs_rows = [r for r in rs_rows if r.series_kind is None]
    workforce = await _load_workforce_response(run_id, workforce_result_repo)
    depth_engine = await _load_depth_engine_response(
        snap_row,
        scenario_repo,
        depth_plan_repo,
        depth_artifact_repo,
    )
    return RunResponse(
        run_id=str(snap_row.run_id),
        result_sets=[
            ResultSetResponse(
                result_id=str(r.result_id),
                metric_type=r.metric_type,
                values=r.values,
                confidence_class=(
                    "ESTIMATED" if (
                        r.metric_type in _ESTIMATED_METRICS
                        or getattr(r, "series_kind", None) == "delta"
                    ) else "COMPUTED"
                ),
                sector_breakdowns=getattr(r, "sector_breakdowns", None) or None,  # P6-4
                year=getattr(r, "year", None),
                series_kind=getattr(r, "series_kind", None),
                baseline_run_id=(
                    str(r.baseline_run_id) if getattr(r, "baseline_run_id", None) else None
                ),
            )
            for r in rs_rows
        ],
        snapshot=SnapshotResponse(
            run_id=str(snap_row.run_id),
            model_version_id=str(snap_row.model_version_id),
            model_denomination=getattr(
                snap_row, "model_denomination", "SAR_MILLIONS",
            ),
        ),
        workforce=workforce,
        depth_engine=depth_engine,
    )


# ---------------------------------------------------------------------------
# Global Endpoints (model registration — not workspace-scoped)
# ---------------------------------------------------------------------------


@models_router.post("/models", status_code=201, response_model=RegisterModelResponse)
async def register_model(
    body: RegisterModelRequest,
    principal: AuthPrincipal = Depends(require_global_role("admin")),
    mv_repo: ModelVersionRepository = Depends(get_model_version_repo),
    md_repo: ModelDataRepository = Depends(get_model_data_repo),
) -> RegisterModelResponse:
    """Register an I-O model (Z, x, sector codes). Admin only."""
    try:
        validated_artifacts = validate_extended_model_artifacts(
            n=len(body.x),
            final_demand_F=body.final_demand_f,
            imports_vector=body.imports_vector,
            compensation_of_employees=body.compensation_of_employees,
            gross_operating_surplus=body.gross_operating_surplus,
            taxes_less_subsidies=body.taxes_less_subsidies,
            household_consumption_shares=body.household_consumption_shares,
            deflator_series=body.deflator_series,
        )
        serialized_artifacts = _serialize_extended_artifacts(validated_artifacts)
        mv = _model_store.register(
            Z=np.array(body.Z),
            x=np.array(body.x),
            sector_codes=body.sector_codes,
            base_year=body.base_year,
            source=body.source,
            artifact_payload=serialized_artifacts,
        )
    except (ModelArtifactValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=_register_model_error_detail(exc),
        ) from exc

    await mv_repo.create(
        model_version_id=mv.model_version_id,
        base_year=mv.base_year,
        source=mv.source,
        sector_count=mv.sector_count,
        checksum=mv.checksum,
    )
    await md_repo.create(
        model_version_id=mv.model_version_id,
        z_matrix_json=[row.tolist() for row in np.array(body.Z)],
        x_vector_json=list(body.x),
        sector_codes=body.sector_codes,
        final_demand_f_json=serialized_artifacts.get("final_demand_F"),
        imports_vector_json=serialized_artifacts.get("imports_vector"),
        compensation_of_employees_json=serialized_artifacts.get("compensation_of_employees"),
        gross_operating_surplus_json=serialized_artifacts.get("gross_operating_surplus"),
        taxes_less_subsidies_json=serialized_artifacts.get("taxes_less_subsidies"),
        household_consumption_shares_json=serialized_artifacts.get("household_consumption_shares"),
        deflator_series_json=serialized_artifacts.get("deflator_series"),
    )

    return RegisterModelResponse(
        model_version_id=str(mv.model_version_id),
        sector_count=mv.sector_count,
        checksum=mv.checksum,
    )


# ---------------------------------------------------------------------------
# Workspace-scoped Endpoints (runs / batch)
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/engine/runs", response_model=RunResponse)
async def create_run(
    workspace_id: UUID,
    body: RunRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
    mv_repo: ModelVersionRepository = Depends(get_model_version_repo),
    md_repo: ModelDataRepository = Depends(get_model_data_repo),
    constraint_repo: ConstraintSetRepository = Depends(get_constraint_set_repo),
    workforce_result_repo: WorkforceResultRepository = Depends(get_workforce_result_repo),
) -> RunResponse:
    """Execute a single scenario run."""
    model_version_id = UUID(body.model_version_id)
    await _enforce_model_provenance(model_version_id, mv_repo)
    loaded = await _ensure_model_loaded(model_version_id, mv_repo, md_repo)

    # P5-2: Auto-load curated satellite coefficients when not provided
    if body.satellite_coefficients is not None:
        coeffs = _make_satellite_coefficients(body.satellite_coefficients)
        employment_coeff_year = body.base_year
    else:
        loaded_coeffs = load_satellite_coefficients(
            year=body.base_year,
            sector_codes=loaded.sector_codes,
        )
        coeffs = loaded_coeffs.coefficients
        employment_coeff_year = getattr(
            loaded_coeffs.provenance, "employment_coeff_year", body.base_year,
        )
        _logger.info(
            "P5-2: Auto-loaded curated satellite coefficients for year %d",
            body.base_year,
        )
    constraint_specs, constraint_set_version_id = await _resolve_constraint_specs(
        workspace_id,
        model_version_id,
        loaded.sector_codes,
        constraint_repo,
    )

    # Sprint 17: baseline handling
    baseline_run_id: UUID | None = None
    baseline_annual_data: dict[int, dict[str, dict[str, float]]] | None = None
    if body.baseline_run_id is not None:
        baseline_run_id = UUID(body.baseline_run_id)
        baseline_annual_rows = await rs_repo.get_by_run_series(
            baseline_run_id, series_kind="annual",
        )
        if not baseline_annual_rows:
            # Check if the baseline run exists at all
            baseline_snap = await snap_repo.get(baseline_run_id)
            if baseline_snap is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "reason_code": "RS_BASELINE_NOT_FOUND",
                        "message": f"Baseline run {baseline_run_id} not found.",
                    },
                )
            # Run exists but has no annual series
            from src.engine.runseries_delta import validate_baseline_has_series
            try:
                validate_baseline_has_series(baseline_annual_rows)
            except RunSeriesValidationError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "reason_code": exc.reason_code,
                        "message": str(exc),
                    },
                ) from exc
        else:
            baseline_annual_data = {}
            for row in baseline_annual_rows:
                yr = row.year
                mt = row.metric_type
                baseline_annual_data.setdefault(yr, {})[mt] = dict(row.values)

    scenario = ScenarioInput(
        scenario_spec_id=new_uuid7(),
        scenario_spec_version=1,
        name="single_run",
        annual_shocks=_annual_shocks_to_numpy(body.annual_shocks),
        base_year=body.base_year,
        deflators=_deflators_to_dict(body.deflators),
        baseline_run_id=baseline_run_id,
        baseline_annual_data=baseline_annual_data,
    )

    settings = get_settings()
    runner = BatchRunner(model_store=_model_store, environment=settings.ENVIRONMENT.value)
    request = BatchRequest(
        scenarios=[scenario],
        model_version_id=model_version_id,
        satellite_coefficients=coeffs,
        version_refs=_make_version_refs(),
        constraints=constraint_specs,
    )

    try:
        result = runner.run(request)
    except TypeIIValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": str(exc),
            },
        ) from exc
    except ValueMeasuresValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": str(exc),
                "environment": exc.environment,
                "measure": exc.measure,
            },
        ) from exc
    except RunSeriesValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": str(exc),
            },
        ) from exc
    sr = result.run_results[0]

    # P6-3: Get model denomination for persistence + response
    model_denom = getattr(loaded.model_version, "model_denomination", "SAR_MILLIONS")

    # Persist to DB (with workspace scoping — Amendment 3)
    await _persist_run_result(
        sr, snap_repo, rs_repo,
        workspace_id=workspace_id,
        model_denomination=model_denom,
        constraint_set_version_id=constraint_set_version_id,
    )
    from src.services.run_execution import RunExecutionService

    await RunExecutionService()._persist_workforce_result(
        sr=sr,
        repo=workforce_result_repo,
        workspace_id=workspace_id,
        coefficients=coeffs,
        employment_coeff_year=employment_coeff_year,
    )
    workforce = await _load_workforce_response(sr.snapshot.run_id, workforce_result_repo)

    return _single_run_to_response(
        sr,
        model_denomination=model_denom,
        workforce=workforce,
    )


@router.get("/{workspace_id}/engine/runs", response_model=ListRunsResponse)
async def list_runs(
    workspace_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
) -> ListRunsResponse:
    """List run snapshots for a workspace (newest first, paginated)."""
    rows = await snap_repo.list_for_workspace(
        workspace_id, limit=limit, offset=offset,
    )
    return ListRunsResponse(
        runs=[
            RunSummary(
                run_id=str(row.run_id),
                model_version_id=str(row.model_version_id),
                created_at=row.created_at.isoformat(),
            )
            for row in rows
        ],
    )


@router.get("/{workspace_id}/engine/runs/{run_id}", response_model=RunResponse)
async def get_run_results(
    workspace_id: UUID,
    run_id: UUID,
    include_series: bool = Query(default=False),
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
    workforce_result_repo: WorkforceResultRepository = Depends(get_workforce_result_repo),
    scenario_repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
    depth_plan_repo: DepthPlanRepository = Depends(get_depth_plan_repo),
    depth_artifact_repo: DepthArtifactRepository = Depends(get_depth_artifact_repo),
) -> RunResponse:
    """Get results for a completed run (workspace-scoped — Amendment 3).

    Sprint 17: include_series=true returns annual/peak/delta rows.
    """
    resp = await _load_run_response(
        run_id,
        snap_repo,
        rs_repo,
        workforce_result_repo,
        scenario_repo,
        depth_plan_repo,
        depth_artifact_repo,
        workspace_id=workspace_id,
        include_series=include_series,
    )
    if resp is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    return resp


@router.post("/{workspace_id}/engine/batch", response_model=BatchResponse)
async def create_batch_run(
    workspace_id: UUID,
    body: BatchRunRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
    batch_repo: BatchRepository = Depends(get_batch_repo),
    mv_repo: ModelVersionRepository = Depends(get_model_version_repo),
    md_repo: ModelDataRepository = Depends(get_model_data_repo),
    constraint_repo: ConstraintSetRepository = Depends(get_constraint_set_repo),
    workforce_result_repo: WorkforceResultRepository = Depends(get_workforce_result_repo),
) -> BatchResponse:
    """Execute a batch of scenario runs with status tracking."""
    model_version_id = UUID(body.model_version_id)
    await _enforce_model_provenance(model_version_id, mv_repo)
    loaded = await _ensure_model_loaded(model_version_id, mv_repo, md_repo)

    batch_id = new_uuid7()

    # Create batch record as RUNNING
    await batch_repo.create(
        batch_id=batch_id,
        run_ids=[],
        status="RUNNING",
        workspace_id=workspace_id,
    )

    # P5-2: Auto-load curated satellite coefficients when not provided
    if body.satellite_coefficients is not None:
        coeffs = _make_satellite_coefficients(body.satellite_coefficients)
        employment_coeff_year = (
            body.scenarios[0].base_year
            if body.scenarios
            else loaded.model_version.base_year
        )
    else:
        loaded_coeffs = load_satellite_coefficients(
            year=body.scenarios[0].base_year if body.scenarios else 2023,
            sector_codes=loaded.sector_codes,
        )
        coeffs = loaded_coeffs.coefficients
        employment_coeff_year = getattr(
            loaded_coeffs.provenance,
            "employment_coeff_year",
            (
                body.scenarios[0].base_year
                if body.scenarios
                else loaded.model_version.base_year
            ),
        )
        _logger.info("P5-2: Auto-loaded curated satellite coefficients for batch run")
    constraint_specs, constraint_set_version_id = await _resolve_constraint_specs(
        workspace_id,
        model_version_id,
        loaded.sector_codes,
        constraint_repo,
    )
    scenarios: list[ScenarioInput] = []
    for sp in body.scenarios:
        # Sprint 17: baseline handling per scenario
        sp_baseline_run_id: UUID | None = None
        sp_baseline_annual_data: dict[int, dict[str, dict[str, float]]] | None = None
        if sp.baseline_run_id is not None:
            sp_baseline_run_id = UUID(sp.baseline_run_id)
            sp_baseline_rows = await rs_repo.get_by_run_series(
                sp_baseline_run_id, series_kind="annual",
            )
            if not sp_baseline_rows:
                sp_baseline_snap = await snap_repo.get(sp_baseline_run_id)
                if sp_baseline_snap is None:
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "reason_code": "RS_BASELINE_NOT_FOUND",
                            "message": f"Baseline run {sp_baseline_run_id} not found.",
                        },
                    )
                from src.engine.runseries_delta import validate_baseline_has_series
                try:
                    validate_baseline_has_series(sp_baseline_rows)
                except RunSeriesValidationError as exc:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "reason_code": exc.reason_code,
                            "message": str(exc),
                        },
                    ) from exc
            else:
                sp_baseline_annual_data = {}
                for row in sp_baseline_rows:
                    yr = row.year
                    mt = row.metric_type
                    sp_baseline_annual_data.setdefault(yr, {})[mt] = dict(row.values)

        scenarios.append(ScenarioInput(
            scenario_spec_id=new_uuid7(),
            scenario_spec_version=1,
            name=sp.name,
            annual_shocks=_annual_shocks_to_numpy(sp.annual_shocks),
            base_year=sp.base_year,
            deflators=_deflators_to_dict(sp.deflators),
            sensitivity_multipliers=sp.sensitivity_multipliers,
            baseline_run_id=sp_baseline_run_id,
            baseline_annual_data=sp_baseline_annual_data,
        ))

    settings = get_settings()
    runner = BatchRunner(model_store=_model_store, environment=settings.ENVIRONMENT.value)
    request = BatchRequest(
        scenarios=scenarios,
        model_version_id=model_version_id,
        satellite_coefficients=coeffs,
        version_refs=_make_version_refs(),
        constraints=constraint_specs,
    )

    try:
        batch_result = runner.run(request)

        # P6-3: Get model denomination for persistence + response
        batch_denom = getattr(loaded.model_version, "model_denomination", "SAR_MILLIONS")

        # Persist results
        run_ids: list[str] = []
        responses: list[RunResponse] = []
        from src.services.run_execution import RunExecutionService

        for sr in batch_result.run_results:
            await _persist_run_result(
                sr, snap_repo, rs_repo,
                workspace_id=workspace_id,
                model_denomination=batch_denom,
                constraint_set_version_id=constraint_set_version_id,
            )
            await RunExecutionService()._persist_workforce_result(
                sr=sr,
                repo=workforce_result_repo,
                workspace_id=workspace_id,
                coefficients=coeffs,
                employment_coeff_year=employment_coeff_year,
            )
            run_ids.append(str(sr.snapshot.run_id))
            workforce = await _load_workforce_response(
                sr.snapshot.run_id, workforce_result_repo,
            )
            responses.append(
                _single_run_to_response(
                    sr,
                    model_denomination=batch_denom,
                    workforce=workforce,
                )
            )

        # Update batch to COMPLETED with run IDs
        batch_row = await batch_repo.get(batch_id)
        if batch_row is not None:
            batch_row.run_ids = run_ids
            batch_row.status = "COMPLETED"
            await batch_repo._session.flush()

        return BatchResponse(batch_id=str(batch_id), status="COMPLETED", results=responses)

    except TypeIIValidationError as exc:
        await batch_repo.update_status(batch_id, "FAILED")
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": str(exc),
            },
        ) from exc
    except ValueMeasuresValidationError as exc:
        await batch_repo.update_status(batch_id, "FAILED")
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": str(exc),
                "environment": exc.environment,
                "measure": exc.measure,
            },
        ) from exc
    except RunSeriesValidationError as exc:
        await batch_repo.update_status(batch_id, "FAILED")
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": str(exc),
            },
        ) from exc
    except Exception:
        await batch_repo.update_status(batch_id, "FAILED")
        raise


@router.get("/{workspace_id}/engine/batch/{batch_id}", response_model=BatchResponse)
async def get_batch_status(
    workspace_id: UUID,
    batch_id: UUID,
    include_series: bool = Query(default=False),
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
    batch_repo: BatchRepository = Depends(get_batch_repo),
    workforce_result_repo: WorkforceResultRepository = Depends(get_workforce_result_repo),
    scenario_repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
    depth_plan_repo: DepthPlanRepository = Depends(get_depth_plan_repo),
    depth_artifact_repo: DepthArtifactRepository = Depends(get_depth_artifact_repo),
) -> BatchResponse:
    """Get batch run status and results (workspace-scoped — Amendment 3).

    Sprint 17: include_series=true returns annual/peak/delta rows.
    """
    batch_row = await batch_repo.get(batch_id)
    if batch_row is None:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found.")
    # Amendment 3: verify batch belongs to this workspace
    if batch_row.workspace_id is not None and batch_row.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found.")

    responses: list[RunResponse] = []
    for rid_str in batch_row.run_ids:
        resp = await _load_run_response(
            UUID(rid_str),
            snap_repo,
            rs_repo,
            workforce_result_repo,
            scenario_repo,
            depth_plan_repo,
            depth_artifact_repo,
            workspace_id=workspace_id,
            include_series=include_series,
        )
        if resp is not None:
            responses.append(resp)

    return BatchResponse(
        batch_id=str(batch_id),
        status=batch_row.status,
        results=responses,
    )
