"""Tests for versioned workforce artifacts and WorkforceBridgeRefinement (Task 12)."""

from __future__ import annotations

from uuid import UUID

from src.data.workforce.nationality_classification import (
    ClassificationOverride,
    NationalityClassification,
    NationalityClassificationSet,
    NationalityTier,
)
from src.data.workforce.occupation_bridge import OccupationBridge, OccupationBridgeEntry
from src.data.workforce.unit_registry import QualityConfidence
from src.flywheel.workforce_refinement import (
    NationalityClassificationVersion,
    OccupationBridgeVersion,
    WorkforceBridgeRefinement,
)
from src.models.common import ConstraintConfidence, new_uuid7


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_classification(
    sector_code: str = "F",
    occupation_code: str = "7",
    tier: NationalityTier = NationalityTier.EXPAT_RELIANT,
    current_saudi_pct: float = 0.1,
) -> NationalityClassification:
    return NationalityClassification(
        sector_code=sector_code,
        occupation_code=occupation_code,
        tier=tier,
        current_saudi_pct=current_saudi_pct,
        rationale="Test classification",
        source_confidence=ConstraintConfidence.ESTIMATED,
        quality_confidence=QualityConfidence.MEDIUM,
        sensitivity_range=None,
        source="test",
    )


def _make_classification_set(
    classifications: list[NationalityClassification] | None = None,
) -> NationalityClassificationSet:
    if classifications is None:
        classifications = [
            _make_classification("F", "7"),
            _make_classification("C", "8", NationalityTier.SAUDI_TRAINABLE, 0.3),
            _make_classification("G", "5", NationalityTier.SAUDI_READY, 0.7),
        ]
    return NationalityClassificationSet(
        year=2024,
        classifications=classifications,
    )


def _make_override(
    sector_code: str = "F",
    occupation_code: str = "7",
    original_tier: NationalityTier = NationalityTier.EXPAT_RELIANT,
    override_tier: NationalityTier = NationalityTier.SAUDI_TRAINABLE,
    engagement_id: str = "eng-001",
) -> ClassificationOverride:
    return ClassificationOverride(
        sector_code=sector_code,
        occupation_code=occupation_code,
        original_tier=original_tier,
        override_tier=override_tier,
        overridden_by="analyst_1",
        engagement_id=engagement_id,
        rationale="Updated based on field data",
        timestamp="2024-01-15T10:00:00Z",
    )


def _make_bridge() -> OccupationBridge:
    return OccupationBridge(
        year=2024,
        entries=[
            OccupationBridgeEntry(
                sector_code="F",
                occupation_code="7",
                share=0.6,
                source="test",
                source_confidence=ConstraintConfidence.ESTIMATED,
                quality_confidence=QualityConfidence.MEDIUM,
            ),
            OccupationBridgeEntry(
                sector_code="F",
                occupation_code="8",
                share=0.4,
                source="test",
                source_confidence=ConstraintConfidence.ESTIMATED,
                quality_confidence=QualityConfidence.MEDIUM,
            ),
        ],
        metadata={"source": "test"},
    )


# ---------------------------------------------------------------------------
# OccupationBridgeVersion tests
# ---------------------------------------------------------------------------


class TestOccupationBridgeVersion:
    """OccupationBridgeVersion is frozen and holds bridge data."""

    def test_is_frozen(self) -> None:
        bridge = _make_bridge()
        version = OccupationBridgeVersion(
            version_number=1,
            bridge_data=bridge,
        )
        # Frozen model should reject attribute assignment
        try:
            version.version_number = 2  # type: ignore[misc]
            assert False, "Should have raised an error for frozen model"
        except (AttributeError, TypeError, ValueError):
            pass

    def test_has_required_fields(self) -> None:
        bridge = _make_bridge()
        version = OccupationBridgeVersion(
            version_number=1,
            bridge_data=bridge,
        )
        assert isinstance(version.version_id, UUID)
        assert version.version_number == 1
        assert version.published_at is not None
        assert version.bridge_data is bridge
        assert version.parent_version_id is None

    def test_parent_version_chain(self) -> None:
        bridge = _make_bridge()
        v1 = OccupationBridgeVersion(version_number=1, bridge_data=bridge)
        v2 = OccupationBridgeVersion(
            version_number=2,
            bridge_data=bridge,
            parent_version_id=v1.version_id,
        )
        assert v2.parent_version_id == v1.version_id


