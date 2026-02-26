"""Baseline instrumentation metrics — MVP-7 Section 21.

Track and record key time-motion metrics:
- Time from scenario request to first results
- Number of scenarios per engagement
- Time on data prep / charting / narrative
- Mapping throughput (items/hour)

Store as structured MetricEvent objects.
Deterministic — no LLM calls.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from src.models.common import new_uuid7, utc_now


class MetricType(StrEnum):
    """Time-motion metric types per Section 21."""

    SCENARIO_REQUEST_TO_RESULTS = "SCENARIO_REQUEST_TO_RESULTS"
    SCENARIOS_PER_ENGAGEMENT = "SCENARIOS_PER_ENGAGEMENT"
    DATA_PREP_TIME = "DATA_PREP_TIME"
    CHARTING_TIME = "CHARTING_TIME"
    NARRATIVE_TIME = "NARRATIVE_TIME"
    MAPPING_THROUGHPUT = "MAPPING_THROUGHPUT"


@dataclass
class MetricEvent:
    """Structured metric event for time-motion tracking."""

    engagement_id: UUID
    metric_type: MetricType
    value: float
    unit: str
    actor: UUID | None = None
    event_id: UUID = field(default_factory=new_uuid7)
    timestamp: datetime = field(default_factory=utc_now)
    metadata: dict = field(default_factory=dict)


class MetricsStore:
    """In-memory metrics store. Production replaces with PostgreSQL."""

    def __init__(self) -> None:
        self._events: list[MetricEvent] = []

    def record(self, event: MetricEvent) -> None:
        """Record a metric event."""
        self._events.append(event)

    def get_all(self) -> list[MetricEvent]:
        """Get all recorded events."""
        return list(self._events)

    def get_by_engagement(self, engagement_id: UUID) -> list[MetricEvent]:
        """Get events for a specific engagement."""
        return [e for e in self._events if e.engagement_id == engagement_id]

    def get_by_type(self, metric_type: MetricType) -> list[MetricEvent]:
        """Get events of a specific metric type."""
        return [e for e in self._events if e.metric_type == metric_type]

    def average_by_type(self, metric_type: MetricType) -> float:
        """Compute average value for a metric type. Returns 0.0 if empty."""
        events = self.get_by_type(metric_type)
        if not events:
            return 0.0
        return sum(e.value for e in events) / len(events)
