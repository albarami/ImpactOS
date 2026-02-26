"""Tests for MappingDecision and MappingLibraryEntry models (MVP-4).

Covers: creation, validation, decision types, confidence bounds.
"""

from uuid import UUID

import pytest
from pydantic import ValidationError
from uuid_extensions import uuid7

from src.models.mapping import (
    DecisionType,
    MappingDecision,
    MappingLibraryEntry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mapping_decision(**overrides: object) -> MappingDecision:
    defaults: dict[str, object] = {
        "line_item_id": uuid7(),
        "suggested_sector_code": "C41",
        "suggested_confidence": 0.92,
        "final_sector_code": "C41",
        "decision_type": DecisionType.APPROVED,
        "decided_by": uuid7(),
    }
    defaults.update(overrides)
    return MappingDecision(**defaults)  # type: ignore[arg-type]


# ===================================================================
# DecisionType enum
# ===================================================================


class TestDecisionType:
    def test_all_types(self) -> None:
        assert DecisionType.APPROVED == "APPROVED"
        assert DecisionType.OVERRIDDEN == "OVERRIDDEN"
        assert DecisionType.DEFERRED == "DEFERRED"
        assert DecisionType.EXCLUDED == "EXCLUDED"


# ===================================================================
# MappingDecision
# ===================================================================


class TestMappingDecision:
    """MappingDecision creation and validation."""

    def test_creation_succeeds(self) -> None:
        md = _make_mapping_decision()
        assert isinstance(md.mapping_decision_id, UUID)
        assert md.final_sector_code == "C41"

    def test_timestamp_generated(self) -> None:
        md = _make_mapping_decision()
        assert md.decided_at is not None
        assert md.decided_at.tzinfo is not None

    def test_confidence_bounds_upper(self) -> None:
        with pytest.raises(ValidationError):
            _make_mapping_decision(suggested_confidence=1.5)

    def test_confidence_bounds_lower(self) -> None:
        with pytest.raises(ValidationError):
            _make_mapping_decision(suggested_confidence=-0.1)

    def test_confidence_can_be_none(self) -> None:
        """Before AI suggestion, confidence is None."""
        md = _make_mapping_decision(
            suggested_sector_code=None,
            suggested_confidence=None,
        )
        assert md.suggested_confidence is None

    def test_decision_note_optional(self) -> None:
        md = _make_mapping_decision(decision_note="Changed to construction sector")
        assert md.decision_note == "Changed to construction sector"

    def test_invalid_decision_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_mapping_decision(decision_type="INVALID")

    def test_final_sector_code_required_for_approved(self) -> None:
        """APPROVED decisions must have a final_sector_code."""
        with pytest.raises(ValidationError, match="final_sector_code"):
            _make_mapping_decision(
                decision_type=DecisionType.APPROVED,
                final_sector_code=None,
            )

    def test_deferred_allows_no_final_sector(self) -> None:
        md = _make_mapping_decision(
            decision_type=DecisionType.DEFERRED,
            final_sector_code=None,
        )
        assert md.final_sector_code is None

    def test_excluded_allows_no_final_sector(self) -> None:
        md = _make_mapping_decision(
            decision_type=DecisionType.EXCLUDED,
            final_sector_code=None,
        )
        assert md.final_sector_code is None


# ===================================================================
# MappingLibraryEntry
# ===================================================================


class TestMappingLibraryEntry:
    """Reusable mapping pattern."""

    def test_creation(self) -> None:
        entry = MappingLibraryEntry(
            pattern="structural steel",
            sector_code="C41",
            confidence=0.95,
        )
        assert entry.pattern == "structural steel"
        assert isinstance(entry.entry_id, UUID)

    def test_confidence_bounded(self) -> None:
        with pytest.raises(ValidationError):
            MappingLibraryEntry(
                pattern="test",
                sector_code="C41",
                confidence=2.0,
            )

    def test_empty_pattern_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MappingLibraryEntry(
                pattern="",
                sector_code="C41",
                confidence=0.9,
            )

    def test_usage_count_default_zero(self) -> None:
        entry = MappingLibraryEntry(
            pattern="concrete works",
            sector_code="F",
            confidence=0.88,
        )
        assert entry.usage_count == 0