# ---------------------------------------------------------------------------
# NationalityClassificationVersion tests
# ---------------------------------------------------------------------------


class TestNationalityClassificationVersion:
    """NationalityClassificationVersion is frozen with overrides tracking."""

    def test_is_frozen(self) -> None:
        cls_set = _make_classification_set()
        version = NationalityClassificationVersion(
            version_number=1,
            classifications=cls_set,
        )
        try:
            version.version_number = 2  # type: ignore[misc]
            assert False, "Should have raised an error for frozen model"
        except (AttributeError, TypeError, ValueError):
            pass

    def test_has_overrides_incorporated(self) -> None:
        cls_set = _make_classification_set()
        override_id_1 = new_uuid7()
        override_id_2 = new_uuid7()
        version = NationalityClassificationVersion(
            version_number=1,
            classifications=cls_set,
            overrides_incorporated=[override_id_1, override_id_2],
        )
        assert version.overrides_incorporated == [override_id_1, override_id_2]

    def test_defaults(self) -> None:
        cls_set = _make_classification_set()
        version = NationalityClassificationVersion(
            version_number=1,
            classifications=cls_set,
        )
        assert version.overrides_incorporated == []
        assert version.parent_version_id is None
        assert isinstance(version.version_id, UUID)
        assert version.published_at is not None


# ---------------------------------------------------------------------------
# WorkforceBridgeRefinement tests
# ---------------------------------------------------------------------------


