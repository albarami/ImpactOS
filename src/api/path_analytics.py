"""Path analytics API endpoints — Sprint 20.

POST /{workspace_id}/path-analytics          — compute (201 new / 200 idempotent)
GET  /{workspace_id}/path-analytics/{id}     — get by ID
GET  /{workspace_id}/path-analytics          — list by run

Workspace-scoped, auth-gated, idempotent by config hash.
"""

import hashlib
import json
import logging
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from pydantic import BaseModel, Field

from src.api.auth_deps import WorkspaceMember, require_workspace_member
from src.api.dependencies import (
    get_model_data_repo,
    get_model_version_repo,
    get_path_analysis_repo,
    get_result_set_repo,
    get_run_snapshot_repo,
)
from src.api.runs import _ensure_model_loaded
from src.db.tables import PathAnalysisRow
from src.engine.structural_path import (
    SPAConfigError,
    SPADimensionError,
    SPAResult,
    compute_spa,
)
from src.models.common import new_uuid7
from src.models.path import (
    ChokePointItem,
    DepthContributionItem,
    PathAnalysisConfig,
    PathAnalysisListResponse,
    PathAnalysisResponse,
    PathContributionItem,
)
from src.repositories.engine import (
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.path_analytics import PathAnalysisRepository


class _RawConfig(BaseModel):
    """Relaxed config that skips Pydantic bounds so the endpoint can validate."""

    max_depth: int = 6
    top_k: int = 20


class _CreateRequest(BaseModel):
    """Request body with relaxed config validation — bounds checked in endpoint."""

    run_id: UUID
    config: _RawConfig = Field(default_factory=_RawConfig)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workspaces", tags=["analytics"])

ANALYSIS_VERSION = "spa_v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_hash(config: PathAnalysisConfig) -> str:
    payload = json.dumps(
        {"max_depth": config.max_depth, "top_k": config.top_k},
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _result_checksum(result: SPAResult) -> str:
    payload = json.dumps(
        {
            "top_paths": [
                {
                    "s": p.source_sector,
                    "t": p.target_sector,
                    "d": p.depth,
                    "c": round(p.contribution, 15),
                }
                for p in result.top_paths
            ],
            "coverage_ratio": round(result.coverage_ratio, 15),
        },
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _reconstruct_delta_d(
    values: dict[str, float],
    sector_codes: list[str],
) -> np.ndarray:
    delta_d = np.zeros(len(sector_codes), dtype=np.float64)
    for idx, code in enumerate(sector_codes):
        delta_d[idx] = values.get(code, 0.0)
    return delta_d


def _row_to_response(row: PathAnalysisRow) -> PathAnalysisResponse:
    return PathAnalysisResponse(
        analysis_id=row.analysis_id,
        run_id=row.run_id,
        analysis_version=row.analysis_version,
        config=PathAnalysisConfig(max_depth=row.max_depth, top_k=row.top_k),
        config_hash=row.config_hash,
        top_paths=[PathContributionItem(**p) for p in row.top_paths_json],
        chokepoints=[ChokePointItem(**c) for c in row.chokepoints_json],
        depth_contributions={
            str(k): DepthContributionItem(**v)
            if isinstance(v, dict)
            else DepthContributionItem(signed=v, absolute=abs(v))
            for k, v in row.depth_contributions_json.items()
        },
        coverage_ratio=row.coverage_ratio,
        result_checksum=row.result_checksum,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# POST /{workspace_id}/path-analytics
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/path-analytics",
    status_code=201,
    response_model=PathAnalysisResponse,
)
async def create_path_analysis(
    workspace_id: UUID,
    body: _CreateRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
    mv_repo: ModelVersionRepository = Depends(get_model_version_repo),
    md_repo: ModelDataRepository = Depends(get_model_data_repo),
    pa_repo: PathAnalysisRepository = Depends(get_path_analysis_repo),
) -> PathAnalysisResponse | JSONResponse:
    """Compute structural path analysis for an existing run.

    Idempotent: returns 200 with existing analysis if config_hash matches.
    """
    raw = body.config

    # 1. Validate config explicitly (before Pydantic bounds)
    if not (0 <= raw.max_depth <= 12):
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "SPA_INVALID_CONFIG",
                "message": f"max_depth must be in [0, 12], got {raw.max_depth}",
            },
        )
    if not (1 <= raw.top_k <= 100):
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "SPA_INVALID_CONFIG",
                "message": f"top_k must be in [1, 100], got {raw.top_k}",
            },
        )

    config = PathAnalysisConfig(max_depth=raw.max_depth, top_k=raw.top_k)

    # 2. Load run and verify workspace
    snap_row = await snap_repo.get(body.run_id)
    if snap_row is None or snap_row.workspace_id != workspace_id:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": "SPA_RUN_NOT_FOUND",
                "message": f"Run {body.run_id} not found in workspace {workspace_id}.",
            },
        )

    # 3. Idempotency check
    ch = _config_hash(config)
    existing = await pa_repo.get_by_run_and_config_for_workspace(
        body.run_id, ch, workspace_id,
    )
    if existing is not None:
        resp_data = _row_to_response(existing)
        return JSONResponse(
            content=resp_data.model_dump(mode="json"),
            status_code=200,
        )

    # 4. Load model data
    try:
        loaded = await _ensure_model_loaded(
            snap_row.model_version_id, mv_repo, md_repo,
        )
    except HTTPException:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "SPA_MODEL_DATA_UNAVAILABLE",
                "message": (
                    f"Model data for version {snap_row.model_version_id} "
                    "could not be loaded."
                ),
            },
        )

    sector_codes = loaded.sector_codes

    # 5. Load ResultSets and find direct_effect
    result_sets = await rs_repo.get_by_run(body.run_id)
    direct_effect_rs = None
    for rs in result_sets:
        if rs.metric_type == "direct_effect" and rs.series_kind is None:
            direct_effect_rs = rs
            break

    if direct_effect_rs is None:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "SPA_MISSING_DIRECT_EFFECT",
                "message": (
                    f"No direct_effect result set found for run {body.run_id}."
                ),
            },
        )

    delta_d = _reconstruct_delta_d(direct_effect_rs.values, sector_codes)

    # 6. Compute SPA
    try:
        result = compute_spa(
            loaded.A,
            loaded.B,
            delta_d,
            sector_codes,
            max_depth=config.max_depth,
            top_k=config.top_k,
        )
    except SPAConfigError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": exc.message,
            },
        ) from exc
    except SPADimensionError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": exc.reason_code,
                "message": exc.message,
            },
        ) from exc

    # 7. Serialize and persist
    top_paths_json = [
        {
            "source_sector_code": p.source_sector_code,
            "target_sector_code": p.target_sector_code,
            "depth": p.depth,
            "coefficient": p.coefficient,
            "contribution": p.contribution,
        }
        for p in result.top_paths
    ]

    chokepoints_json = [
        {
            "sector_code": c.sector_code,
            "forward_linkage": c.forward_linkage,
            "backward_linkage": c.backward_linkage,
            "norm_forward": c.norm_forward,
            "norm_backward": c.norm_backward,
            "chokepoint_score": c.chokepoint_score,
            "is_chokepoint": c.is_chokepoint,
        }
        for c in result.chokepoints
    ]

    depth_contributions_json = {
        str(k): {"signed": dc.signed, "absolute": dc.absolute}
        for k, dc in result.depth_contributions.items()
    }

    analysis_id = new_uuid7()
    rc = _result_checksum(result)

    row = await pa_repo.create(
        analysis_id=analysis_id,
        run_id=body.run_id,
        workspace_id=workspace_id,
        analysis_version=ANALYSIS_VERSION,
        config_json={"max_depth": config.max_depth, "top_k": config.top_k},
        config_hash=ch,
        max_depth=config.max_depth,
        top_k=config.top_k,
        top_paths_json=top_paths_json,
        chokepoints_json=chokepoints_json,
        depth_contributions_json=depth_contributions_json,
        coverage_ratio=result.coverage_ratio,
        result_checksum=rc,
    )

    return _row_to_response(row)


