"""Tests for learning loop (MVP-8).

Covers: store analyst override pairs, retrieve relevant overrides as
few-shot examples, track suggestion accuracy over time.
"""

import pytest
from uuid_extensions import uuid7

from src.compiler.learning import (
    LearningLoop,
    OverridePair,
    AccuracyMetrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_override(
    suggested: str = "F",
    final: str = "H",
    line_text: str = "transport equipment delivery",
    project_type: str = "logistics",
) -> OverridePair:
    return OverridePair(
        engagement_id=uuid7(),
        line_item_id=uuid7(),
        line_item_text=line_text,
        suggested_sector_code=suggested,
        final_sector_code=final,
        project_type=project_type,
        actor=uuid7(),
    )


# ===================================================================
# Store override pairs
# ===================================================================


class TestStoreOverrides:
    """Store analyst override pairs (suggested → final) with context."""

    def test_store_override(self) -> None:
        loop = LearningLoop()
        pair = _make_override()
        loop.record_override(pair)
        assert loop.total_overrides() == 1

    def test_store_multiple_overrides(self) -> None:
        loop = LearningLoop()
        loop.record_override(_make_override(suggested="F", final="H"))
        loop.record_override(_make_override(suggested="F", final="F"))
        loop.record_override(_make_override(suggested="C", final="F"))
        assert loop.total_overrides() == 3

    def test_override_pair_fields(self) -> None:
        pair = _make_override(suggested="F", final="H", line_text="test item")
        assert pair.suggested_sector_code == "F"
        assert pair.final_sector_code == "H"
        assert pair.line_item_text == "test item"
        assert pair.was_correct is False

    def test_correct_suggestion(self) -> None:
        pair = _make_override(suggested="F", final="F")
        assert pair.was_correct is True


# ===================================================================
# Retrieve relevant overrides as few-shot examples
# ===================================================================


class TestRetrieveExamples:
    """Retrieve relevant overrides for future mapping suggestions."""

    def test_retrieve_by_text_similarity(self) -> None:
        loop = LearningLoop()
        loop.record_override(_make_override(
            suggested="F", final="H",
            line_text="transport equipment delivery",
        ))
        loop.record_override(_make_override(
            suggested="F", final="F",
            line_text="concrete foundation works",
        ))
        examples = loop.get_relevant_examples(
            text="equipment transport services",
            top_k=5,
        )
        assert len(examples) >= 1
        assert examples[0].line_item_text == "transport equipment delivery"

    def test_retrieve_empty(self) -> None:
        loop = LearningLoop()
        examples = loop.get_relevant_examples(text="test", top_k=5)
        assert len(examples) == 0

    def test_top_k_limit(self) -> None:
        loop = LearningLoop()
        for i in range(10):
            loop.record_override(_make_override(
                line_text=f"item type {i} concrete",
            ))
        examples = loop.get_relevant_examples(text="concrete item", top_k=3)
        assert len(examples) <= 3

    def test_retrieve_by_project_type(self) -> None:
        loop = LearningLoop()
        loop.record_override(_make_override(
            line_text="steel works", project_type="construction",
        ))
        loop.record_override(_make_override(
            line_text="steel works", project_type="manufacturing",
        ))
        examples = loop.get_relevant_examples(
            text="steel works",
            project_type="construction",
            top_k=5,
        )
        # Should prefer the matching project type
        assert any(e.project_type == "construction" for e in examples)


# ===================================================================
# Accuracy tracking
# ===================================================================


class TestAccuracyTracking:
    """Track suggestion accuracy over time."""

    def test_accuracy_all_correct(self) -> None:
        loop = LearningLoop()
        loop.record_override(_make_override(suggested="F", final="F"))
        loop.record_override(_make_override(suggested="H", final="H"))
        metrics = loop.compute_accuracy()
        assert metrics.accuracy == pytest.approx(1.0)

    def test_accuracy_none_correct(self) -> None:
        loop = LearningLoop()
        loop.record_override(_make_override(suggested="F", final="H"))
        loop.record_override(_make_override(suggested="C", final="F"))
        metrics = loop.compute_accuracy()
        assert metrics.accuracy == pytest.approx(0.0)

    def test_accuracy_partial(self) -> None:
        loop = LearningLoop()
        loop.record_override(_make_override(suggested="F", final="F"))
        loop.record_override(_make_override(suggested="F", final="H"))
        metrics = loop.compute_accuracy()
        assert metrics.accuracy == pytest.approx(0.5)

    def test_accuracy_empty(self) -> None:
        loop = LearningLoop()
        metrics = loop.compute_accuracy()
        assert metrics.accuracy == 0.0
        assert metrics.total == 0

    def test_accuracy_by_sector(self) -> None:
        loop = LearningLoop()
        loop.record_override(_make_override(suggested="F", final="F"))
        loop.record_override(_make_override(suggested="F", final="H"))
        loop.record_override(_make_override(suggested="H", final="H"))
        by_sector = loop.accuracy_by_sector()
        assert by_sector["F"].accuracy == pytest.approx(0.5)
        assert by_sector["H"].accuracy == pytest.approx(1.0)

    def test_metrics_fields(self) -> None:
        loop = LearningLoop()
        loop.record_override(_make_override(suggested="F", final="F"))
        loop.record_override(_make_override(suggested="F", final="H"))
        metrics = loop.compute_accuracy()
        assert metrics.total == 2
        assert metrics.correct == 1
        assert metrics.incorrect == 1
