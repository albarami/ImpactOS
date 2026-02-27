"""FastAPI depth engine endpoints — MVP-9.

POST /v1/workspaces/{workspace_id}/depth/plans                          — trigger
GET  /v1/workspaces/{workspace_id}/depth/plans/{plan_id}                — status
GET  /v1/workspaces/{workspace_id}/depth/plans/{plan_id}/artifacts/{step} — artifact
GET  /v1/workspaces/{workspace_id}/depth/plans/{plan_id}/suite          — suite plan

Workspace-scoped routes. Deterministic fallback for RESTRICTED workspaces.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.agents.depth.tasks import dispatch_depth_plan, run_depth_plan
from src.api.dependencies import get_depth_artifact_repo, get_depth_plan_repo
from src.config.settings import get_settings
from src.models.common import DisclosureTier, new_uuid7
from src.models.depth import DepthPlanStatus, DepthStepName
from src.repositories.depth import DepthArtifactRepository, DepthPlanRepository

router = APIRouter(prefix="/v1/workspaces", tags=["depth"])

# ---------------------------------------------------------------------------
# Valid step names for validation
# ---------------------------------------------------------------------------

_VALID_STEPS = {s.value for s in DepthStepName}

# Tier ordering for filtering
_TIER_ORDER = {
    DisclosureTier.TIER0: 0,
    DisclosureTier.TIER1: 1,
    DisclosureTier.TIER2: 2,
}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class TriggerDepthPlanRequest(BaseModel):
    scenario_spec_id: str | None = None
    classification: str = "INTERNAL"
    context: dict = Field(default_factory=dict)


class TriggerDepthPlanResponse(BaseModel):
    plan_id: str
    status: str


class ArtifactSummary(BaseModel):
    step: str
    disclosure_tier: str
    has_payload: bool


class DepthPlanStatusResponse(BaseModel):
    plan_id: str
    workspace_id: str
    status: str
    current_step: str | None = None
    degraded_steps: list[str] = Field(default_factory=list)
    step_errors: dict = Field(default_factory=dict)
    error_message: str | None = None
    artifacts: list[ArtifactSummary] = Field(default_factory=list)


class ArtifactResponse(BaseModel):
    artifact_id: str
    plan_id: str
    step: str
    payload: dict
    disclosure_tier: str
    metadata: dict = Field(default_factory=dict)


class SuitePlanResponse(BaseModel):
    plan_id: str
    suite_plan: dict


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/depth/plans",
    status_code=201,
    response_model=TriggerDepthPlanResponse,
)
async def trigger_depth_plan(
    workspace_id: UUID,
    body: TriggerDepthPlanRequest,
    plan_repo: DepthPlanRepository = Depends(get_depth_plan_repo),
    artifact_repo: DepthArtifactRepository = Depends(get_depth_artifact_repo),
) -> TriggerDepthPlanResponse:
    """Trigger a new depth engine plan.

    Creates plan row (PENDING), then runs sync or dispatches to Celery.
    """
    plan_id = new_uuid7()
    scenario_spec_id = (
        UUID(body.scenario_spec_id)
        if body.scenario_spec_id
        else None
    )

    # Persist plan as PENDING
    await plan_repo.create(
        plan_id=plan_id,
        workspace_id=workspace_id,
        scenario_spec_id=scenario_spec_id,
    )

    settings = get_settings()
    context = dict(body.context)
    context["workspace_id"] = str(workspace_id)

    if settings.CELERY_BROKER_URL:
        # Async mode: dispatch to Celery worker
        dispatch_depth_plan(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=body.classification,
        )
        return TriggerDepthPlanResponse(
            plan_id=str(plan_id),
            status=DepthPlanStatus.PENDING.value,
        )

    # Sync mode (dev/test): run inline
    final_status = await run_depth_plan(
        plan_id=plan_id,
        workspace_id=workspace_id,
        context=context,
        classification=body.classification,
        plan_repo=plan_repo,
        artifact_repo=artifact_repo,
    )

    return TriggerDepthPlanResponse(
        plan_id=str(plan_id),
        status=final_status,
    )


@router.get(
    "/{workspace_id}/depth/plans/{plan_id}",
    response_model=DepthPlanStatusResponse,
)
async def get_depth_plan_status(
    workspace_id: UUID,
    plan_id: UUID,
    max_disclosure_tier: str | None = Query(
        default=None,
        description=(
            "Filter artifacts to this tier and below."
            " TIER0=internal, TIER1=client, TIER2=boardroom."
        ),
    ),
    plan_repo: DepthPlanRepository = Depends(get_depth_plan_repo),
    artifact_repo: DepthArtifactRepository = Depends(get_depth_artifact_repo),
) -> DepthPlanStatusResponse:
    """Get depth plan status and artifact summary."""
    plan = await plan_repo.get(plan_id)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail=f"Depth plan {plan_id} not found.",
        )

    artifacts = await artifact_repo.get_by_plan(plan_id)

    # Filter by disclosure tier if specified
    if max_disclosure_tier:
        max_tier = DisclosureTier(max_disclosure_tier)
        max_order = _TIER_ORDER.get(max_tier, 2)
        artifacts = [
            a for a in artifacts
            if _TIER_ORDER.get(DisclosureTier(a.disclosure_tier), 0) <= max_order
        ]

    artifact_summaries = [
        ArtifactSummary(
            step=a.step,
            disclosure_tier=a.disclosure_tier,
            has_payload=a.payload is not None,
        )
        for a in artifacts
    ]

    return DepthPlanStatusResponse(
        plan_id=str(plan.plan_id),
        workspace_id=str(plan.workspace_id),
        status=plan.status,
        current_step=plan.current_step,
        degraded_steps=plan.degraded_steps or [],
        step_errors=plan.step_errors or {},
        error_message=plan.error_message,
        artifacts=artifact_summaries,
    )


@router.get(
    "/{workspace_id}/depth/plans/{plan_id}/artifacts/{step}",
    response_model=ArtifactResponse,
)
async def get_depth_artifact(
    workspace_id: UUID,
    plan_id: UUID,
    step: str,
    max_disclosure_tier: str | None = Query(
        default=None,
        description="Maximum disclosure tier to return.",
    ),
    plan_repo: DepthPlanRepository = Depends(get_depth_plan_repo),
    artifact_repo: DepthArtifactRepository = Depends(get_depth_artifact_repo),
) -> ArtifactResponse:
    """Get a single depth artifact by step name."""
    if step not in _VALID_STEPS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid step '{step}'."
                f" Valid steps: {sorted(_VALID_STEPS)}"
            ),
        )

    plan = await plan_repo.get(plan_id)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail=f"Depth plan {plan_id} not found.",
        )

    artifact = await artifact_repo.get_by_plan_and_step(plan_id, step)
    if artifact is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Artifact for step '{step}' not found"
                f" in plan {plan_id}."
            ),
        )

    # Disclosure tier filtering
    if max_disclosure_tier:
        max_tier = DisclosureTier(max_disclosure_tier)
        max_order = _TIER_ORDER.get(max_tier, 2)
        art_order = _TIER_ORDER.get(
            DisclosureTier(artifact.disclosure_tier), 0,
        )
        if art_order > max_order:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Artifact tier {artifact.disclosure_tier}"
                    f" exceeds max tier {max_disclosure_tier}."
                ),
            )

    return ArtifactResponse(
        artifact_id=str(artifact.artifact_id),
        plan_id=str(artifact.plan_id),
        step=artifact.step,
        payload=artifact.payload,
        disclosure_tier=artifact.disclosure_tier,
        metadata=artifact.metadata_json or {},
    )


@router.get(
    "/{workspace_id}/depth/plans/{plan_id}/suite",
    response_model=SuitePlanResponse,
)
async def get_depth_suite(
    workspace_id: UUID,
    plan_id: UUID,
    plan_repo: DepthPlanRepository = Depends(get_depth_plan_repo),
    artifact_repo: DepthArtifactRepository = Depends(get_depth_artifact_repo),
) -> SuitePlanResponse:
    """Get the final scenario suite plan (convenience endpoint)."""
    plan = await plan_repo.get(plan_id)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail=f"Depth plan {plan_id} not found.",
        )

    artifact = await artifact_repo.get_by_plan_and_step(
        plan_id, DepthStepName.SUITE_PLANNING.value,
    )
    if artifact is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Suite plan not yet computed for plan {plan_id}."
                f" Current status: {plan.status}."
            ),
        )

    suite_data = artifact.payload.get("suite_plan", artifact.payload)

    return SuitePlanResponse(
        plan_id=str(plan_id),
        suite_plan=suite_data,
    )
