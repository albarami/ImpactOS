"""FastAPI data quality endpoints — MVP-13.

POST /{workspace_id}/runs/{run_id}/quality              — compute quality summary
GET  /{workspace_id}/runs/{run_id}/quality               — get run quality
GET  /{workspace_id}/quality/freshness                   — get workspace freshness overview
GET  /{workspace_id}/quality                             — get workspace quality overview

Workspace-scoped routes. Deterministic engine code only (no LLM).

All 7 amendments enforced:
1. STRUCTURAL_VALIDITY dimension
2. Input-type-aware DEFAULT_DIMENSION_WEIGHTS
3. mapping_coverage_pct on summary + gate logic
4. Smooth freshness decay
5. summary_version + summary_hash for audit
6. ?force_recompute=true on POST
7. Publication gate modes: PASS / PASS_WITH_WARNINGS / FAIL_REQUIRES_WAIVER
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.dependencies import get_data_quality_repo
from src.engine.data_quality import (
    compute_input_quality,
    compute_run_quality_summary,
    generate_freshness_report,
)
from src.models.common import new_uuid7
from src.repositories.data_quality import DataQualityRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workspaces", tags=["data-quality"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class DataInputSpec(BaseModel):
    """Specification for a single data input to score."""

    input_type: str
    input_data: dict = Field(default_factory=dict)
    reference_data: dict | None = None
    dimension_weights: dict[str, float] | None = None


class FreshnessSourceSpec(BaseModel):
    """Specification for a freshness data source."""

    name: str
    type: str
    last_updated: datetime


class ComputeQualityRequest(BaseModel):
    """Request body for computing run quality summary."""

    base_table_year: int
    current_year: int
    coverage_pct: float = Field(ge=0.0, le=1.0)
    mapping_coverage_pct: float | None = None
    base_table_vintage: str = ""
    inputs: list[DataInputSpec] = Field(default_factory=list)
    freshness_sources: list[FreshnessSourceSpec] = Field(default_factory=list)
    key_gaps: list[str] = Field(default_factory=list)
    key_strengths: list[str] = Field(default_factory=list)


class QualitySummaryResponse(BaseModel):
    """Response for a run quality summary."""

    summary_id: str
    run_id: str
    workspace_id: str
    overall_run_score: float
    overall_run_grade: str
    coverage_pct: float
    mapping_coverage_pct: float | None = None
    publication_gate_pass: bool
    publication_gate_mode: str
    summary_version: str
    summary_hash: str
    key_gaps: list[str]
    key_strengths: list[str]
    recommendation: str
    created_at: str
    payload: dict


class FreshnessOverviewResponse(BaseModel):
    """Response for workspace freshness overview."""

    workspace_id: str
    summaries_count: int
    freshness_reports: list[dict]


class QualityOverviewResponse(BaseModel):
    """Response for workspace quality overview."""

    workspace_id: str
    total_summaries: int
    passing_count: int
    warning_count: int
    failing_count: int
    summaries: list[QualitySummaryResponse]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/runs/{run_id}/quality",
    status_code=201,
    response_model=QualitySummaryResponse,
)
async def compute_quality(
    workspace_id: UUID,
    run_id: UUID,
    body: ComputeQualityRequest,
    force_recompute: bool = Query(
        default=False,
        description="Amendment 6: Delete existing summary and recompute",
    ),
    dq_repo: DataQualityRepository = Depends(get_data_quality_repo),
) -> QualitySummaryResponse:
    """Compute data quality summary for a run.

    Amendment 6: ?force_recompute=true deletes existing and recomputes.
    Otherwise returns 409 if summary already exists.
    """
    # Check for existing
    existing = await dq_repo.get_by_run(run_id)
    if existing is not None:
        if not force_recompute:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Quality summary already exists for run {run_id}. "
                    "Use ?force_recompute=true to replace."
                ),
            )
        await dq_repo.delete_by_run(run_id)

    # Score each input
    input_scores = []
    for inp in body.inputs:
        score = compute_input_quality(
            input_type=inp.input_type,
            input_data=inp.input_data,
            reference_data=inp.reference_data,
            dimension_weights=inp.dimension_weights,
        )
        input_scores.append(score)

    # Build freshness report
    freshness_sources = [
        {
            "name": src.name,
            "type": src.type,
            "last_updated": src.last_updated,
        }
        for src in body.freshness_sources
    ]
    freshness_report = generate_freshness_report(freshness_sources)

    # Compute run quality summary
    summary = compute_run_quality_summary(
        run_id=run_id,
        workspace_id=workspace_id,
        base_table_year=body.base_table_year,
        current_year=body.current_year,
        input_scores=input_scores,
        freshness_report=freshness_report,
        coverage_pct=body.coverage_pct,
        key_gaps=body.key_gaps,
        key_strengths=body.key_strengths,
        mapping_coverage_pct=body.mapping_coverage_pct,
        base_table_vintage=body.base_table_vintage,
    )

    # Persist
    summary_id = new_uuid7()
    payload = summary.model_dump(mode="json")

    row = await dq_repo.save_summary(
        summary_id=summary_id,
        run_id=run_id,
        workspace_id=workspace_id,
        overall_run_score=summary.overall_run_score,
        overall_run_grade=summary.overall_run_grade.value,
        coverage_pct=summary.coverage_pct,
        mapping_coverage_pct=summary.mapping_coverage_pct,
        publication_gate_pass=summary.publication_gate_pass,
        publication_gate_mode=summary.publication_gate_mode.value,
        summary_version=summary.summary_version,
        summary_hash=summary.summary_hash,
        payload=payload,
    )

    return QualitySummaryResponse(
        summary_id=str(row.summary_id),
        run_id=str(row.run_id),
        workspace_id=str(row.workspace_id),
        overall_run_score=row.overall_run_score,
        overall_run_grade=row.overall_run_grade,
        coverage_pct=row.coverage_pct,
        mapping_coverage_pct=row.mapping_coverage_pct,
        publication_gate_pass=row.publication_gate_pass,
        publication_gate_mode=row.publication_gate_mode,
        summary_version=row.summary_version,
        summary_hash=row.summary_hash,
        key_gaps=row.payload.get("key_gaps", []),
        key_strengths=row.payload.get("key_strengths", []),
        recommendation=row.payload.get("recommendation", ""),
        created_at=str(row.created_at),
        payload=row.payload,
    )


@router.get(
    "/{workspace_id}/runs/{run_id}/quality",
    response_model=QualitySummaryResponse,
)
async def get_run_quality(
    workspace_id: UUID,
    run_id: UUID,
    dq_repo: DataQualityRepository = Depends(get_data_quality_repo),
) -> QualitySummaryResponse:
    """Get the quality summary for a specific run."""
    row = await dq_repo.get_by_run(run_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No quality summary found for run {run_id}.",
        )

    return QualitySummaryResponse(
        summary_id=str(row.summary_id),
        run_id=str(row.run_id),
        workspace_id=str(row.workspace_id),
        overall_run_score=row.overall_run_score,
        overall_run_grade=row.overall_run_grade,
        coverage_pct=row.coverage_pct,
        mapping_coverage_pct=row.mapping_coverage_pct,
        publication_gate_pass=row.publication_gate_pass,
        publication_gate_mode=row.publication_gate_mode,
        summary_version=row.summary_version,
        summary_hash=row.summary_hash,
        key_gaps=row.payload.get("key_gaps", []),
        key_strengths=row.payload.get("key_strengths", []),
        recommendation=row.payload.get("recommendation", ""),
        created_at=str(row.created_at),
        payload=row.payload,
    )


@router.get(
    "/{workspace_id}/quality/freshness",
    response_model=FreshnessOverviewResponse,
)
async def get_freshness_overview(
    workspace_id: UUID,
    dq_repo: DataQualityRepository = Depends(get_data_quality_repo),
) -> FreshnessOverviewResponse:
    """Get freshness overview for all runs in a workspace."""
    rows = await dq_repo.get_by_workspace(workspace_id)

    freshness_reports = []
    for row in rows:
        fr = row.payload.get("freshness_report", {})
        freshness_reports.append({
            "run_id": str(row.run_id),
            "overall_freshness": fr.get("overall_freshness", "CURRENT"),
            "stale_count": fr.get("stale_count", 0),
            "expired_count": fr.get("expired_count", 0),
            "checks": fr.get("checks", []),
        })

    return FreshnessOverviewResponse(
        workspace_id=str(workspace_id),
        summaries_count=len(rows),
        freshness_reports=freshness_reports,
    )


@router.get(
    "/{workspace_id}/quality",
    response_model=QualityOverviewResponse,
)
async def get_quality_overview(
    workspace_id: UUID,
    dq_repo: DataQualityRepository = Depends(get_data_quality_repo),
) -> QualityOverviewResponse:
    """Get quality overview for all runs in a workspace."""
    rows = await dq_repo.get_by_workspace(workspace_id)

    passing = 0
    warning = 0
    failing = 0
    summaries = []

    for row in rows:
        mode = row.publication_gate_mode
        if mode == "PASS":
            passing += 1
        elif mode == "PASS_WITH_WARNINGS":
            warning += 1
        else:
            failing += 1

        summaries.append(
            QualitySummaryResponse(
                summary_id=str(row.summary_id),
                run_id=str(row.run_id),
                workspace_id=str(row.workspace_id),
                overall_run_score=row.overall_run_score,
                overall_run_grade=row.overall_run_grade,
                coverage_pct=row.coverage_pct,
                mapping_coverage_pct=row.mapping_coverage_pct,
                publication_gate_pass=row.publication_gate_pass,
                publication_gate_mode=row.publication_gate_mode,
                summary_version=row.summary_version,
                summary_hash=row.summary_hash,
                key_gaps=row.payload.get("key_gaps", []),
                key_strengths=row.payload.get("key_strengths", []),
                recommendation=row.payload.get("recommendation", ""),
                created_at=str(row.created_at),
                payload=row.payload,
            ),
        )

    return QualityOverviewResponse(
        workspace_id=str(workspace_id),
        total_summaries=len(rows),
        passing_count=passing,
        warning_count=warning,
        failing_count=failing,
        summaries=summaries,
    )
