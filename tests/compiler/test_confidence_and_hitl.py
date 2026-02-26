"""Tests for confidence thresholds and HITL bulk operations (MVP-4 Sections 9.5, 11.1).

Covers: HIGH/MEDIUM/LOW classification, bulk-approve, bulk-override,
defer, escalate, audit trail.
"""

import pytest
from uuid_extensions import uuid7

from src.compiler.confidence import (
    ConfidenceBand,
    classify_confidence,
    classify_mappings,
)
from src.compiler.hitl import (
    AuditEntry,
    HITLService,
)
from src.compiler.mapping_state import MappingState, MappingStateMachine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACTOR_ID = uuid7()


def _make_sm_with_suggestion(
    confidence: float = 0.90,
) -> MappingStateMachine:
    """Create a state machine in AI_SUGGESTED state."""
    sm = MappingStateMachine(line_item_id=uuid7())
    sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="AI suggestion")
    return sm


# ===================================================================
# Confidence classification (Section 9.5)
# ===================================================================


class TestConfidenceClassification:
    """HIGH >= 0.85, MEDIUM 0.60-0.85, LOW < 0.60."""

    def test_high_confidence(self) -> None:
        assert classify_confidence(0.90) == ConfidenceBand.HIGH
        assert classify_confidence(0.85) == ConfidenceBand.HIGH
        assert classify_confidence(1.0) == ConfidenceBand.HIGH

    def test_medium_confidence(self) -> None:
        assert classify_confidence(0.70) == ConfidenceBand.MEDIUM
        assert classify_confidence(0.60) == ConfidenceBand.MEDIUM
        assert classify_confidence(0.84) == ConfidenceBand.MEDIUM

    def test_low_confidence(self) -> None:
        assert classify_confidence(0.50) == ConfidenceBand.LOW
        assert classify_confidence(0.0) == ConfidenceBand.LOW
        assert classify_confidence(0.59) == ConfidenceBand.LOW

    def test_classify_list(self) -> None:
        confidences = [0.90, 0.70, 0.40, 0.85, 0.60, 0.30]
        result = classify_mappings(confidences)
        assert result[ConfidenceBand.HIGH] == [0.90, 0.85]
        assert result[ConfidenceBand.MEDIUM] == [0.70, 0.60]
        assert result[ConfidenceBand.LOW] == [0.40, 0.30]


# ===================================================================
# HITL bulk approve
# ===================================================================


class TestBulkApprove:
    """Bulk-approve mappings at or above confidence threshold."""

    def test_bulk_approve_high_confidence(self) -> None:
        machines = [_make_sm_with_suggestion(0.90) for _ in range(5)]
        svc = HITLService()

        entries = svc.bulk_approve(
            state_machines=machines,
            actor=ACTOR_ID,
            rationale="Bulk-approve high confidence",
        )
        for sm in machines:
            assert sm.state == MappingState.APPROVED
        assert len(entries) == 5

    def test_bulk_approve_returns_audit_entries(self) -> None:
        machines = [_make_sm_with_suggestion()]
        svc = HITLService()

        entries = svc.bulk_approve(
            state_machines=machines,
            actor=ACTOR_ID,
            rationale="Bulk approved",
        )
        assert len(entries) == 1
        assert isinstance(entries[0], AuditEntry)
        assert entries[0].action == "BULK_APPROVE"

    def test_bulk_approve_skips_non_suggested(self) -> None:
        """Only AI_SUGGESTED items can be bulk-approved."""
        sm_suggested = _make_sm_with_suggestion()
        sm_unmapped = MappingStateMachine(line_item_id=uuid7())
        svc = HITLService()

        entries = svc.bulk_approve(
            state_machines=[sm_suggested, sm_unmapped],
            actor=ACTOR_ID,
            rationale="test",
        )
        assert sm_suggested.state == MappingState.APPROVED
        assert sm_unmapped.state == MappingState.UNMAPPED
        assert len(entries) == 1


# ===================================================================
# HITL bulk override
# ===================================================================


class TestBulkOverride:
    """Bulk-override: set different sector for multiple items."""

    def test_bulk_override(self) -> None:
        machines = [_make_sm_with_suggestion() for _ in range(3)]
        svc = HITLService()

        entries = svc.bulk_override(
            state_machines=machines,
            actor=ACTOR_ID,
            rationale="Changed to construction sector",
        )
        for sm in machines:
            assert sm.state == MappingState.OVERRIDDEN
        assert len(entries) == 3


# ===================================================================
# HITL defer
# ===================================================================


class TestDefer:
    """Defer items back through manager review."""

    def test_escalate_to_manager(self) -> None:
        sm = _make_sm_with_suggestion()
        svc = HITLService()

        entries = svc.escalate(
            state_machines=[sm],
            actor=ACTOR_ID,
            rationale="Politically sensitive mapping",
        )
        assert sm.state == MappingState.MANAGER_REVIEW
        assert len(entries) == 1
        assert entries[0].action == "ESCALATE"


# ===================================================================
# Audit trail
# ===================================================================


class TestAuditTrail:
    """All HITL operations produce audit entries."""

    def test_audit_entry_has_fields(self) -> None:
        sm = _make_sm_with_suggestion()
        svc = HITLService()

        entries = svc.bulk_approve(
            state_machines=[sm],
            actor=ACTOR_ID,
            rationale="Approved",
        )
        entry = entries[0]
        assert entry.actor == ACTOR_ID
        assert entry.rationale == "Approved"
        assert entry.line_item_id == sm.line_item_id
        assert entry.timestamp is not None
        assert entry.timestamp.tzinfo is not None

    def test_audit_entry_tracks_state_change(self) -> None:
        sm = _make_sm_with_suggestion()
        svc = HITLService()

        entries = svc.bulk_approve(
            state_machines=[sm],
            actor=ACTOR_ID,
            rationale="test",
        )
        assert entries[0].from_state == MappingState.AI_SUGGESTED
        assert entries[0].to_state == MappingState.APPROVED

    def test_unresolved_count(self) -> None:
        """Track how many items remain unresolved."""
        machines = [
            _make_sm_with_suggestion(),
            _make_sm_with_suggestion(),
            MappingStateMachine(line_item_id=uuid7()),  # UNMAPPED
        ]
        svc = HITLService()
        svc.bulk_approve(
            state_machines=[machines[0], machines[1]],
            actor=ACTOR_ID,
            rationale="test",
        )
        unresolved = svc.count_unresolved(machines)
        assert unresolved == 1  # Only the UNMAPPED one
