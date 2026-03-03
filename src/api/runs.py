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
    get_model_data_repo,
    get_model_version_repo,
    get_result_set_repo,
    get_run_snapshot_repo,
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
from src.engine.model_store import LoadedModel, ModelStore, compute_model_checksum
from src.engine.satellites import SatelliteCoefficients
from src.engine.runseries_delta import RunSeriesValidationError
from src.engine.type_ii_validation import TypeIIValidationError
from src.engine.value_measures_validation import ValueMeasuresValidationError
from src.models.common import new_uuid7
from src.models.model_version import ModelVersion
from src.repositories.engine import (
    BatchRepository,
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)

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
    satellite_coefficients: SatelliteCoeffsPayload
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
    satellite_coefficients: SatelliteCoeffsPayload


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
    # Sprint 17: RunSeries fields
    year: int | None = None
    series_kind: str | None = None
    baseline_run_id: str | None = None


class SnapshotResponse(BaseModel):
    run_id: str
    model_version_id: str


class RunResponse(BaseModel):
    run_id: str
    result_sets: list[ResultSetResponse]
    snapshot: SnapshotResponse


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


def _single_run_to_response(sr: SingleRunResult, *, include_series: bool = False) -> RunResponse:
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
                year=rs.year,
                series_kind=rs.series_kind,
                baseline_run_id=str(rs.baseline_run_id) if rs.baseline_run_id else None,
            )
            for rs in rows
        ],
        snapshot=SnapshotResponse(
            run_id=str(sr.snapshot.run_id),
            model_version_id=str(sr.snapshot.model_version_id),
        ),
    )


async def _persist_run_result(
    sr: SingleRunResult,
    snap_repo: RunSnapshotRepository,
    rs_repo: ResultSetRepository,
    workspace_id: UUID | None = None,
) -> None:
    """Persist a SingleRunResult to DB (snapshot + result sets)."""
    snap = sr.snapshot
    await snap_repo.create(
        run_id=snap.run_id,
        model_version_id=snap.model_version_id,
        taxonomy_version_id=snap.taxonomy_version_id,
        concordance_version_id=snap.concordance_version_id,
        mapping_library_version_id=snap.mapping_library_version_id,
        assumption_library_version_id=snap.assumption_library_version_id,
        prompt_pack_version_id=snap.prompt_pack_version_id,
        workspace_id=workspace_id,
    )
    for rs in sr.result_sets:
        await rs_repo.create(
            result_id=rs.result_id,
            run_id=rs.run_id,
            metric_type=rs.metric_type,
            values=rs.values,
            workspace_id=workspace_id,
            year=rs.year,
            series_kind=rs.series_kind,
            baseline_run_id=rs.baseline_run_id,
        )


async def _load_run_response(
    run_id: UUID,
    snap_repo: RunSnapshotRepository,
    rs_repo: ResultSetRepository,
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
        ),
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
) -> RunResponse:
    """Execute a single scenario run."""
    model_version_id = UUID(body.model_version_id)
    await _enforce_model_provenance(model_version_id, mv_repo)
    await _ensure_model_loaded(model_version_id, mv_repo, md_repo)

    coeffs = _make_satellite_coefficients(body.satellite_coefficients)

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

    # Persist to DB (with workspace scoping — Amendment 3)
    await _persist_run_result(sr, snap_repo, rs_repo, workspace_id=workspace_id)

    return _single_run_to_response(sr)


@router.get("/{workspace_id}/engine/runs/{run_id}", response_model=RunResponse)
async def get_run_results(
    workspace_id: UUID,
    run_id: UUID,
    include_series: bool = Query(default=False),
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
) -> RunResponse:
    """Get results for a completed run (workspace-scoped — Amendment 3).

    Sprint 17: include_series=true returns annual/peak/delta rows.
    """
    resp = await _load_run_response(
        run_id, snap_repo, rs_repo,
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
) -> BatchResponse:
    """Execute a batch of scenario runs with status tracking."""
    model_version_id = UUID(body.model_version_id)
    await _enforce_model_provenance(model_version_id, mv_repo)
    await _ensure_model_loaded(model_version_id, mv_repo, md_repo)

    batch_id = new_uuid7()

    # Create batch record as RUNNING
    await batch_repo.create(
        batch_id=batch_id,
        run_ids=[],
        status="RUNNING",
        workspace_id=workspace_id,
    )

    coeffs = _make_satellite_coefficients(body.satellite_coefficients)
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
    )

    try:
        batch_result = runner.run(request)

        # Persist results
        run_ids: list[str] = []
        responses: list[RunResponse] = []
        for sr in batch_result.run_results:
            await _persist_run_result(sr, snap_repo, rs_repo, workspace_id=workspace_id)
            run_ids.append(str(sr.snapshot.run_id))
            responses.append(_single_run_to_response(sr))

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
            UUID(rid_str), snap_repo, rs_repo,
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
