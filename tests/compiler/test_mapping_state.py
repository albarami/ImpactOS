"""Tests for mapping state machine (MVP-4 Section 11.1.1).

State machine: UNMAPPED → AI_SUGGESTED → APPROVED → OVERRIDDEN →
MANAGER_REVIEW → EXCLUDED → LOCKED.
Every transition logs actor, timestamp, and rationale.
"""

from uuid import UUID

import pytest
from uuid_extensions import uuid7

from src.compiler.mapping_state import (
    MappingState,
    MappingStateMachine,
    TransitionLog,
    VALID_MAPPING_TRANSITIONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACTOR_ID = uuid7()
LINE_ITEM_ID = uuid7()


def _make_sm(state: MappingState = MappingState.UNMAPPED) -> MappingStateMachine:
    return MappingStateMachine(line_item_id=LINE_ITEM_ID, state=state)


# ===================================================================
# State enum values
# ===================================================================


class TestMappingStateEnum:
    """All states from Section 11.1.1 exist."""

    def test_all_states(self) -> None:
        assert MappingState.UNMAPPED == "UNMAPPED"
        assert MappingState.AI_SUGGESTED == "AI_SUGGESTED"
        assert MappingState.APPROVED == "APPROVED"
        assert MappingState.OVERRIDDEN == "OVERRIDDEN"
        assert MappingState.MANAGER_REVIEW == "MANAGER_REVIEW"
        assert MappingState.EXCLUDED == "EXCLUDED"
        assert MappingState.LOCKED == "LOCKED"


# ===================================================================
# Valid transitions from Section 11.1.1
# ===================================================================


class TestValidTransitions:
    """Each state allows only the transitions specified in the spec table."""

    def test_unmapped_to_ai_suggested(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="AI suggestion requested")
        assert sm.state == MappingState.AI_SUGGESTED

    def test_unmapped_to_approved(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        sm.transition(MappingState.APPROVED, actor=ACTOR_ID, rationale="Manual map")
        assert sm.state == MappingState.APPROVED

    def test_unmapped_to_excluded(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        sm.transition(MappingState.EXCLUDED, actor=ACTOR_ID, rationale="Out of scope")
        assert sm.state == MappingState.EXCLUDED

    def test_ai_suggested_to_approved(self) -> None:
        sm = _make_sm(MappingState.AI_SUGGESTED)
        sm.transition(MappingState.APPROVED, actor=ACTOR_ID, rationale="Analyst approved")
        assert sm.state == MappingState.APPROVED

    def test_ai_suggested_to_overridden(self) -> None:
        sm = _make_sm(MappingState.AI_SUGGESTED)
        sm.transition(MappingState.OVERRIDDEN, actor=ACTOR_ID, rationale="Different sector chosen")
        assert sm.state == MappingState.OVERRIDDEN

    def test_ai_suggested_to_manager_review(self) -> None:
        sm = _make_sm(MappingState.AI_SUGGESTED)
        sm.transition(MappingState.MANAGER_REVIEW, actor=ACTOR_ID, rationale="Escalated")
        assert sm.state == MappingState.MANAGER_REVIEW

    def test_approved_to_overridden(self) -> None:
        sm = _make_sm(MappingState.APPROVED)
        sm.transition(MappingState.OVERRIDDEN, actor=ACTOR_ID, rationale="Edit")
        assert sm.state == MappingState.OVERRIDDEN

    def test_approved_to_locked(self) -> None:
        sm = _make_sm(MappingState.APPROVED)
        sm.transition(MappingState.LOCKED, actor=ACTOR_ID, rationale="Locked for run")
        assert sm.state == MappingState.LOCKED

    def test_overridden_to_locked(self) -> None:
        sm = _make_sm(MappingState.OVERRIDDEN)
        sm.transition(MappingState.LOCKED, actor=ACTOR_ID, rationale="Locked for run")
        assert sm.state == MappingState.LOCKED

    def test_overridden_to_manager_review(self) -> None:
        sm = _make_sm(MappingState.OVERRIDDEN)
        sm.transition(MappingState.MANAGER_REVIEW, actor=ACTOR_ID, rationale="Dispute")
        assert sm.state == MappingState.MANAGER_REVIEW

    def test_manager_review_to_locked(self) -> None:
        sm = _make_sm(MappingState.MANAGER_REVIEW)
        sm.transition(MappingState.LOCKED, actor=ACTOR_ID, rationale="Manager approved")
        assert sm.state == MappingState.LOCKED

    def test_manager_review_to_ai_suggested(self) -> None:
        sm = _make_sm(MappingState.MANAGER_REVIEW)
        sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="Request new suggestion")
        assert sm.state == MappingState.AI_SUGGESTED

    def test_manager_review_to_overridden(self) -> None:
        sm = _make_sm(MappingState.MANAGER_REVIEW)
        sm.transition(MappingState.OVERRIDDEN, actor=ACTOR_ID, rationale="Manager revised")
        assert sm.state == MappingState.OVERRIDDEN

    def test_excluded_to_unmapped(self) -> None:
        sm = _make_sm(MappingState.EXCLUDED)
        sm.transition(MappingState.UNMAPPED, actor=ACTOR_ID, rationale="Re-included")
        assert sm.state == MappingState.UNMAPPED

    def test_excluded_to_ai_suggested(self) -> None:
        sm = _make_sm(MappingState.EXCLUDED)
        sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="Re-mapped via AI")
        assert sm.state == MappingState.AI_SUGGESTED

    def test_locked_to_approved(self) -> None:
        sm = _make_sm(MappingState.LOCKED)
        sm.transition(MappingState.APPROVED, actor=ACTOR_ID, rationale="Unlocked for edit")
        assert sm.state == MappingState.APPROVED

    def test_locked_to_overridden(self) -> None:
        sm = _make_sm(MappingState.LOCKED)
        sm.transition(MappingState.OVERRIDDEN, actor=ACTOR_ID, rationale="Unlocked for override")
        assert sm.state == MappingState.OVERRIDDEN


# ===================================================================
# Invalid transitions
# ===================================================================


class TestInvalidTransitions:
    """Invalid transitions must raise ValueError."""

    def test_unmapped_to_locked_invalid(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        with pytest.raises(ValueError, match="Cannot transition"):
            sm.transition(MappingState.LOCKED, actor=ACTOR_ID, rationale="skip")

    def test_unmapped_to_overridden_invalid(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        with pytest.raises(ValueError, match="Cannot transition"):
            sm.transition(MappingState.OVERRIDDEN, actor=ACTOR_ID, rationale="skip")

    def test_ai_suggested_to_excluded_invalid(self) -> None:
        sm = _make_sm(MappingState.AI_SUGGESTED)
        with pytest.raises(ValueError, match="Cannot transition"):
            sm.transition(MappingState.EXCLUDED, actor=ACTOR_ID, rationale="skip")

    def test_locked_to_unmapped_invalid(self) -> None:
        sm = _make_sm(MappingState.LOCKED)
        with pytest.raises(ValueError, match="Cannot transition"):
            sm.transition(MappingState.UNMAPPED, actor=ACTOR_ID, rationale="skip")

    def test_excluded_to_locked_invalid(self) -> None:
        sm = _make_sm(MappingState.EXCLUDED)
        with pytest.raises(ValueError, match="Cannot transition"):
            sm.transition(MappingState.LOCKED, actor=ACTOR_ID, rationale="skip")

    def test_self_transition_invalid(self) -> None:
        sm = _make_sm(MappingState.APPROVED)
        with pytest.raises(ValueError, match="Cannot transition"):
            sm.transition(MappingState.APPROVED, actor=ACTOR_ID, rationale="noop")


# ===================================================================
# Audit trail / transition logging
# ===================================================================


class TestTransitionLogging:
    """Every transition logs actor, timestamp, and rationale."""

    def test_log_created_on_transition(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="test")
        assert len(sm.history) == 1

    def test_log_contains_actor(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="test")
        assert sm.history[0].actor == ACTOR_ID

    def test_log_contains_rationale(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="AI requested")
        assert sm.history[0].rationale == "AI requested"

    def test_log_contains_from_and_to_states(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="test")
        log = sm.history[0]
        assert log.from_state == MappingState.UNMAPPED
        assert log.to_state == MappingState.AI_SUGGESTED

    def test_log_has_timestamp(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="test")
        assert sm.history[0].timestamp is not None
        assert sm.history[0].timestamp.tzinfo is not None

    def test_multiple_transitions_accumulate_history(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="step 1")
        sm.transition(MappingState.APPROVED, actor=ACTOR_ID, rationale="step 2")
        sm.transition(MappingState.LOCKED, actor=ACTOR_ID, rationale="step 3")
        assert len(sm.history) == 3

    def test_failed_transition_does_not_log(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        with pytest.raises(ValueError):
            sm.transition(MappingState.LOCKED, actor=ACTOR_ID, rationale="bad")
        assert len(sm.history) == 0

    def test_rationale_required(self) -> None:
        sm = _make_sm(MappingState.UNMAPPED)
        with pytest.raises(ValueError, match="rationale"):
            sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="")
