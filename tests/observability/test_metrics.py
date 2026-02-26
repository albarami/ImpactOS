"""Tests for baseline instrumentation metrics (MVP-7).

Covers: time-motion metrics, scenarios per engagement, data prep time,
mapping throughput (items/hour). Structured MetricEvent storage.
"""

from datetime import datetime, timedelta, timezone

import pytest
from uuid_extensions import uuid7

from src.observability.metrics import (
    MetricEvent,
    MetricType,
    MetricsStore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid7()
ACTOR_ID = uuid7()


def _utc(hour: int = 10, minute: int = 0) -> datetime:
    return datetime(2026, 2, 27, hour, minute, tzinfo=timezone.utc)


# ===================================================================
# MetricEvent creation
# ===================================================================


class TestMetricEvent:
    """Structured metric event recording."""

    def test_create_event(self) -> None:
        event = MetricEvent(
            engagement_id=ENGAGEMENT_ID,
            metric_type=MetricType.SCENARIO_REQUEST_TO_RESULTS,
            value=45.0,
            unit="minutes",
            actor=ACTOR_ID,
        )
        assert event.metric_type == MetricType.SCENARIO_REQUEST_TO_RESULTS
        assert event.value == 45.0

    def test_event_has_timestamp(self) -> None:
        event = MetricEvent(
            engagement_id=ENGAGEMENT_ID,
            metric_type=MetricType.SCENARIO_REQUEST_TO_RESULTS,
            value=45.0,
            unit="minutes",
        )
        assert event.timestamp is not None

    def test_event_has_id(self) -> None:
        e1 = MetricEvent(
            engagement_id=ENGAGEMENT_ID,
            metric_type=MetricType.SCENARIOS_PER_ENGAGEMENT,
            value=5.0,
            unit="count",
        )
        e2 = MetricEvent(
            engagement_id=ENGAGEMENT_ID,
            metric_type=MetricType.SCENARIOS_PER_ENGAGEMENT,
            value=8.0,
            unit="count",
        )
        assert e1.event_id != e2.event_id


# ===================================================================
# MetricType coverage
# ===================================================================


class TestMetricTypes:
    """All required metric types are defined."""

    def test_scenario_request_to_results(self) -> None:
        assert MetricType.SCENARIO_REQUEST_TO_RESULTS is not None

    def test_scenarios_per_engagement(self) -> None:
        assert MetricType.SCENARIOS_PER_ENGAGEMENT is not None

    def test_data_prep_time(self) -> None:
        assert MetricType.DATA_PREP_TIME is not None

    def test_charting_time(self) -> None:
        assert MetricType.CHARTING_TIME is not None

    def test_narrative_time(self) -> None:
        assert MetricType.NARRATIVE_TIME is not None

    def test_mapping_throughput(self) -> None:
        assert MetricType.MAPPING_THROUGHPUT is not None


# ===================================================================
# MetricsStore
# ===================================================================


class TestMetricsStore:
    """In-memory metrics store."""

    def test_record_event(self) -> None:
        store = MetricsStore()
        event = MetricEvent(
            engagement_id=ENGAGEMENT_ID,
            metric_type=MetricType.SCENARIO_REQUEST_TO_RESULTS,
            value=45.0,
            unit="minutes",
        )
        store.record(event)
        assert len(store.get_all()) == 1

    def test_get_by_engagement(self) -> None:
        store = MetricsStore()
        e1 = MetricEvent(engagement_id=ENGAGEMENT_ID, metric_type=MetricType.DATA_PREP_TIME, value=30.0, unit="minutes")
        other_id = uuid7()
        e2 = MetricEvent(engagement_id=other_id, metric_type=MetricType.DATA_PREP_TIME, value=20.0, unit="minutes")
        store.record(e1)
        store.record(e2)
        result = store.get_by_engagement(ENGAGEMENT_ID)
        assert len(result) == 1

    def test_get_by_type(self) -> None:
        store = MetricsStore()
        store.record(MetricEvent(engagement_id=ENGAGEMENT_ID, metric_type=MetricType.DATA_PREP_TIME, value=30.0, unit="minutes"))
        store.record(MetricEvent(engagement_id=ENGAGEMENT_ID, metric_type=MetricType.CHARTING_TIME, value=15.0, unit="minutes"))
        result = store.get_by_type(MetricType.DATA_PREP_TIME)
        assert len(result) == 1

    def test_average_by_type(self) -> None:
        store = MetricsStore()
        store.record(MetricEvent(engagement_id=uuid7(), metric_type=MetricType.SCENARIO_REQUEST_TO_RESULTS, value=40.0, unit="minutes"))
        store.record(MetricEvent(engagement_id=uuid7(), metric_type=MetricType.SCENARIO_REQUEST_TO_RESULTS, value=60.0, unit="minutes"))
        avg = store.average_by_type(MetricType.SCENARIO_REQUEST_TO_RESULTS)
        assert avg == pytest.approx(50.0)

    def test_average_empty_returns_zero(self) -> None:
        store = MetricsStore()
        assert store.average_by_type(MetricType.NARRATIVE_TIME) == 0.0

    def test_mapping_throughput_tracking(self) -> None:
        store = MetricsStore()
        store.record(MetricEvent(
            engagement_id=ENGAGEMENT_ID,
            metric_type=MetricType.MAPPING_THROUGHPUT,
            value=120.0,
            unit="items/hour",
        ))
        events = store.get_by_type(MetricType.MAPPING_THROUGHPUT)
        assert events[0].value == 120.0
        assert events[0].unit == "items/hour"
