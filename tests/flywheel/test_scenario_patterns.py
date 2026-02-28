"""Tests for ScenarioPattern model and ScenarioPatternLibrary (Task 9)."""

from __future__ import annotations

from uuid import UUID

import pytest

from src.flywheel.models import ReuseScopeLevel
from src.flywheel.scenario_patterns import ScenarioPattern, ScenarioPatternLibrary
from src.models.common import new_uuid7


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_pattern(
    name: str = "Logistics Zone",
    description: str = "Standard logistics zone pattern",
    typical_sector_shares: dict[str, float] | None = None,
    project_type: str = "logistics_zone",
    sector_focus: str | None = None,
    engagement_count: int = 0,
    confidence: str = "medium",
    typical_import_share: float | None = None,
    typical_local_content: float | None = None,
    typical_duration_years: int | None = None,
) -> ScenarioPattern:
    if typical_sector_shares is None:
        typical_sector_shares = {"F": 0.5, "C": 0.3, "H": 0.2}
    return ScenarioPattern(
        name=name,
        description=description,
        typical_sector_shares=typical_sector_shares,
        project_type=project_type,
        sector_focus=sector_focus,
        engagement_count=engagement_count,
        confidence=confidence,
        typical_import_share=typical_import_share,
        typical_local_content=typical_local_content,
        typical_duration_years=typical_duration_years,
    )


# ---------------------------------------------------------------------------
# ScenarioPattern model tests
# ---------------------------------------------------------------------------


class TestScenarioPatternModel:
    """ScenarioPattern has all required fields including lineage."""

    def test_has_all_fields_including_lineage(self) -> None:
        pattern = _make_pattern()
        # Core fields
        assert isinstance(pattern.pattern_id, UUID)
        assert pattern.name == "Logistics Zone"
        assert pattern.description == "Standard logistics zone pattern"
        assert pattern.typical_sector_shares == {"F": 0.5, "C": 0.3, "H": 0.2}
        assert pattern.project_type == "logistics_zone"
        assert pattern.engagement_count == 0
        assert pattern.confidence == "medium"
        # Lineage fields (Amendment 7)
        assert pattern.contributing_engagement_ids == []
        assert pattern.contributing_scenario_ids == []
        assert pattern.merge_history is None
        # Scope fields (Amendment 1)
        assert pattern.workspace_id is None
        assert pattern.source_engagement_id is None
        assert pattern.reuse_scope == ReuseScopeLevel.WORKSPACE_ONLY
        assert pattern.sanitized_for_promotion is False
        # Optional fields
        assert pattern.sector_share_ranges is None
        assert pattern.typical_phasing is None
        assert pattern.typical_duration_years is None
        assert pattern.typical_import_share is None
        assert pattern.typical_local_content is None
        assert pattern.last_used_at is None
        assert pattern.sector_focus is None

    def test_optional_fields_can_be_set(self) -> None:
        eng_id = new_uuid7()
        scen_id = new_uuid7()
        pattern = ScenarioPattern(
            name="Giga Project",
            description="Large-scale giga project",
            typical_sector_shares={"F": 0.6, "C": 0.4},
            sector_share_ranges={"F": (0.5, 0.7), "C": (0.3, 0.5)},
            typical_phasing={0: 0.1, 1: 0.3, 2: 0.4, 3: 0.2},
            typical_duration_years=4,
            typical_import_share=0.35,
            typical_local_content=0.40,
            project_type="giga_project",
            sector_focus="infrastructure",
            confidence="high",
            contributing_engagement_ids=[eng_id],
            contributing_scenario_ids=[scen_id],
            merge_history=[{"merged_from": str(eng_id), "similarity_score": 0.95}],
        )
        assert pattern.sector_share_ranges == {"F": (0.5, 0.7), "C": (0.3, 0.5)}
        assert pattern.typical_phasing == {0: 0.1, 1: 0.3, 2: 0.4, 3: 0.2}
        assert pattern.typical_duration_years == 4
        assert pattern.typical_import_share == 0.35
        assert pattern.typical_local_content == 0.40
        assert pattern.sector_focus == "infrastructure"
        assert pattern.contributing_engagement_ids == [eng_id]
        assert pattern.contributing_scenario_ids == [scen_id]
        assert len(pattern.merge_history) == 1


# ---------------------------------------------------------------------------
# find_patterns tests
# ---------------------------------------------------------------------------


