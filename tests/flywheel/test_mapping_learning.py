"""Tests for LearningLoop.extract_new_patterns and update_confidence_scores (Task 6)."""

from __future__ import annotations

import pytest

from src.compiler.learning import LearningLoop, OverridePair
from src.models.common import new_uuid7
from src.models.mapping import MappingLibraryEntry


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_override(
    line_item_text: str = "concrete supply",
    suggested_sector_code: str = "S01",
    final_sector_code: str = "S01",
) -> OverridePair:
    return OverridePair(
        engagement_id=new_uuid7(),
        line_item_id=new_uuid7(),
        line_item_text=line_item_text,
        suggested_sector_code=suggested_sector_code,
        final_sector_code=final_sector_code,
    )


def _make_entry(
    pattern: str = "concrete supply",
    sector_code: str = "S01",
    confidence: float = 0.8,
) -> MappingLibraryEntry:
    return MappingLibraryEntry(
        pattern=pattern,
        sector_code=sector_code,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# extract_new_patterns tests
# ---------------------------------------------------------------------------


class TestExtractNewPatterns:
    """LearningLoop.extract_new_patterns groups overrides and creates entries."""

    def test_groups_by_sector_creates_entries_for_freq_ge_min(self) -> None:
        loop = LearningLoop()
        overrides = [
            _make_override(line_item_text="steel rebar supply", final_sector_code="S02"),
            _make_override(line_item_text="steel rebar delivery", final_sector_code="S02"),
            _make_override(line_item_text="steel rebar supply", final_sector_code="S02"),
        ]
        entries = loop.extract_new_patterns(overrides, existing_library=[], min_frequency=2)
        assert len(entries) == 1
        assert entries[0].sector_code == "S02"

    def test_does_not_duplicate_existing_entries(self) -> None:
        loop = LearningLoop()
        existing = [_make_entry(pattern="steel rebar supply", sector_code="S02")]
        overrides = [
            _make_override(line_item_text="steel rebar supply", final_sector_code="S02"),
            _make_override(line_item_text="steel rebar supply", final_sector_code="S02"),
            _make_override(line_item_text="steel rebar supply", final_sector_code="S02"),
        ]
        entries = loop.extract_new_patterns(overrides, existing_library=existing, min_frequency=2)
        assert len(entries) == 0

    def test_empty_overrides_returns_empty(self) -> None:
        loop = LearningLoop()
        entries = loop.extract_new_patterns(overrides=[], existing_library=[])
        assert entries == []

    def test_confidence_reflects_override_accuracy(self) -> None:
        loop = LearningLoop()
        # 2 correct, 1 incorrect for sector S03
        overrides = [
            _make_override(
                line_item_text="pipe fitting",
                suggested_sector_code="S03",
                final_sector_code="S03",
            ),
            _make_override(
                line_item_text="pipe fitting",
                suggested_sector_code="S03",
                final_sector_code="S03",
            ),
            _make_override(
                line_item_text="pipe fitting",
                suggested_sector_code="S01",
                final_sector_code="S03",
            ),
        ]
        entries = loop.extract_new_patterns(overrides, existing_library=[], min_frequency=2)
        assert len(entries) == 1
        # 2 out of 3 correct for S03 group
        assert entries[0].confidence == pytest.approx(2.0 / 3.0)

    def test_below_min_frequency_not_included(self) -> None:
        loop = LearningLoop()
        overrides = [
            _make_override(line_item_text="unique item", final_sector_code="S99"),
        ]
        entries = loop.extract_new_patterns(overrides, existing_library=[], min_frequency=2)
        assert len(entries) == 0


# ---------------------------------------------------------------------------
# update_confidence_scores tests
# ---------------------------------------------------------------------------


class TestUpdateConfidenceScores:
    """LearningLoop.update_confidence_scores adjusts confidence based on overrides."""

    def test_approved_patterns_get_confidence_increase(self) -> None:
        loop = LearningLoop()
        existing = [_make_entry(pattern="concrete supply", sector_code="S01", confidence=0.6)]
        # All overrides correct for S01 => accuracy = 1.0
        overrides = [
            _make_override(
                line_item_text="concrete supply",
                suggested_sector_code="S01",
                final_sector_code="S01",
            ),
        ]
        updated = loop.update_confidence_scores(overrides, existing)
        # new_confidence = (0.6 + 1.0) / 2 = 0.8
        assert updated[0].confidence == pytest.approx(0.8)

    def test_overridden_patterns_get_confidence_decrease(self) -> None:
        loop = LearningLoop()
        existing = [_make_entry(pattern="concrete supply", sector_code="S01", confidence=0.8)]
        # All overrides incorrect for S01 => accuracy = 0.0
        overrides = [
            _make_override(
                line_item_text="concrete supply",
                suggested_sector_code="S01",
                final_sector_code="S99",
            ),
        ]
        updated = loop.update_confidence_scores(overrides, existing)
        # new_confidence = (0.8 + 0.0) / 2 = 0.4
        assert updated[0].confidence == pytest.approx(0.4)

    def test_no_matching_overrides_unchanged(self) -> None:
        loop = LearningLoop()
        existing = [_make_entry(pattern="concrete supply", sector_code="S01", confidence=0.8)]
        # Overrides target a different sector
        overrides = [
            _make_override(
                line_item_text="steel rebar",
                suggested_sector_code="S99",
                final_sector_code="S99",
            ),
        ]
        updated = loop.update_confidence_scores(overrides, existing)
        assert updated[0].confidence == pytest.approx(0.8)

    def test_returns_new_list_originals_unchanged(self) -> None:
        loop = LearningLoop()
        original = _make_entry(pattern="concrete supply", sector_code="S01", confidence=0.6)
        existing = [original]
        overrides = [
            _make_override(
                line_item_text="concrete supply",
                suggested_sector_code="S01",
                final_sector_code="S01",
            ),
        ]
        updated = loop.update_confidence_scores(overrides, existing)
        # Original should be unchanged
        assert original.confidence == pytest.approx(0.6)
        # Updated should be different object with new confidence
        assert updated[0].confidence == pytest.approx(0.8)
        assert updated[0] is not original
