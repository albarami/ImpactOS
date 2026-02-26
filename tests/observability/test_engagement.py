"""Tests for engagement lifecycle tracker (MVP-7).

Covers: engagement records, phase transitions, cycle time per phase,
comparison against baseline targets (2x minimum, 3-5x target).
"""

from datetime import datetime, timedelta, timezone

import pytest
from uuid_extensions import uuid7

from src.observability.engagement import (
    EngagementPhase,
    EngagementRecord,
    EngagementTracker,
    ImprovementAssessment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORKSPACE_ID = uuid7()


def _utc(day: int = 1, hour: int = 10) -> datetime:
    return datetime(2026, 2, day, hour, 0, tzinfo=timezone.utc)


# ===================================================================
# Engagement creation
# ===================================================================


class TestEngagementCreation:
    """Create engagement records tied to workspaces."""

    def test_create_engagement(self) -> None:
        tracker = EngagementTracker()
        record = tracker.create(
            workspace_id=WORKSPACE_ID,
            name="NEOM Logistics",
        )
        assert isinstance(record, EngagementRecord)
        assert record.workspace_id == WORKSPACE_ID
        assert record.name == "NEOM Logistics"

    def test_engagement_starts_in_data_assembly(self) -> None:
        tracker = EngagementTracker()
        record = tracker.create(workspace_id=WORKSPACE_ID, name="Test")
        assert record.current_phase == EngagementPhase.DATA_ASSEMBLY

    def test_engagement_has_unique_id(self) -> None:
        tracker = EngagementTracker()
        r1 = tracker.create(workspace_id=WORKSPACE_ID, name="A")
        r2 = tracker.create(workspace_id=WORKSPACE_ID, name="B")
        assert r1.engagement_id != r2.engagement_id

    def test_get_engagement(self) -> None:
        tracker = EngagementTracker()
        record = tracker.create(workspace_id=WORKSPACE_ID, name="Test")
        retrieved = tracker.get(record.engagement_id)
        assert retrieved.engagement_id == record.engagement_id

    def test_get_nonexistent_raises(self) -> None:
        tracker = EngagementTracker()
        with pytest.raises(KeyError):
            tracker.get(uuid7())


# ===================================================================
# Phase transitions
# ===================================================================


class TestPhaseTransitions:
    """Track phase transitions through the lifecycle."""

    def test_transition_to_compilation(self) -> None:
        tracker = EngagementTracker()
        record = tracker.create(workspace_id=WORKSPACE_ID, name="Test")
        tracker.transition(record.engagement_id, EngagementPhase.COMPILATION)
        updated = tracker.get(record.engagement_id)
        assert updated.current_phase == EngagementPhase.COMPILATION

    def test_full_lifecycle(self) -> None:
        tracker = EngagementTracker()
        record = tracker.create(workspace_id=WORKSPACE_ID, name="Test")
        eid = record.engagement_id
        tracker.transition(eid, EngagementPhase.COMPILATION)
        tracker.transition(eid, EngagementPhase.REVIEW)
        tracker.transition(eid, EngagementPhase.EXPORT)
        updated = tracker.get(eid)
        assert updated.current_phase == EngagementPhase.EXPORT

    def test_transition_records_timestamp(self) -> None:
        tracker = EngagementTracker()
        record = tracker.create(workspace_id=WORKSPACE_ID, name="Test")
        tracker.transition(record.engagement_id, EngagementPhase.COMPILATION)
        updated = tracker.get(record.engagement_id)
        assert len(updated.phase_transitions) >= 1

    def test_phases_ordered(self) -> None:
        """Phases must follow the defined order."""
        assert EngagementPhase.DATA_ASSEMBLY.value == "DATA_ASSEMBLY"
        assert EngagementPhase.COMPILATION.value == "COMPILATION"
        assert EngagementPhase.REVIEW.value == "REVIEW"
        assert EngagementPhase.EXPORT.value == "EXPORT"


# ===================================================================
# Cycle time computation
# ===================================================================


class TestCycleTime:
    """Compute cycle time per phase."""

    def test_cycle_time_per_phase(self) -> None:
        tracker = EngagementTracker()
        record = tracker.create(workspace_id=WORKSPACE_ID, name="Test")
        eid = record.engagement_id
        tracker.transition(eid, EngagementPhase.COMPILATION, timestamp=_utc(day=1, hour=10))
        tracker.transition(eid, EngagementPhase.REVIEW, timestamp=_utc(day=2, hour=10))
        times = tracker.cycle_times(eid)
        # COMPILATION phase lasted 24 hours
        assert "COMPILATION" in times
        assert times["COMPILATION"] == pytest.approx(24.0, abs=0.1)

    def test_total_cycle_time(self) -> None:
        tracker = EngagementTracker()
        record = tracker.create(workspace_id=WORKSPACE_ID, name="Test")
        eid = record.engagement_id
        tracker.transition(eid, EngagementPhase.COMPILATION, timestamp=_utc(day=1, hour=12))
        tracker.transition(eid, EngagementPhase.REVIEW, timestamp=_utc(day=2, hour=12))
        tracker.transition(eid, EngagementPhase.EXPORT, timestamp=_utc(day=3, hour=12))
        total = tracker.total_cycle_time(eid)
        assert total == pytest.approx(48.0, abs=0.1)


# ===================================================================
# Baseline comparison
# ===================================================================


class TestBaselineComparison:
    """Compare against targets: 2x minimum, 3-5x target."""

    def test_meets_minimum_improvement(self) -> None:
        tracker = EngagementTracker()
        assessment = tracker.assess_improvement(
            baseline_hours=100.0,
            actual_hours=50.0,
        )
        assert assessment.improvement_factor == pytest.approx(2.0)
        assert assessment.meets_minimum is True

    def test_below_minimum(self) -> None:
        tracker = EngagementTracker()
        assessment = tracker.assess_improvement(
            baseline_hours=100.0,
            actual_hours=80.0,
        )
        assert assessment.improvement_factor == pytest.approx(1.25)
        assert assessment.meets_minimum is False

    def test_meets_target(self) -> None:
        tracker = EngagementTracker()
        assessment = tracker.assess_improvement(
            baseline_hours=100.0,
            actual_hours=25.0,
        )
        assert assessment.improvement_factor == pytest.approx(4.0)
        assert assessment.meets_target is True

    def test_exceeds_target(self) -> None:
        tracker = EngagementTracker()
        assessment = tracker.assess_improvement(
            baseline_hours=100.0,
            actual_hours=15.0,
        )
        assert assessment.meets_target is True
        assert assessment.exceeds_target is True

    def test_zero_actual_handled(self) -> None:
        tracker = EngagementTracker()
        assessment = tracker.assess_improvement(
            baseline_hours=100.0,
            actual_hours=0.0,
        )
        assert assessment.meets_target is True
