"""FastAPI engine/run endpoints — MVP-3 Sections 6.2.9, 6.2.10.

POST /v1/engine/models           — register a model
POST /v1/engine/runs             — single run
GET  /v1/engine/runs/{run_id}    — get run results
POST /v1/engine/batch            — batch runs
GET  /v1/engine/batch/{batch_id} — batch status

Deterministic only — no LLM calls.
In-memory stores for MVP; production uses PostgreSQL.
"""

from uuid import UUID

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.engine.batch import (
    BatchRequest,
    BatchRunner,
    ScenarioInput,
    SingleRunResult,
)
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteCoefficients
from src.models.common import new_uuid7

router = APIRouter(prefix="/v1/engine", tags=["engine"])

# ---------------------------------------------------------------------------
# In-memory stores (MVP — replaced by PostgreSQL in production)
# ---------------------------------------------------------------------------

_model_store = ModelStore()

# run_id -> SingleRunResult
_run_results: dict[UUID, SingleRunResult] = {}
# batch_id -> list of run_ids
_batch_results: dict[UUID, list[UUID]] = {}


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
    """Generate placeholder version refs for MVP.

    In production these would come from actual versioned data stores.
    """
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/models", status_code=201, response_model=RegisterModelResponse)
async def register_model(body: RegisterModelRequest) -> RegisterModelResponse:
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

    return RegisterModelResponse(
        model_version_id=str(mv.model_version_id),
        sector_count=mv.sector_count,
        checksum=mv.checksum,
    )


@router.post("/runs", response_model=RunResponse)
async def create_run(body: RunRequest) -> RunResponse:
    """Execute a single scenario run."""
    model_version_id = UUID(body.model_version_id)
    try:
        loaded = _model_store.get(model_version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Model {body.model_version_id} not found.") from exc

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
    _run_results[sr.snapshot.run_id] = sr

    return _single_run_to_response(sr)


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run_results(run_id: UUID) -> RunResponse:
    """Get results for a completed run."""
    sr = _run_results.get(run_id)
    if sr is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    return _single_run_to_response(sr)


@router.post("/batch", response_model=BatchResponse)
async def create_batch_run(body: BatchRunRequest) -> BatchResponse:
    """Execute a batch of scenario runs."""
    model_version_id = UUID(body.model_version_id)
    try:
        _model_store.get(model_version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Model {body.model_version_id} not found.") from exc

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

    batch_result = runner.run(request)
    batch_id = new_uuid7()

    # Store results
    run_ids: list[UUID] = []
    responses: list[RunResponse] = []
    for sr in batch_result.run_results:
        _run_results[sr.snapshot.run_id] = sr
        run_ids.append(sr.snapshot.run_id)
        responses.append(_single_run_to_response(sr))

    _batch_results[batch_id] = run_ids

    return BatchResponse(batch_id=str(batch_id), results=responses)


@router.get("/batch/{batch_id}", response_model=BatchResponse)
async def get_batch_status(batch_id: UUID) -> BatchResponse:
    """Get batch run status and results."""
    run_ids = _batch_results.get(batch_id)
    if run_ids is None:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found.")

    responses: list[RunResponse] = []
    for rid in run_ids:
        sr = _run_results.get(rid)
        if sr is not None:
            responses.append(_single_run_to_response(sr))

    return BatchResponse(batch_id=str(batch_id), results=responses)
