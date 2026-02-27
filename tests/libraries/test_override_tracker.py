"""Tests for OverrideTracker (MVP-12).

Wraps existing OverridePair from src/compiler/learning.py.
Computes accuracy, frequency, and promotes to mapping library.
"""

from uuid_extensions import uuid7

from src.compiler.learning import OverridePair
from src.models.libraries import MappingLibraryEntry


def _make_override(
    text: str = "concrete works",
    suggested: str = "C",
    final: str = "F",
) -> OverridePair:
    return OverridePair(
        engagement_id=uuid7(),
        line_item_id=uuid7(),
        line_item_text=text,
        suggested_sector_code=suggested,
        final_sector_code=final,
    )


class TestOverrideTracker:
    def test_compute_accuracy_all_correct(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        overrides = [
            _make_override("text1", "F", "F"),
            _make_override("text2", "C", "C"),
        ]
        tracker = OverrideTracker(overrides)
        report = tracker.compute_accuracy()
        assert report.accuracy_pct == 1.0
        assert report.accepted_count == 2
        assert report.overridden_count == 0

    def test_compute_accuracy_none_correct(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        overrides = [
            _make_override("text1", "C", "F"),
            _make_override("text2", "D", "F"),
        ]
        tracker = OverrideTracker(overrides)
        report = tracker.compute_accuracy()
        assert report.accuracy_pct == 0.0

    def test_compute_accuracy_partial(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        overrides = [
            _make_override("text1", "F", "F"),  # correct
            _make_override("text2", "C", "F"),  # incorrect
            _make_override("text3", "D", "D"),  # correct
            _make_override("text4", "C", "D"),  # incorrect
        ]
        tracker = OverrideTracker(overrides)
        report = tracker.compute_accuracy()
        assert report.accuracy_pct == 0.5

    def test_compute_accuracy_empty(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        tracker = OverrideTracker([])
        report = tracker.compute_accuracy()
        assert report.accuracy_pct == 0.0
        assert report.total_suggestions == 0

    def test_accuracy_by_sector(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        overrides = [
            _make_override("text1", "F", "F"),  # F correct
            _make_override("text2", "F", "C"),  # F incorrect
            _make_override("text3", "C", "C"),  # C correct
        ]
        tracker = OverrideTracker(overrides)
        report = tracker.compute_accuracy()
        assert "F" in report.by_sector
        assert report.by_sector["F"]["accuracy"] == 0.5
        assert report.by_sector["C"]["accuracy"] == 1.0

    def test_get_high_confidence_overrides(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        overrides = [
            _make_override("concrete works", "C", "F"),
            _make_override("concrete works", "C", "F"),
            _make_override("concrete works", "C", "F"),
            _make_override("steel pipes", "D", "C"),
        ]
        tracker = OverrideTracker(overrides)
        hc = tracker.get_high_confidence_overrides(min_count=3)
        assert len(hc) == 1
        assert hc[0][0] == "concrete works"
        assert hc[0][1] == "F"
        assert hc[0][2] == 3

    def test_get_high_confidence_below_threshold(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        overrides = [
            _make_override("concrete works", "C", "F"),
            _make_override("concrete works", "C", "F"),
        ]
        tracker = OverrideTracker(overrides)
        hc = tracker.get_high_confidence_overrides(min_count=3)
        assert len(hc) == 0

    def test_get_override_frequency(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        overrides = [
            _make_override("text1", "C", "F"),
            _make_override("text2", "C", "F"),
            _make_override("text3", "C", "D"),
        ]
        tracker = OverrideTracker(overrides)
        freq = tracker.get_override_frequency()
        assert freq["C"]["F"] == 2
        assert freq["C"]["D"] == 1

    def test_get_override_frequency_empty(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        tracker = OverrideTracker([])
        assert tracker.get_override_frequency() == {}

    def test_promote_to_mapping_library(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        ws = uuid7()
        overrides = [
            _make_override("concrete works", "C", "F"),
            _make_override("concrete works", "C", "F"),
            _make_override("concrete works", "C", "F"),
        ]
        tracker = OverrideTracker(overrides)
        entries = tracker.promote_to_mapping_library(
            min_count=3, workspace_id=ws,
        )
        assert len(entries) == 1
        assert isinstance(entries[0], MappingLibraryEntry)
        assert entries[0].sector_code == "F"
        assert entries[0].workspace_id == ws

    def test_promote_min_count(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        overrides = [
            _make_override("concrete works", "C", "F"),
            _make_override("concrete works", "C", "F"),
        ]
        tracker = OverrideTracker(overrides)
        entries = tracker.promote_to_mapping_library(
            min_count=3, workspace_id=uuid7(),
        )
        assert len(entries) == 0

    def test_promote_empty(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        tracker = OverrideTracker([])
        entries = tracker.promote_to_mapping_library(
            min_count=3, workspace_id=uuid7(),
        )
        assert len(entries) == 0

    def test_promote_correct_confidence(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        overrides = [_make_override("concrete", "C", "F")] * 5
        tracker = OverrideTracker(overrides)
        entries = tracker.promote_to_mapping_library(
            min_count=3, workspace_id=uuid7(),
        )
        assert entries[0].confidence >= 0.85

    def test_promote_workspace_id_set(self) -> None:
        from src.libraries.override_tracker import OverrideTracker

        ws = uuid7()
        overrides = [_make_override("concrete", "C", "F")] * 3
        tracker = OverrideTracker(overrides)
        entries = tracker.promote_to_mapping_library(
            min_count=3, workspace_id=ws,
        )
        assert entries[0].workspace_id == ws