class TestWorkforceBridgeRefinement:
    """WorkforceBridgeRefinement manages override accumulation and refinement."""

    def test_record_engagement_overrides_accumulates(self) -> None:
        mgr = WorkforceBridgeRefinement()
        eng_id = new_uuid7()
        overrides = [_make_override("F", "7"), _make_override("C", "8")]
        mgr.record_engagement_overrides(eng_id, overrides)
        assert len(mgr.get_all_overrides()) == 2

    def test_get_all_overrides_returns_all_accumulated(self) -> None:
        mgr = WorkforceBridgeRefinement()
        eng_1 = new_uuid7()
        eng_2 = new_uuid7()
        mgr.record_engagement_overrides(eng_1, [_make_override("F", "7")])
        mgr.record_engagement_overrides(eng_2, [_make_override("C", "8")])
        all_overrides = mgr.get_all_overrides()
        assert len(all_overrides) == 2
        sectors = {o.sector_code for o in all_overrides}
        assert sectors == {"F", "C"}

    def test_multiple_engagements_accumulate_independently(self) -> None:
        mgr = WorkforceBridgeRefinement()
        eng_1 = new_uuid7()
        eng_2 = new_uuid7()
        mgr.record_engagement_overrides(eng_1, [_make_override("F", "7")])
        mgr.record_engagement_overrides(
            eng_2,
            [_make_override("C", "8"), _make_override("G", "5")],
        )
        # Total overrides is 3
        assert len(mgr.get_all_overrides()) == 3
        # Each engagement tracked separately via coverage
        coverage = mgr.get_refinement_coverage()
        assert coverage["engagement_count"] == 2

    def test_get_refinement_coverage_correct_engagement_count(self) -> None:
        mgr = WorkforceBridgeRefinement()
        eng_1 = new_uuid7()
        eng_2 = new_uuid7()
        eng_3 = new_uuid7()
        mgr.record_engagement_overrides(eng_1, [_make_override("F", "7")])
        mgr.record_engagement_overrides(eng_2, [_make_override("C", "8")])
        mgr.record_engagement_overrides(eng_3, [_make_override("G", "5")])
        coverage = mgr.get_refinement_coverage()
        assert coverage["engagement_count"] == 3

    def test_get_refinement_coverage_correct_calibrated_count(self) -> None:
        mgr = WorkforceBridgeRefinement()
        eng_id = new_uuid7()
        mgr.record_engagement_overrides(
            eng_id,
            [
                _make_override("F", "7"),
                _make_override("C", "8"),
                _make_override("G", "5"),
            ],
        )
        coverage = mgr.get_refinement_coverage()
        assert coverage["engagement_calibrated_cells"] == 3
        assert coverage["total_cells"] == 3

    def test_build_refined_classifications_applies_overrides(self) -> None:
        mgr = WorkforceBridgeRefinement()
        eng_id = new_uuid7()
        mgr.record_engagement_overrides(
            eng_id,
            [_make_override("F", "7", NationalityTier.EXPAT_RELIANT, NationalityTier.SAUDI_TRAINABLE)],
        )
        base = _make_classification_set()
        refined = mgr.build_refined_classifications(base)
        # The F/7 entry should now be SAUDI_TRAINABLE
        entry = refined.get_tier("F", "7")
        assert entry is not None
        assert entry.tier == NationalityTier.SAUDI_TRAINABLE
        # Unchanged entries remain
        entry_c = refined.get_tier("C", "8")
        assert entry_c is not None
        assert entry_c.tier == NationalityTier.SAUDI_TRAINABLE  # was already trainable

    def test_coverage_increases_after_recording_overrides(self) -> None:
        mgr = WorkforceBridgeRefinement()
        coverage_before = mgr.get_refinement_coverage()
        assert coverage_before["engagement_calibrated_cells"] == 0

        eng_id = new_uuid7()
        mgr.record_engagement_overrides(eng_id, [_make_override("F", "7")])
        coverage_after = mgr.get_refinement_coverage()
        assert coverage_after["engagement_calibrated_cells"] == 1
        assert coverage_after["engagement_calibrated_cells"] > coverage_before["engagement_calibrated_cells"]

    def test_empty_overrides_coverage_all_zeros(self) -> None:
        mgr = WorkforceBridgeRefinement()
        coverage = mgr.get_refinement_coverage()
        assert coverage["total_cells"] == 0
        assert coverage["assumed_cells"] == 0
        assert coverage["engagement_calibrated_cells"] == 0
        assert coverage["engagement_count"] == 0
        assert coverage["cells_by_engagement"] == {}

    def test_duplicate_sector_occupation_from_different_engagements(self) -> None:
        """When two engagements override the same cell, both are recorded."""
        mgr = WorkforceBridgeRefinement()
        eng_1 = new_uuid7()
        eng_2 = new_uuid7()
        mgr.record_engagement_overrides(eng_1, [_make_override("F", "7")])
        mgr.record_engagement_overrides(eng_2, [_make_override("F", "7")])
        # Both overrides are accumulated
        assert len(mgr.get_all_overrides()) == 2
        # But unique cells count should still be 1
        coverage = mgr.get_refinement_coverage()
        assert coverage["engagement_calibrated_cells"] == 1
        assert coverage["engagement_count"] == 2

    def test_cells_by_engagement_in_coverage(self) -> None:
        """Coverage includes per-engagement cell breakdown."""
        mgr = WorkforceBridgeRefinement()
        eng_1 = new_uuid7()
        eng_2 = new_uuid7()
        mgr.record_engagement_overrides(
            eng_1,
            [_make_override("F", "7"), _make_override("C", "8")],
        )
        mgr.record_engagement_overrides(eng_2, [_make_override("G", "5")])
        coverage = mgr.get_refinement_coverage()
        assert eng_1 in coverage["cells_by_engagement"]
        assert eng_2 in coverage["cells_by_engagement"]
        assert len(coverage["cells_by_engagement"][eng_1]) == 2
        assert len(coverage["cells_by_engagement"][eng_2]) == 1
