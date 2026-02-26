"""Engagement lifecycle tracker — MVP-7 Section 15.5.1 / 21.

Create engagement records tied to workspaces, track phase transitions
(data assembly → compilation → review → export), compute cycle time
per phase, compare against baseline targets (2x minimum, 3-5x target).

Deterministic — no LLM calls.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from src.models.common import new_uuid7, utc_now


class EngagementPhase(StrEnum):
    """Engagement lifecycle phases."""

    DATA_ASSEMBLY = "DATA_ASSEMBLY"
    COMPILATION = "COMPILATION"
    REVIEW = "REVIEW"
    EXPORT = "EXPORT"


@dataclass
class PhaseTransition:
    """Record of a phase transition."""

    from_phase: EngagementPhase
    to_phase: EngagementPhase
    timestamp: datetime


@dataclass
class EngagementRecord:
    """Engagement record tied to a workspace."""

    engagement_id: UUID
    workspace_id: UUID
    name: str
    current_phase: EngagementPhase
    phase_transitions: list[PhaseTransition] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class ImprovementAssessment:
    """Assessment of cycle time improvement vs baseline."""

    baseline_hours: float
    actual_hours: float
    improvement_factor: float
    meets_minimum: bool  # >= 2x
    meets_target: bool   # >= 3x
    exceeds_target: bool  # >= 5x


# Gate thresholds per Section 15.5.1
_MINIMUM_IMPROVEMENT = 2.0
_TARGET_IMPROVEMENT = 3.0
_EXCEED_IMPROVEMENT = 5.0


class EngagementTracker:
    """Track engagement lifecycle and compare against baseline targets."""

    def __init__(self) -> None:
        self._store: dict[UUID, EngagementRecord] = {}

    def create(self, *, workspace_id: UUID, name: str) -> EngagementRecord:
        """Create a new engagement record."""
        record = EngagementRecord(
            engagement_id=new_uuid7(),
            workspace_id=workspace_id,
            name=name,
            current_phase=EngagementPhase.DATA_ASSEMBLY,
        )
        self._store[record.engagement_id] = record
        return record

    def get(self, engagement_id: UUID) -> EngagementRecord:
        """Get engagement by ID. Raises KeyError if not found."""
        try:
            return self._store[engagement_id]
        except KeyError:
            raise KeyError(f"Engagement {engagement_id} not found.") from None

    def transition(
        self,
        engagement_id: UUID,
        to_phase: EngagementPhase,
        timestamp: datetime | None = None,
    ) -> EngagementRecord:
        """Record a phase transition."""
        record = self.get(engagement_id)
        ts = timestamp or utc_now()
        record.phase_transitions.append(
            PhaseTransition(
                from_phase=record.current_phase,
                to_phase=to_phase,
                timestamp=ts,
            )
        )
        record.current_phase = to_phase
        return record

    def cycle_times(self, engagement_id: UUID) -> dict[str, float]:
        """Compute cycle time (hours) per phase."""
        record = self.get(engagement_id)
        times: dict[str, float] = {}
        transitions = record.phase_transitions

        for i in range(len(transitions) - 1):
            phase_name = transitions[i].to_phase.value
            start = transitions[i].timestamp
            end = transitions[i + 1].timestamp
            hours = (end - start).total_seconds() / 3600.0
            times[phase_name] = hours

        return times

    def total_cycle_time(self, engagement_id: UUID) -> float:
        """Total cycle time from first to last transition (hours)."""
        record = self.get(engagement_id)
        if len(record.phase_transitions) < 2:
            return 0.0
        first = record.phase_transitions[0].timestamp
        last = record.phase_transitions[-1].timestamp
        return (last - first).total_seconds() / 3600.0

    @staticmethod
    def assess_improvement(
        *,
        baseline_hours: float,
        actual_hours: float,
    ) -> ImprovementAssessment:
        """Compare actual cycle time against baseline targets."""
        if actual_hours <= 0:
            factor = float("inf")
        else:
            factor = baseline_hours / actual_hours

        return ImprovementAssessment(
            baseline_hours=baseline_hours,
            actual_hours=actual_hours,
            improvement_factor=factor,
            meets_minimum=factor >= _MINIMUM_IMPROVEMENT,
            meets_target=factor >= _TARGET_IMPROVEMENT,
            exceeds_target=factor >= _EXCEED_IMPROVEMENT,
        )
