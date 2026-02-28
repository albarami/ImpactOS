"""FastAPI observability/metrics endpoints — MVP-7.

POST /v1/workspaces/{workspace_id}/metrics                     — record metric
GET  /v1/workspaces/{workspace_id}/metrics/engagement/{id}     — engagement metrics
GET  /v1/workspaces/{workspace_id}/metrics/dashboard           — dashboard (empty)
POST /v1/workspaces/{workspace_id}/metrics/dashboard           — dashboard (data)
POST /v1/workspaces/{workspace_id}/metrics/readiness           — readiness check

S0-4: Workspace-scoped routes.
Deterministic — no LLM calls.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from uuid_extensions import uuid7

from src.api.dependencies import get_metric_event_repo
from src.observability.dashboard import DashboardService, DashboardSummary
from src.observability.health import HealthChecker
from src.observability.metrics import MetricType
from src.repositories.metrics import MetricEventRepository

router = APIRouter(prefix="/v1/workspaces", tags=["metrics"])

# ---------------------------------------------------------------------------
# Stateless services (no DB needed)
# ---------------------------------------------------------------------------

_dashboard_svc = DashboardService()
_health_checker = HealthChecker()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class RecordMetricRequest(BaseModel):
    engagement_id: str
    metric_type: MetricType
    value: float
    unit: str
    actor: str = "system"


class RecordMetricResponse(BaseModel):
    event_id: str
    engagement_id: str
    metric_type: str
    value: float
    unit: str


class MetricEventOut(BaseModel):
    event_id: str
    metric_type: str
    value: float
    unit: str


class EngagementMetricsResponse(BaseModel):
    engagement_id: str
    events: list[MetricEventOut]


class DashboardRequest(BaseModel):
    engagements: list[dict]
    library: dict


class DashboardResponse(BaseModel):
    total_engagements: int
    total_scenarios: int
    avg_scenarios_per_engagement: float
    avg_cycle_time_hours: float
    nff_compliance_rate: float
    avg_claim_support_rate: float
    scenario_throughput: list[int]
    library_mappings: int
    library_assumptions: int
    library_patterns: int


class ReadinessRequest(BaseModel):
    database: bool = False
    object_storage: bool = False
    model_versions_loaded: int = 0
    mapping_library_size: int = 0
    assumption_library_size: int = 0
    pattern_library_size: int = 0


class ReadinessResponse(BaseModel):
    ready: bool
    blocking_reasons: list[str]
    checks: dict[str, bool]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/metrics", status_code=201, response_model=RecordMetricResponse)
async def record_metric(
    workspace_id: UUID,
    body: RecordMetricRequest,
    repo: MetricEventRepository = Depends(get_metric_event_repo),
) -> RecordMetricResponse:
    """Record a metric event."""
    eid = UUID(body.engagement_id)
    event_id = uuid7()
    row = await repo.create(
        event_id=event_id,
        engagement_id=eid,
        metric_type=body.metric_type.value,
        value=body.value,
        unit=body.unit,
    )

    return RecordMetricResponse(
        event_id=str(row.event_id),
        engagement_id=str(row.engagement_id),
        metric_type=row.metric_type,
        value=row.value,
        unit=row.unit,
    )


@router.get(
    "/{workspace_id}/metrics/engagement/{engagement_id}",
    response_model=EngagementMetricsResponse,
)
async def get_engagement_metrics(
    workspace_id: UUID,
    engagement_id: str,
    repo: MetricEventRepository = Depends(get_metric_event_repo),
) -> EngagementMetricsResponse:
    """Get all metric events for an engagement."""
    eid = UUID(engagement_id)
    rows = await repo.get_by_engagement(eid)
    return EngagementMetricsResponse(
        engagement_id=engagement_id,
        events=[
            MetricEventOut(
                event_id=str(r.event_id),
                metric_type=r.metric_type,
                value=r.value,
                unit=r.unit,
            )
            for r in rows
        ],
    )


@router.get("/{workspace_id}/metrics/dashboard", response_model=DashboardResponse)
async def get_dashboard(workspace_id: UUID) -> DashboardResponse:
    """Get dashboard summary with empty data (default)."""
    summary = _dashboard_svc.compute_summary(engagements=[], library={})
    return _summary_to_response(summary)


@router.post("/{workspace_id}/metrics/dashboard", response_model=DashboardResponse)
async def post_dashboard(workspace_id: UUID, body: DashboardRequest) -> DashboardResponse:
    """Get dashboard summary with provided data."""
    summary = _dashboard_svc.compute_summary(
        engagements=body.engagements,
        library=body.library,
    )
    return _summary_to_response(summary)


@router.post("/{workspace_id}/metrics/readiness", response_model=ReadinessResponse)
async def check_readiness(workspace_id: UUID, body: ReadinessRequest) -> ReadinessResponse:
    """Run pilot readiness check against provided dependencies."""
    deps = {
        "database": body.database,
        "object_storage": body.object_storage,
        "model_versions_loaded": body.model_versions_loaded,
        "mapping_library_size": body.mapping_library_size,
        "assumption_library_size": body.assumption_library_size,
        "pattern_library_size": body.pattern_library_size,
    }
    readiness = _health_checker.pilot_readiness(deps)
    return ReadinessResponse(
        ready=readiness.ready,
        blocking_reasons=readiness.blocking_reasons,
        checks=readiness.checks,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summary_to_response(summary: DashboardSummary) -> DashboardResponse:
    return DashboardResponse(
        total_engagements=summary.total_engagements,
        total_scenarios=summary.total_scenarios,
        avg_scenarios_per_engagement=summary.avg_scenarios_per_engagement,
        avg_cycle_time_hours=summary.avg_cycle_time_hours,
        nff_compliance_rate=summary.nff_compliance_rate,
        avg_claim_support_rate=summary.avg_claim_support_rate,
        scenario_throughput=summary.scenario_throughput,
        library_mappings=summary.library_mappings,
        library_assumptions=summary.library_assumptions,
        library_patterns=summary.library_patterns,
    )
