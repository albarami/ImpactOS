"""FastAPI observability/metrics endpoints — MVP-7.

POST /v1/metrics                         — record metric event
GET  /v1/metrics/engagement/{id}         — engagement metrics
GET  /v1/metrics/dashboard               — dashboard summary (empty data)
POST /v1/metrics/dashboard               — dashboard summary (with data)
POST /v1/metrics/readiness               — pilot readiness check

Deterministic — no LLM calls.
"""

from enum import StrEnum
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from uuid_extensions import uuid7

from src.observability.dashboard import DashboardService, DashboardSummary
from src.observability.health import HealthChecker
from src.observability.metrics import MetricEvent, MetricType, MetricsStore

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])

# ---------------------------------------------------------------------------
# In-memory stores (MVP — replaced by PostgreSQL in production)
# ---------------------------------------------------------------------------

_store = MetricsStore()
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


@router.post("", status_code=201, response_model=RecordMetricResponse)
async def record_metric(body: RecordMetricRequest) -> RecordMetricResponse:
    """Record a metric event."""
    eid = UUID(body.engagement_id)
    event = MetricEvent(
        engagement_id=eid,
        metric_type=body.metric_type,
        value=body.value,
        unit=body.unit,
        actor=body.actor,
    )
    _store.record(event)

    return RecordMetricResponse(
        event_id=str(event.event_id),
        engagement_id=str(event.engagement_id),
        metric_type=event.metric_type.value,
        value=event.value,
        unit=event.unit,
    )


@router.get("/engagement/{engagement_id}", response_model=EngagementMetricsResponse)
async def get_engagement_metrics(engagement_id: str) -> EngagementMetricsResponse:
    """Get all metric events for an engagement."""
    eid = UUID(engagement_id)
    events = _store.get_by_engagement(eid)
    return EngagementMetricsResponse(
        engagement_id=engagement_id,
        events=[
            MetricEventOut(
                event_id=str(e.event_id),
                metric_type=e.metric_type.value,
                value=e.value,
                unit=e.unit,
            )
            for e in events
        ],
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard() -> DashboardResponse:
    """Get dashboard summary with empty data (default)."""
    summary = _dashboard_svc.compute_summary(engagements=[], library={})
    return _summary_to_response(summary)


@router.post("/dashboard", response_model=DashboardResponse)
async def post_dashboard(body: DashboardRequest) -> DashboardResponse:
    """Get dashboard summary with provided data."""
    summary = _dashboard_svc.compute_summary(
        engagements=body.engagements,
        library=body.library,
    )
    return _summary_to_response(summary)


@router.post("/readiness", response_model=ReadinessResponse)
async def check_readiness(body: ReadinessRequest) -> ReadinessResponse:
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