# ---------------------------------------------------------------------------
# GET /{workspace_id}/path-analytics/{analysis_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/path-analytics/{analysis_id}",
    response_model=PathAnalysisResponse,
)
async def get_path_analysis(
    workspace_id: UUID,
    analysis_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    pa_repo: PathAnalysisRepository = Depends(get_path_analysis_repo),
) -> PathAnalysisResponse:
    """Get a single path analysis by ID (workspace-scoped)."""
    row = await pa_repo.get_for_workspace(analysis_id, workspace_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": "SPA_ANALYSIS_NOT_FOUND",
                "message": f"Analysis {analysis_id} not found in workspace {workspace_id}.",
            },
        )
    return _row_to_response(row)


# ---------------------------------------------------------------------------
# GET /{workspace_id}/path-analytics
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/path-analytics",
    response_model=PathAnalysisListResponse,
)
async def list_path_analyses(
    workspace_id: UUID,
    run_id: UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    pa_repo: PathAnalysisRepository = Depends(get_path_analysis_repo),
) -> PathAnalysisListResponse:
    """List path analyses for a run (workspace-scoped, paginated)."""
    # Verify run exists in workspace
    snap_row = await snap_repo.get(run_id)
    if snap_row is None or snap_row.workspace_id != workspace_id:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": "SPA_RUN_NOT_FOUND",
                "message": f"Run {run_id} not found in workspace {workspace_id}.",
            },
        )

    rows, total = await pa_repo.list_by_run(
        run_id, workspace_id, limit=limit, offset=offset,
    )
    return PathAnalysisListResponse(
        items=[_row_to_response(r) for r in rows],
        total=total,
    )
