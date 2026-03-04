"""Portfolio optimization API endpoints — Sprint 21.

POST /{workspace_id}/portfolio/optimize   — compute (201 new / 200 idempotent)
GET  /{workspace_id}/portfolio/{id}       — get by ID
GET  /{workspace_id}/portfolio            — paginated list

Workspace-scoped, auth-gated, idempotent by config hash.
"""

import hashlib
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_deps import WorkspaceMember, require_workspace_member
from src.api.dependencies import (
    get_portfolio_repo,
    get_result_set_repo,
    get_run_snapshot_repo,
)
from src.db.session import get_async_session
from src.db.tables import PortfolioOptimizationRow
from src.engine.portfolio_optimizer import (
    CandidateRun,
    PortfolioInfeasibleError,
    PortfolioResult,
    optimize_portfolio,
)
from src.models.common import new_uuid7
from src.models.portfolio import (
    PortfolioConfig,
    PortfolioListResponse,
    PortfolioOptimizationResponse,
)
from src.repositories.engine import ResultSetRepository, RunSnapshotRepository
from src.repositories.portfolio import PortfolioRepository

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workspaces", tags=["portfolio"])

OPTIMIZATION_VERSION = "portfolio_v1"
MAX_CANDIDATES = 25


# ---------------------------------------------------------------------------
# Relaxed request schema (bounds checked explicitly in endpoint)
# ---------------------------------------------------------------------------