class TestFindPatterns:
    """find_patterns filters by project_type and/or sector_focus."""

    def test_find_by_project_type(self) -> None:
        lib = ScenarioPatternLibrary()
        p1 = _make_pattern(name="Logistics A", project_type="logistics_zone")
        p2 = _make_pattern(name="Housing A", project_type="housing")
        lib._patterns = [p1, p2]

        result = lib.find_patterns(project_type="logistics_zone")
        assert len(result) == 1
        assert result[0].name == "Logistics A"

    def test_find_by_sector_focus(self) -> None:
        lib = ScenarioPatternLibrary()
        p1 = _make_pattern(name="Infra A", sector_focus="infrastructure")
        p2 = _make_pattern(name="Energy A", sector_focus="energy")
        lib._patterns = [p1, p2]

        result = lib.find_patterns(sector_focus="infrastructure")
        assert len(result) == 1
        assert result[0].name == "Infra A"

    def test_find_no_filter_returns_all(self) -> None:
        lib = ScenarioPatternLibrary()
        p1 = _make_pattern(name="A")
        p2 = _make_pattern(name="B")
        p3 = _make_pattern(name="C")
        lib._patterns = [p1, p2, p3]

        result = lib.find_patterns()
        assert len(result) == 3

    def test_find_with_both_filters(self) -> None:
        lib = ScenarioPatternLibrary()
        p1 = _make_pattern(
            name="Match",
            project_type="logistics_zone",
            sector_focus="infrastructure",
        )
        p2 = _make_pattern(
            name="Wrong type",
            project_type="housing",
            sector_focus="infrastructure",
        )
        p3 = _make_pattern(
            name="Wrong focus",
            project_type="logistics_zone",
            sector_focus="energy",
        )
        lib._patterns = [p1, p2, p3]

        result = lib.find_patterns(
            project_type="logistics_zone", sector_focus="infrastructure"
        )
        assert len(result) == 1
        assert result[0].name == "Match"


# ---------------------------------------------------------------------------
# record_engagement_pattern tests
# ---------------------------------------------------------------------------


class TestRecordEngagementPattern:
    """record_engagement_pattern creates or merges patterns."""

    def test_creates_new_when_no_similar_exists(self) -> None:
        lib = ScenarioPatternLibrary()
        eng_id = new_uuid7()
        scen_id = new_uuid7()

        pattern = lib.record_engagement_pattern(
            engagement_id=eng_id,
            scenario_spec_id=scen_id,
            project_type="logistics_zone",
            sector_shares={"F": 0.5, "C": 0.3, "H": 0.2},
            name="New logistics pattern",
            import_share=0.35,
            local_content=0.40,
            duration_years=3,
        )

        assert pattern.name == "New logistics pattern"
        assert pattern.project_type == "logistics_zone"
        assert pattern.typical_sector_shares == {"F": 0.5, "C": 0.3, "H": 0.2}
        assert pattern.engagement_count == 1
        assert eng_id in pattern.contributing_engagement_ids
        assert scen_id in pattern.contributing_scenario_ids
        assert pattern.typical_import_share == 0.35
        assert pattern.typical_local_content == 0.40
        assert pattern.typical_duration_years == 3
        assert len(lib._patterns) == 1

    def test_merges_when_similarity_above_threshold(self) -> None:
        lib = ScenarioPatternLibrary()
        # Create an existing pattern
        existing = _make_pattern(
            name="Existing logistics",
            project_type="logistics_zone",
            typical_sector_shares={"F": 0.5, "C": 0.3, "H": 0.2},
            engagement_count=1,
        )
        existing.contributing_engagement_ids = [new_uuid7()]
        lib._patterns = [existing]

        eng_id = new_uuid7()
        scen_id = new_uuid7()
        # Very similar sector shares — should merge
        pattern = lib.record_engagement_pattern(
            engagement_id=eng_id,
            scenario_spec_id=scen_id,
            project_type="logistics_zone",
            sector_shares={"F": 0.52, "C": 0.28, "H": 0.2},
        )

        # Should have merged into existing, not created new
        assert len(lib._patterns) == 1
        assert pattern is lib._patterns[0]

    def test_merge_increments_engagement_count(self) -> None:
        lib = ScenarioPatternLibrary()
        existing = _make_pattern(
            project_type="logistics_zone",
            typical_sector_shares={"F": 0.5, "C": 0.3, "H": 0.2},
            engagement_count=3,
        )
        lib._patterns = [existing]

        eng_id = new_uuid7()
        scen_id = new_uuid7()
        pattern = lib.record_engagement_pattern(
            engagement_id=eng_id,
            scenario_spec_id=scen_id,
            project_type="logistics_zone",
            sector_shares={"F": 0.52, "C": 0.28, "H": 0.2},
        )

        assert pattern.engagement_count == 4

    def test_merge_records_merge_history(self) -> None:
        lib = ScenarioPatternLibrary()
        existing = _make_pattern(
            project_type="logistics_zone",
            typical_sector_shares={"F": 0.5, "C": 0.3, "H": 0.2},
            engagement_count=1,
        )
        lib._patterns = [existing]

        eng_id = new_uuid7()
        scen_id = new_uuid7()
        pattern = lib.record_engagement_pattern(
            engagement_id=eng_id,
            scenario_spec_id=scen_id,
            project_type="logistics_zone",
            sector_shares={"F": 0.52, "C": 0.28, "H": 0.2},
        )

        assert pattern.merge_history is not None
        assert len(pattern.merge_history) == 1
        entry = pattern.merge_history[0]
        assert entry["merged_from"] == str(eng_id)
        assert "similarity_score" in entry
        assert "date" in entry

    def test_merge_uses_rolling_average_on_sector_shares(self) -> None:
        lib = ScenarioPatternLibrary()
        existing = _make_pattern(
            project_type="logistics_zone",
            typical_sector_shares={"F": 0.5, "C": 0.3, "H": 0.2},
            engagement_count=1,
        )
        lib._patterns = [existing]

        eng_id = new_uuid7()
        scen_id = new_uuid7()
        # New engagement with different shares
        pattern = lib.record_engagement_pattern(
            engagement_id=eng_id,
            scenario_spec_id=scen_id,
            project_type="logistics_zone",
            sector_shares={"F": 0.6, "C": 0.2, "H": 0.2},
        )

        # Rolling average: (old * count + new) / (count + 1)
        # F: (0.5 * 1 + 0.6) / 2 = 0.55
        # C: (0.3 * 1 + 0.2) / 2 = 0.25
        # H: (0.2 * 1 + 0.2) / 2 = 0.20
        assert pattern.typical_sector_shares["F"] == pytest.approx(0.55)
        assert pattern.typical_sector_shares["C"] == pytest.approx(0.25)
        assert pattern.typical_sector_shares["H"] == pytest.approx(0.20)

    def test_creates_new_when_orthogonal_shares(self) -> None:
        """Completely different sector shares should create a new pattern."""
        lib = ScenarioPatternLibrary()
        existing = _make_pattern(
            project_type="logistics_zone",
            typical_sector_shares={"F": 1.0},
            engagement_count=1,
        )
        lib._patterns = [existing]

        eng_id = new_uuid7()
        scen_id = new_uuid7()
        # Orthogonal — no shared sectors
        pattern = lib.record_engagement_pattern(
            engagement_id=eng_id,
            scenario_spec_id=scen_id,
            project_type="logistics_zone",
            sector_shares={"K": 1.0},
        )

        assert len(lib._patterns) == 2

    def test_auto_generates_name_when_none(self) -> None:
        lib = ScenarioPatternLibrary()
        eng_id = new_uuid7()
        scen_id = new_uuid7()
        pattern = lib.record_engagement_pattern(
            engagement_id=eng_id,
            scenario_spec_id=scen_id,
            project_type="giga_project",
            sector_shares={"F": 0.6, "C": 0.4},
        )
        assert pattern.name  # should be non-empty
        assert "giga_project" in pattern.name


