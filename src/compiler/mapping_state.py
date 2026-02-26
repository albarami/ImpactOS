"""Mapping state machine — MVP-4 Section 11.1.1.

Full line-item mapping lifecycle:
UNMAPPED → AI_SUGGESTED → APPROVED → OVERRIDDEN → MANAGER_REVIEW → EXCLUDED → LOCKED

Every transition is validated, logged with actor/timestamp/rationale.
Deterministic — no LLM calls.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from src.models.common import utc_now


class MappingState(StrEnum):
    """Line item mapping states per Section 11.1.1."""

    UNMAPPED = "UNMAPPED"
    AI_SUGGESTED = "AI_SUGGESTED"
    APPROVED = "APPROVED"
    OVERRIDDEN = "OVERRIDDEN"
    MANAGER_REVIEW = "MANAGER_REVIEW"
    EXCLUDED = "EXCLUDED"
    LOCKED = "LOCKED"


# Valid transitions per spec table 11.1.1
VALID_MAPPING_TRANSITIONS: dict[MappingState, frozenset[MappingState]] = {
    MappingState.UNMAPPED: frozenset({
        MappingState.AI_SUGGESTED,
        MappingState.APPROVED,
        MappingState.EXCLUDED,
    }),
    MappingState.AI_SUGGESTED: frozenset({
        MappingState.APPROVED,
        MappingState.OVERRIDDEN,
        MappingState.MANAGER_REVIEW,
    }),
    MappingState.APPROVED: frozenset({
        MappingState.OVERRIDDEN,
        MappingState.LOCKED,
    }),
    MappingState.OVERRIDDEN: frozenset({
        MappingState.LOCKED,
        MappingState.MANAGER_REVIEW,
    }),
    MappingState.MANAGER_REVIEW: frozenset({
        MappingState.LOCKED,
        MappingState.AI_SUGGESTED,
        MappingState.OVERRIDDEN,
    }),
    MappingState.EXCLUDED: frozenset({
        MappingState.UNMAPPED,
        MappingState.AI_SUGGESTED,
    }),
    MappingState.LOCKED: frozenset({
        MappingState.APPROVED,
        MappingState.OVERRIDDEN,
    }),
}


@dataclass(frozen=True)
class TransitionLog:
    """Immutable audit record for a state transition."""

    from_state: MappingState
    to_state: MappingState
    actor: UUID
    rationale: str
    timestamp: datetime


class MappingStateMachine:
    """State machine for a single line item's mapping lifecycle.

    Enforces valid transitions and maintains an immutable audit trail.
    """

    def __init__(self, *, line_item_id: UUID, state: MappingState = MappingState.UNMAPPED) -> None:
        self._line_item_id = line_item_id
        self._state = state
        self._history: list[TransitionLog] = []

    @property
    def line_item_id(self) -> UUID:
        return self._line_item_id

    @property
    def state(self) -> MappingState:
        return self._state

    @property
    def history(self) -> list[TransitionLog]:
        return list(self._history)

    def transition(self, to_state: MappingState, *, actor: UUID, rationale: str) -> None:
        """Attempt a state transition.

        Args:
            to_state: Target state.
            actor: User/system performing the transition.
            rationale: Required explanation for the transition.

        Raises:
            ValueError: If the transition is invalid or rationale is empty.
        """
        if not rationale or not rationale.strip():
            msg = "rationale must not be empty."
            raise ValueError(msg)

        allowed = VALID_MAPPING_TRANSITIONS.get(self._state, frozenset())
        if to_state not in allowed:
            msg = (
                f"Cannot transition from {self._state} to {to_state}. "
                f"Allowed: {sorted(s.value for s in allowed)}."
            )
            raise ValueError(msg)

        log = TransitionLog(
            from_state=self._state,
            to_state=to_state,
            actor=actor,
            rationale=rationale,
            timestamp=utc_now(),
        )

        self._state = to_state
        self._history.append(log)
