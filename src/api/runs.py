"""FastAPI engine/run endpoints — MVP-3 Sections 6.2.9, 6.2.10.

POST /v1/engine/models                                       — register (global)
POST /v1/workspaces/{workspace_id}/engine/runs               — single run
GET  /v1/workspaces/{workspace_id}/engine/runs/{run_id}      — get results
POST /v1/workspaces/{workspace_id}/engine/batch              — batch runs
GET  /v1/workspaces/{workspace_id}/engine/batch/{batch_id}   — batch status

S0-4: Workspace-scoped runs/batch. Model registration stays global.
Batch status tracking (PENDING → RUNNING → COMPLETED/FAILED).

Deterministic only — no LLM calls.
ModelStore kept as in-memory LRU cache for synchronous engine access.
DB repos persist model metadata, run snapshots, result sets, batches.
"""

from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import (
    get_batch_repo,
    get_model_data_repo,
    get_model_version_repo,
    get_result_set_repo,
    get_run_snapshot_repo,
)
from src.engine.batch import (
    BatchRequest,
    BatchRunner,
    ScenarioInput,
    SingleRunResult,
)
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteCoefficients
from src.models.common import new_uuid7
from src.repositories.engine import (
    BatchRepository,
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)

# Global model registration router (not workspace-scoped)
models_router = APIRouter(prefix="/v1/engine", tags=["engine"])

# Workspace-scoped engine router for runs/batch
router = APIRouter(prefix="/v1/workspaces", tags=["engine"])

# ---------------------------------------------------------------------------
# In-memory LRU cache for synchronous engine access (BatchRunner needs .get())
# ---------------------------------------------------------------------------

_model_store = ModelStore()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class RegisterModelRequest(BaseModel):
    Z: list[list[float]]
    x: list[float]
    sector_codes: list[str]
    base_year: int
    source: str


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


class ScenarioPayload(BaseModel):
    name: str
    annual_shocks: dict[str, list[float]]
    base_year: int
    deflators: dict[str, float] | None = None
    sensitivity_multipliers: list[float] | None = None


class BatchRunRequest(BaseModel):
    model_version_id: str
    scenarios: list[ScenarioPayload]
    satellite_coefficients: SatelliteCoeffsPayload


class ResultSetResponse(BaseModel):
    result_id: str
    metric_type: str
    values: dict[str, float]


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


def _single_run_to_response(sr: SingleRunResult) -> RunResponse:
    return RunResponse(
        run_id=str(sr.snapshot.run_id),
        result_sets=[
            ResultSetResponse(
                result_id=str(rs.result_id),
                metric_type=rs.metric_type,
                values=rs.values,
            )
            for rs in sr.result_sets
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
    )
    for rs in sr.result_sets:
        await rs_repo.create(
            result_id=rs.result_id,
            run_id=rs.run_id,
            metric_type=rs.metric_type,
            values=rs.values,
        )


async def _load_run_response(
    run_id: UUID,
    snap_repo: RunSnapshotRepository,
    rs_repo: ResultSetRepository,
) -> RunResponse | None:
    """Load a RunResponse from DB."""
    snap_row = await snap_repo.get(run_id)
    if snap_row is None:
        return None
    rs_rows = await rs_repo.get_by_run(run_id)
    return RunResponse(
        run_id=str(snap_row.run_id),
        result_sets=[
            ResultSetResponse(
                result_id=str(r.result_id),
                metric_type=r.metric_type,
                values=r.values,
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
    mv_repo: ModelVersionRepository = Depends(get_model_version_repo),
    md_repo: ModelDataRepository = Depends(get_model_data_repo),
) -> RegisterModelResponse:
    """Register an I-O model (Z, x, sector codes)."""
    try:
        mv = _model_store.register(
            Z=np.array(body.Z),
            x=np.array(body.x),
            sector_codes=body.sector_codes,
            base_year=body.base_year,
            source=body.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Persist to DB
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
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
) -> RunResponse:
    """Execute a single scenario run."""
    model_version_id = UUID(body.model_version_id)
    try:
        _model_store.get(model_version_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Model {body.model_version_id} not found.",
        ) from exc

    coeffs = _make_satellite_coefficients(body.satellite_coefficients)

    scenario = ScenarioInput(
        scenario_spec_id=new_uuid7(),
        scenario_spec_version=1,
        name="single_run",
        annual_shocks=_annual_shocks_to_numpy(body.annual_shocks),
        base_year=body.base_year,
        deflators=_deflators_to_dict(body.deflators),
    )

    runner = BatchRunner(model_store=_model_store)
    request = BatchRequest(
        scenarios=[scenario],
        model_version_id=model_version_id,
        satellite_coefficients=coeffs,
        version_refs=_make_version_refs(),
    )

    result = runner.run(request)
    sr = result.run_results[0]

    # Persist to DB
    await _persist_run_result(sr, snap_repo, rs_repo)

    return _single_run_to_response(sr)


@router.get("/{workspace_id}/engine/runs/{run_id}", response_model=RunResponse)
async def get_run_results(
    workspace_id: UUID,
    run_id: UUID,
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
) -> RunResponse:
    """Get results for a completed run."""
    resp = await _load_run_response(run_id, snap_repo, rs_repo)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    return resp


@router.post("/{workspace_id}/engine/batch", response_model=BatchResponse)
async def create_batch_run(
    workspace_id: UUID,
    body: BatchRunRequest,
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
    batch_repo: BatchRepository = Depends(get_batch_repo),
) -> BatchResponse:
    """Execute a batch of scenario runs with status tracking."""
    model_version_id = UUID(body.model_version_id)
    try:
        _model_store.get(model_version_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Model {body.model_version_id} not found.",
        ) from exc

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
        scenarios.append(ScenarioInput(
            scenario_spec_id=new_uuid7(),
            scenario_spec_version=1,
            name=sp.name,
            annual_shocks=_annual_shocks_to_numpy(sp.annual_shocks),
            base_year=sp.base_year,
            deflators=_deflators_to_dict(sp.deflators),
            sensitivity_multipliers=sp.sensitivity_multipliers,
        ))

    runner = BatchRunner(model_store=_model_store)
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
            await _persist_run_result(sr, snap_repo, rs_repo)
            run_ids.append(str(sr.snapshot.run_id))
            responses.append(_single_run_to_response(sr))

        # Update batch to COMPLETED with run IDs
        batch_row = await batch_repo.get(batch_id)
        if batch_row is not None:
            batch_row.run_ids = run_ids
            batch_row.status = "COMPLETED"
            await batch_repo._session.flush()

        return BatchResponse(batch_id=str(batch_id), status="COMPLETED", results=responses)

    except Exception:
        await batch_repo.update_status(batch_id, "FAILED")
        raise


@router.get("/{workspace_id}/engine/batch/{batch_id}", response_model=BatchResponse)
async def get_batch_status(
    workspace_id: UUID,
    batch_id: UUID,
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
    batch_repo: BatchRepository = Depends(get_batch_repo),
) -> BatchResponse:
    """Get batch run status and results."""
    batch_row = await batch_repo.get(batch_id)
    if batch_row is None:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found.")

    responses: list[RunResponse] = []
    for rid_str in batch_row.run_ids:
        resp = await _load_run_response(UUID(rid_str), snap_repo, rs_repo)
        if resp is not None:
            responses.append(resp)

    return BatchResponse(
        batch_id=str(batch_id),
        status=batch_row.status,
        results=responses,
    )