# ---------------------------------------------------------------------------
# suggest_template tests
# ---------------------------------------------------------------------------


class TestSuggestTemplate:
    """suggest_template returns highest engagement_count pattern."""

    def test_returns_highest_engagement_count(self) -> None:
        lib = ScenarioPatternLibrary()
        p1 = _make_pattern(
            name="Low count",
            project_type="logistics_zone",
            engagement_count=2,
        )
        p2 = _make_pattern(
            name="High count",
            project_type="logistics_zone",
            engagement_count=10,
        )
        p3 = _make_pattern(
            name="Mid count",
            project_type="logistics_zone",
            engagement_count=5,
        )
        lib._patterns = [p1, p2, p3]

        result = lib.suggest_template(project_type="logistics_zone")
        assert result is not None
        assert result.name == "High count"

    def test_returns_none_for_unknown_project_type(self) -> None:
        lib = ScenarioPatternLibrary()
        p1 = _make_pattern(project_type="logistics_zone", engagement_count=5)
        lib._patterns = [p1]

        result = lib.suggest_template(project_type="unknown_type")
        assert result is None

    def test_returns_none_when_library_empty(self) -> None:
        lib = ScenarioPatternLibrary()
        result = lib.suggest_template(project_type="logistics_zone")
        assert result is None


# ---------------------------------------------------------------------------
# cosine_similarity tests
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    """_cosine_similarity computes cosine similarity on sparse sector vectors."""

    def test_identical_vectors_return_1(self) -> None:
        a = {"F": 0.5, "C": 0.3, "H": 0.2}
        b = {"F": 0.5, "C": 0.3, "H": 0.2}
        sim = ScenarioPatternLibrary._cosine_similarity(a, b)
        assert sim == pytest.approx(1.0)

    def test_orthogonal_vectors_return_0(self) -> None:
        a = {"F": 1.0}
        b = {"K": 1.0}
        sim = ScenarioPatternLibrary._cosine_similarity(a, b)
        assert sim == pytest.approx(0.0)

    def test_partially_overlapping_vectors(self) -> None:
        a = {"F": 1.0, "C": 0.0}
        b = {"F": 1.0, "K": 1.0}
        # dot = 1*1 = 1
        # |a| = 1.0, |b| = sqrt(2)
        # sim = 1 / sqrt(2) ~ 0.707
        sim = ScenarioPatternLibrary._cosine_similarity(a, b)
        assert sim == pytest.approx(1.0 / (2**0.5))

    def test_empty_vectors_return_0(self) -> None:
        sim = ScenarioPatternLibrary._cosine_similarity({}, {})
        assert sim == pytest.approx(0.0)

    def test_one_empty_vector_returns_0(self) -> None:
        sim = ScenarioPatternLibrary._cosine_similarity({"F": 1.0}, {})
        assert sim == pytest.approx(0.0)