class _RawConfig(BaseModel):
    """Relaxed config that skips Pydantic bounds so the endpoint can validate."""

    objective_metric: str = ""
    cost_metric: str = ""
    candidate_run_ids: list[str] = Field(default_factory=list)
    budget: float = 0.0
    min_selected: int = 1
    max_selected: int | None = None
    group_caps: dict[str, int] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_hash(
    candidate_run_ids: list[str],
    objective_metric: str,
    cost_metric: str,
    budget: float,
    min_selected: int,
    max_selected: int | None,
    group_caps: dict[str, int] | None,
) -> str:
    """SHA-256 of canonical JSON config with sorted keys."""
    payload = json.dumps(
        {
            "budget": budget,
            "candidate_run_ids": sorted(candidate_run_ids),
            "cost_metric": cost_metric,
            "group_caps": dict(sorted(group_caps.items())) if group_caps else None,
            "max_selected": max_selected,
            "min_selected": min_selected,
            "objective_metric": objective_metric,
            "optimization_version": OPTIMIZATION_VERSION,
        },
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _result_checksum(result_json: dict) -> str:
    """SHA-256 of result_json + optimization_version."""
    payload = json.dumps(
        {
            "optimization_version": OPTIMIZATION_VERSION,
            "result": result_json,
        },
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _row_to_response(row: PortfolioOptimizationRow) -> PortfolioOptimizationResponse:
    """Convert DB row to API response model."""
    config = PortfolioConfig(
        objective_metric=row.objective_metric,
        cost_metric=row.cost_metric,
        candidate_run_ids=[UUID(r) for r in row.candidate_run_ids_json],
        budget=row.budget,
        min_selected=row.min_selected,
        max_selected=row.max_selected,
        group_caps=row.config_json.get("group_caps") if row.config_json else None,
    )
    result = row.result_json or {}
    return PortfolioOptimizationResponse(
        portfolio_id=str(row.portfolio_id),
        workspace_id=str(row.workspace_id),
        model_version_id=str(row.model_version_id),
        config=config,
        selected_run_ids=row.selected_run_ids_json,
        total_objective=result.get("total_objective", 0.0),
        total_cost=result.get("total_cost", 0.0),
        solver_method=result.get("solver_method", ""),
        candidates_evaluated=result.get("candidates_evaluated", 0),
        feasible_count=result.get("feasible_count", 0),
        optimization_version=row.optimization_version,
        result_checksum=row.result_checksum,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# POST /{workspace_id}/portfolio/optimize
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/portfolio/optimize",
    status_code=201,
    response_model=PortfolioOptimizationResponse,
)
async def create_portfolio(
    workspace_id: UUID,
    body: _RawConfig,
    member: WorkspaceMember = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_async_session),  # for rollback on race condition
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
    pf_repo: PortfolioRepository = Depends(get_portfolio_repo),
) -> PortfolioOptimizationResponse | JSONResponse:
    """Create or retrieve a portfolio optimization.

    Idempotent: returns 200 with existing result if config_hash matches.
    """
    raw = body

    # --- 1. No candidates ---
    if not raw.candidate_run_ids:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "PORTFOLIO_NO_CANDIDATES",
                "message": "No candidate run IDs provided.",
            },
        )

    # --- 1b. Empty metric names ---
    if not raw.objective_metric:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "PORTFOLIO_INVALID_CONFIG",
                "message": "objective_metric must not be empty.",
            },
        )
    if not raw.cost_metric:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "PORTFOLIO_INVALID_CONFIG",
                "message": "cost_metric must not be empty.",
            },
        )

    # --- 2. Duplicate candidates ---
    if len(raw.candidate_run_ids) != len(set(raw.candidate_run_ids)):
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "PORTFOLIO_DUPLICATE_CANDIDATES",
                "message": "Duplicate candidate run IDs provided.",
            },
        )

    # --- 3. Parse UUIDs ---
    try:
        run_uuids = [UUID(rid) for rid in raw.candidate_run_ids]
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "PORTFOLIO_INVALID_CONFIG",
                "message": f"Invalid run ID format: {exc}",
            },
        ) from exc

    # --- 4. Check all run_ids exist in workspace ---
    snap_rows = []
    for rid in run_uuids:
        snap_row = await snap_repo.get(rid)
        if snap_row is None or snap_row.workspace_id != workspace_id:
            raise HTTPException(
                status_code=404,
                detail={
                    "reason_code": "PORTFOLIO_RUN_NOT_FOUND",
                    "message": f"Run {rid} not found in workspace {workspace_id}.",
                },
            )
        snap_rows.append(snap_row)

    # --- 5. Check model compatibility (all same model_version_id) ---
    model_version_ids = {sr.model_version_id for sr in snap_rows}
    if len(model_version_ids) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "PORTFOLIO_MODEL_MISMATCH",
                "message": (
                    "All candidate runs must share the same model_version_id. "
                    f"Found {len(model_version_ids)} distinct versions."
                ),
            },
        )
    model_version_id = model_version_ids.pop()

    # --- 6. Check both metrics exist for every candidate ---
    candidates: list[CandidateRun] = []
    for rid in run_uuids:
        result_sets = await rs_repo.get_by_run(rid)
        metric_map: dict[str, float] = {}
        for rs in result_sets:
            if rs.metric_type == raw.objective_metric:
                # Sum values across sectors for scalar metric
                metric_map["objective"] = sum(rs.values.values())
            if rs.metric_type == raw.cost_metric:
                metric_map["cost"] = sum(rs.values.values())

        if "objective" not in metric_map:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason_code": "PORTFOLIO_METRIC_NOT_FOUND",
                    "message": (f"Metric '{raw.objective_metric}' not found for run {rid}."),
                },
            )
        if "cost" not in metric_map:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason_code": "PORTFOLIO_METRIC_NOT_FOUND",
                    "message": (f"Metric '{raw.cost_metric}' not found for run {rid}."),
                },
            )

        candidates.append(
            CandidateRun(
                run_id=rid,
                objective_value=metric_map["objective"],
                cost=metric_map["cost"],
            )
        )

    # --- 7. Config sanity ---
    if raw.budget <= 0:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "PORTFOLIO_INVALID_CONFIG",
                "message": f"Budget must be positive, got {raw.budget}.",
            },
        )
    if raw.min_selected < 1:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "PORTFOLIO_INVALID_CONFIG",
                "message": f"min_selected must be >= 1, got {raw.min_selected}.",
            },
        )
    if raw.max_selected is not None and raw.max_selected < 1:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "PORTFOLIO_INVALID_CONFIG",
                "message": f"max_selected must be >= 1, got {raw.max_selected}.",
            },
        )
    if raw.max_selected is not None and raw.max_selected < raw.min_selected:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "PORTFOLIO_INVALID_CONFIG",
                "message": (
                    f"max_selected ({raw.max_selected}) < min_selected ({raw.min_selected})."
                ),
            },
        )
    if raw.group_caps is not None:
        for key, cap in raw.group_caps.items():
            if cap < 1:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "reason_code": "PORTFOLIO_INVALID_CONFIG",
                        "message": f"Group cap for '{key}' must be >= 1, got {cap}.",
                    },
                )

    # --- 8. Candidate limit ---
    if len(run_uuids) > MAX_CANDIDATES:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED",
                "message": (f"Too many candidates ({len(run_uuids)} > {MAX_CANDIDATES})."),
            },
        )

    # --- 9. Idempotency check ---
    ch = _config_hash(
        candidate_run_ids=raw.candidate_run_ids,
        objective_metric=raw.objective_metric,
        cost_metric=raw.cost_metric,
        budget=raw.budget,
        min_selected=raw.min_selected,
        max_selected=raw.max_selected,
        group_caps=raw.group_caps,
    )
    existing = await pf_repo.get_by_config_for_workspace(workspace_id, ch)
    if existing is not None:
        resp_data = _row_to_response(existing)
        return JSONResponse(
            content=resp_data.model_dump(mode="json"),
            status_code=200,
        )

    # --- 10. Run optimizer ---
    try:
        result: PortfolioResult = optimize_portfolio(
            candidates,
            raw.budget,
            min_selected=raw.min_selected,
            max_selected=raw.max_selected,
            group_caps=raw.group_caps,
        )
    except PortfolioInfeasibleError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": exc.message,
            },
        ) from exc

    # --- 11. Serialize and persist ---
    selected_run_ids_json = sorted([str(rid) for rid in result.selected_run_ids])
    candidate_run_ids_json = sorted(raw.candidate_run_ids)

    result_json = {
        "selected_run_ids": selected_run_ids_json,
        "total_objective": result.total_objective,
        "total_cost": result.total_cost,
        "solver_method": result.solver_method,
        "candidates_evaluated": result.candidates_evaluated,
        "feasible_count": result.feasible_count,
    }

    config_json = {
        "objective_metric": raw.objective_metric,
        "cost_metric": raw.cost_metric,
        "candidate_run_ids": candidate_run_ids_json,
        "budget": raw.budget,
        "min_selected": raw.min_selected,
        "max_selected": raw.max_selected,
        "group_caps": raw.group_caps,
    }

    portfolio_id = new_uuid7()
    rc = _result_checksum(result_json)

    try:
        row = await pf_repo.create(
            portfolio_id=portfolio_id,
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            optimization_version=OPTIMIZATION_VERSION,
            config_json=config_json,
            config_hash=ch,
            objective_metric=raw.objective_metric,
            cost_metric=raw.cost_metric,
            budget=raw.budget,
            min_selected=raw.min_selected,
            max_selected=raw.max_selected,
            candidate_run_ids_json=candidate_run_ids_json,
            selected_run_ids_json=selected_run_ids_json,
            result_json=result_json,
            result_checksum=rc,
        )
    except IntegrityError:
        # Race condition: concurrent request inserted same config_hash.
        # Rollback failed transaction, then SELECT the winning row.
        await session.rollback()
        existing = await pf_repo.get_by_config_for_workspace(workspace_id, ch)
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
# GET /{workspace_id}/portfolio/{portfolio_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/portfolio/{portfolio_id}",
    response_model=PortfolioOptimizationResponse,
)
async def get_portfolio(
    workspace_id: UUID,
    portfolio_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    pf_repo: PortfolioRepository = Depends(get_portfolio_repo),
) -> PortfolioOptimizationResponse:
    """Get a single portfolio optimization by ID (workspace-scoped)."""
    row = await pf_repo.get_for_workspace(portfolio_id, workspace_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": "PORTFOLIO_NOT_FOUND",
                "message": (f"Portfolio {portfolio_id} not found in workspace {workspace_id}."),
            },
        )
    return _row_to_response(row)


# ---------------------------------------------------------------------------
# GET /{workspace_id}/portfolio
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/portfolio",
    response_model=PortfolioListResponse,
)
async def list_portfolios(
    workspace_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    member: WorkspaceMember = Depends(require_workspace_member),
    pf_repo: PortfolioRepository = Depends(get_portfolio_repo),
) -> PortfolioListResponse:
    """List portfolio optimizations for a workspace (paginated)."""
    rows, total = await pf_repo.list_for_workspace(
        workspace_id,
        limit=limit,
        offset=offset,
    )
    return PortfolioListResponse(
        items=[_row_to_response(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
