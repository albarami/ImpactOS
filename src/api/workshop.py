"""Workshop session API endpoints -- Sprint 22.

POST /{workspace_id}/workshop/sessions              -- create (201 new / 200 idempotent)
GET  /{workspace_id}/workshop/sessions/{session_id}  -- get by ID
GET  /{workspace_id}/workshop/sessions               -- paginated list
POST /{workspace_id}/workshop/preview                -- ephemeral engine preview
POST /{workspace_id}/workshop/sessions/{session_id}/commit  -- commit session
POST /{workspace_id}/workshop/sessions/{session_id}/export  -- export gate

Workspace-scoped, auth-gated, idempotent by config_hash.
Preview is ephemeral (no persist). Commit creates a real RunSnapshot.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_deps import WorkspaceMember, require_workspace_member
from src.api.dependencies import (
    get_model_data_repo,
    get_model_version_repo,
    get_result_set_repo,
    get_run_snapshot_repo,
    get_workshop_session_repo,
)
from src.api.runs import (
    SatelliteCoeffsPayload,
    _annual_shocks_to_numpy,
    _deflators_to_dict,
    _ensure_model_loaded,
    _make_satellite_coefficients,
    _make_version_refs,
    _model_store,
    _persist_run_result,
)
from src.config.settings import get_settings
from src.db.session import get_async_session
from src.db.tables import WorkshopSessionRow
from src.engine.batch import BatchRequest, BatchRunner, ScenarioInput
from src.engine.runseries_delta import RunSeriesValidationError
from src.engine.type_ii_validation import TypeIIValidationError
from src.engine.value_measures_validation import ValueMeasuresValidationError
from src.engine.workshop_transform import (
    SliderInput,
    WorkshopTransformError,
    transform_sliders,
    validate_base_shocks,
    validate_sliders,
    workshop_config_hash,
)
from src.models.common import new_uuid7
from src.models.workshop import (
    SliderItem,
    WorkshopListResponse,
    WorkshopSessionResponse,
)
from src.repositories.engine import (
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.workshop import WorkshopSessionRepository

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workspaces", tags=["workshop"])


# ---------------------------------------------------------------------------
# Relaxed request schemas (bounds checked explicitly in endpoints)
# ---------------------------------------------------------------------------


class _SliderItemRaw(BaseModel):
    sector_code: str = ""
    pct_delta: float = 0.0


class CreateSessionRequest(BaseModel):
    baseline_run_id: str
    base_shocks: dict[str, list[float]]
    sliders: list[_SliderItemRaw] = Field(default_factory=list)


class PreviewRequest(BaseModel):
    baseline_run_id: str
    base_shocks: dict[str, list[float]]
    sliders: list[_SliderItemRaw] = Field(default_factory=list)
    model_version_id: str
    base_year: int
    satellite_coefficients: SatelliteCoeffsPayload


class CommitRequest(BaseModel):
    model_version_id: str
    base_year: int
    satellite_coefficients: SatelliteCoeffsPayload
    deflators: dict[str, float] | None = None


class WorkshopExportRequest(BaseModel):
    mode: str
    export_formats: list[str]
    pack_data: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_response(row: WorkshopSessionRow) -> WorkshopSessionResponse:
    """Convert DB row to API response model."""
    slider_config = [
        SliderItem(sector_code=s["sector_code"], pct_delta=s["pct_delta"])
        for s in (row.slider_config_json or [])
    ]
    return WorkshopSessionResponse(
        session_id=row.session_id,
        workspace_id=row.workspace_id,
        baseline_run_id=row.baseline_run_id,
        slider_config=slider_config,
        status=row.status,
        committed_run_id=row.committed_run_id,
        config_hash=row.config_hash,
        preview_summary=row.preview_summary_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _get_sector_codes(
    model_version_id: UUID,
    md_repo: ModelDataRepository,
) -> list[str]:
    """Load sector_codes from ModelData for the given model_version_id."""
    md_row = await md_repo.get(model_version_id)
    if md_row is None:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "WORKSHOP_NO_BASELINE",
                "message": f"Model data for model_version_id {model_version_id} not found.",
            },
        )
    return md_row.sector_codes


def _raw_sliders_to_inputs(sliders: list[_SliderItemRaw]) -> list[SliderInput]:
    """Convert raw slider items to typed SliderInput dataclasses."""
    return [SliderInput(sector_code=s.sector_code, pct_delta=s.pct_delta) for s in sliders]


# ---------------------------------------------------------------------------
# POST /{workspace_id}/workshop/sessions  (create, idempotent)
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/workshop/sessions",
    status_code=201,
    response_model=WorkshopSessionResponse,
)
async def create_workshop_session(
    workspace_id: UUID,
    body: CreateSessionRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_async_session),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    md_repo: ModelDataRepository = Depends(get_model_data_repo),
    ws_repo: WorkshopSessionRepository = Depends(get_workshop_session_repo),
) -> WorkshopSessionResponse | JSONResponse:
    """Create or retrieve a workshop session.

    Idempotent: returns 200 with existing session if config_hash matches.
    """
    # --- 1. Validate baseline_run_id exists in workspace ---
    baseline_run_id = UUID(body.baseline_run_id)
    snap_row = await snap_repo.get(baseline_run_id)
    if snap_row is None or snap_row.workspace_id != workspace_id:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "WORKSHOP_NO_BASELINE",
                "message": (
                    f"Baseline run {body.baseline_run_id} not found in workspace {workspace_id}."
                ),
            },
        )

    # --- 2. Get sector_codes from model ---
    sector_codes = await _get_sector_codes(snap_row.model_version_id, md_repo)

    # --- 3. Validate sliders ---
    slider_inputs = _raw_sliders_to_inputs(body.sliders)
    try:
        validate_sliders(slider_inputs, sector_codes)
    except WorkshopTransformError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": exc.message,
            },
        ) from exc

    # --- 4. Validate base_shocks ---
    try:
        validate_base_shocks(body.base_shocks, sector_codes)
    except WorkshopTransformError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": exc.message,
            },
        ) from exc

    # --- 5. Transform sliders -> annual_shocks ---
    transformed = transform_sliders(body.base_shocks, slider_inputs, sector_codes)

    # --- 6. Compute config_hash ---
    ch = workshop_config_hash(body.baseline_run_id, body.base_shocks, slider_inputs)

    # --- 7. Idempotency check ---
    existing = await ws_repo.get_by_config_for_workspace(workspace_id, ch)
    if existing is not None:
        resp_data = _row_to_response(existing)
        return JSONResponse(
            content=resp_data.model_dump(mode="json"),
            status_code=200,
        )

    # --- 8. Create session ---
    session_id = new_uuid7()
    slider_config_json = [
        {"sector_code": s.sector_code, "pct_delta": s.pct_delta} for s in slider_inputs
    ]

    try:
        row = await ws_repo.create(
            session_id=session_id,
            workspace_id=workspace_id,
            baseline_run_id=baseline_run_id,
            base_shocks_json=body.base_shocks,
            slider_config_json=slider_config_json,
            transformed_shocks_json=transformed,
            config_hash=ch,
        )
    except IntegrityError:
        # Race condition: concurrent request inserted same config_hash.
        # Rollback failed transaction, then SELECT the winning row.
        await session.rollback()
        existing = await ws_repo.get_by_config_for_workspace(workspace_id, ch)
        if existing is not None:
            resp_data = _row_to_response(existing)
            return JSONResponse(
                content=resp_data.model_dump(mode="json"),
                status_code=200,
            )
        _logger.error("Race-safe retry SELECT returned None after IntegrityError")
        raise

    return _row_to_response(row)


# ---------------------------------------------------------------------------
# GET /{workspace_id}/workshop/sessions/{session_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/workshop/sessions/{session_id}",
    response_model=WorkshopSessionResponse,
)
async def get_workshop_session(
    workspace_id: UUID,
    session_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    ws_repo: WorkshopSessionRepository = Depends(get_workshop_session_repo),
) -> WorkshopSessionResponse:
    """Get a single workshop session by ID (workspace-scoped)."""
    row = await ws_repo.get_for_workspace(session_id, workspace_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": "WORKSHOP_SESSION_NOT_FOUND",
                "message": f"Workshop session {session_id} not found in workspace {workspace_id}.",
            },
        )
    return _row_to_response(row)


# ---------------------------------------------------------------------------
# GET /{workspace_id}/workshop/sessions
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/workshop/sessions",
    response_model=WorkshopListResponse,
)
async def list_workshop_sessions(
    workspace_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    member: WorkspaceMember = Depends(require_workspace_member),
    ws_repo: WorkshopSessionRepository = Depends(get_workshop_session_repo),
) -> WorkshopListResponse:
    """List workshop sessions for a workspace (paginated)."""
    rows, total = await ws_repo.list_for_workspace(
        workspace_id,
        limit=limit,
        offset=offset,
    )
    return WorkshopListResponse(
        items=[_row_to_response(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# POST /{workspace_id}/workshop/preview  (ephemeral)
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/workshop/preview",
    status_code=200,
)
async def preview_workshop(
    workspace_id: UUID,
    body: PreviewRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    md_repo: ModelDataRepository = Depends(get_model_data_repo),
    mv_repo: ModelVersionRepository = Depends(get_model_version_repo),
) -> dict:
    """Run an ephemeral engine preview -- results NOT persisted.

    Same engine path as POST /engine/runs but without storing RunSnapshot/ResultSet.
    """
    # --- 1. Validate baseline ---
    baseline_run_id = UUID(body.baseline_run_id)
    snap_row = await snap_repo.get(baseline_run_id)
    if snap_row is None or snap_row.workspace_id != workspace_id:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "WORKSHOP_NO_BASELINE",
                "message": (
                    f"Baseline run {body.baseline_run_id} not found in workspace {workspace_id}."
                ),
            },
        )

    # --- 2. Get sector_codes and validate ---
    model_version_id = UUID(body.model_version_id)
    sector_codes = await _get_sector_codes(model_version_id, md_repo)

    slider_inputs = _raw_sliders_to_inputs(body.sliders)
    try:
        validate_sliders(slider_inputs, sector_codes)
    except WorkshopTransformError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": exc.message,
            },
        ) from exc

    try:
        validate_base_shocks(body.base_shocks, sector_codes)
    except WorkshopTransformError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": exc.message,
            },
        ) from exc

    # --- 3. Transform ---
    transformed = transform_sliders(body.base_shocks, slider_inputs, sector_codes)

    # --- 4. Run engine (ephemeral) ---
    try:
        await _ensure_model_loaded(model_version_id, mv_repo, md_repo)
        coeffs = _make_satellite_coefficients(body.satellite_coefficients)

        scenario = ScenarioInput(
            scenario_spec_id=new_uuid7(),
            scenario_spec_version=1,
            name="workshop_preview",
            annual_shocks=_annual_shocks_to_numpy(transformed),
            base_year=body.base_year,
            baseline_run_id=baseline_run_id,
        )

        settings = get_settings()
        runner = BatchRunner(model_store=_model_store, environment=settings.ENVIRONMENT.value)
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=model_version_id,
            satellite_coefficients=coeffs,
            version_refs=_make_version_refs(),
        )
        result = runner.run(request)
    except (TypeIIValidationError, ValueMeasuresValidationError, RunSeriesValidationError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": getattr(exc, "reason_code", "WORKSHOP_PREVIEW_FAILED"),
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        _logger.exception("Workshop preview engine failure")
        raise HTTPException(
            status_code=503,
            detail={
                "reason_code": "WORKSHOP_PREVIEW_FAILED",
                "message": f"Engine preview failed: {exc}",
            },
        ) from exc

    # --- 5. Return results WITHOUT persisting ---
    sr = result.run_results[0]
    preview_result_sets = []
    for rs in sr.result_sets:
        preview_result_sets.append(
            {
                "metric_type": rs.metric_type,
                "values": rs.values,
                "year": rs.year,
                "series_kind": rs.series_kind,
            }
        )

    return {
        "preview": True,
        "transformed_shocks": transformed,
        "result_sets": preview_result_sets,
    }


# ---------------------------------------------------------------------------
# POST /{workspace_id}/workshop/sessions/{session_id}/commit
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/workshop/sessions/{session_id}/commit",
    status_code=200,
    response_model=WorkshopSessionResponse,
)
async def commit_workshop_session(
    workspace_id: UUID,
    session_id: UUID,
    body: CommitRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    ws_repo: WorkshopSessionRepository = Depends(get_workshop_session_repo),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
    mv_repo: ModelVersionRepository = Depends(get_model_version_repo),
    md_repo: ModelDataRepository = Depends(get_model_data_repo),
) -> WorkshopSessionResponse:
    """Commit a draft workshop session -- creates a real RunSnapshot.

    If already committed returns 409.
    """
    # --- 1. Validate session exists and is in correct workspace ---
    row = await ws_repo.get_for_workspace(session_id, workspace_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": "WORKSHOP_SESSION_NOT_FOUND",
                "message": f"Workshop session {session_id} not found in workspace {workspace_id}.",
            },
        )

    # --- 2. Check status ---
    if row.status == "committed":
        raise HTTPException(
            status_code=409,
            detail={
                "reason_code": "WORKSHOP_ALREADY_COMMITTED",
                "message": f"Workshop session {session_id} is already committed.",
            },
        )

    # --- 3. Run engine with transformed_shocks_json from session ---
    model_version_id = UUID(body.model_version_id)
    try:
        await _ensure_model_loaded(model_version_id, mv_repo, md_repo)
        coeffs = _make_satellite_coefficients(body.satellite_coefficients)

        scenario = ScenarioInput(
            scenario_spec_id=new_uuid7(),
            scenario_spec_version=1,
            name="workshop_commit",
            annual_shocks=_annual_shocks_to_numpy(row.transformed_shocks_json),
            base_year=body.base_year,
            deflators=_deflators_to_dict(body.deflators),
            baseline_run_id=row.baseline_run_id,
        )

        settings = get_settings()
        runner = BatchRunner(model_store=_model_store, environment=settings.ENVIRONMENT.value)
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=model_version_id,
            satellite_coefficients=coeffs,
            version_refs=_make_version_refs(),
        )
        result = runner.run(request)
    except (TypeIIValidationError, ValueMeasuresValidationError, RunSeriesValidationError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": getattr(exc, "reason_code", "WORKSHOP_PREVIEW_FAILED"),
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        _logger.exception("Workshop commit engine failure")
        raise HTTPException(
            status_code=503,
            detail={
                "reason_code": "WORKSHOP_PREVIEW_FAILED",
                "message": f"Engine commit failed: {exc}",
            },
        ) from exc

    # --- 4. Persist run ---
    sr = result.run_results[0]
    await _persist_run_result(sr, snap_repo, rs_repo, workspace_id=workspace_id)

    # --- 5. Update session status ---
    committed_run_id = sr.snapshot.run_id
    updated_row = await ws_repo.update_status(
        session_id,
        status="committed",
        committed_run_id=committed_run_id,
    )

    return _row_to_response(updated_row)


# ---------------------------------------------------------------------------
# POST /{workspace_id}/workshop/sessions/{session_id}/export
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/workshop/sessions/{session_id}/export",
    status_code=200,
)
async def export_workshop_session(
    workspace_id: UUID,
    session_id: UUID,
    body: WorkshopExportRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    ws_repo: WorkshopSessionRepository = Depends(get_workshop_session_repo),
) -> dict:
    """Export gate -- returns committed_run_id for client to use with POST /exports.

    Session must be committed (status == 'committed').
    """
    # --- 1. Validate session exists ---
    row = await ws_repo.get_for_workspace(session_id, workspace_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": "WORKSHOP_SESSION_NOT_FOUND",
                "message": f"Workshop session {session_id} not found in workspace {workspace_id}.",
            },
        )

    # --- 2. Check committed status ---
    if row.status != "committed":
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "WORKSHOP_NOT_COMMITTED",
                "message": f"Workshop session {session_id} is not committed (status={row.status}).",
            },
        )

    # --- 3. Return committed_run_id for client ---
    return {
        "session_id": str(row.session_id),
        "committed_run_id": str(row.committed_run_id),
        "status": row.status,
        "message": "Use committed_run_id with POST /exports to generate export.",
    }
