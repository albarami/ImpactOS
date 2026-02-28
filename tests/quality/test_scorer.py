"""Tests for QualityScorer — all 7 quality dimensions.

Covers: vintage, mapping, assumptions, constraints, workforce,
plausibility, freshness scoring with provenance verification.

TDD: these tests are written BEFORE the implementation.
"""

from __future__ import annotations

import pytest

from src.quality.config import QualityScoringConfig
from src.quality.models import (
    DimensionAssessment,
    QualityDimension,
    QualitySeverity,
    SourceAge,
    SourceUpdateFrequency,
)
from src.quality.scorer import QualityScorer


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def scorer() -> QualityScorer:
    """Default scorer with standard config."""
    return QualityScorer()


@pytest.fixture
def custom_config() -> QualityScoringConfig:
    """Custom config for testing overrides."""
    return QualityScoringConfig(
        vintage_thresholds=[
            (1, 1.0),
            (3, 0.8),
            (5, 0.5),
            (99, 0.1),
        ],
        freshness_ratio_thresholds=[
            (0.5, 1.0),
            (1.0, 0.8),
            (2.0, 0.5),
            (99.0, 0.1),
        ],
    )


# ===================================================================
# Dimension 1: Vintage
# ===================================================================


class TestScoreVintage:
    """score_vintage: age-based decay from config thresholds."""

    def test_current_year_scores_1(self, scorer: QualityScorer) -> None:
        result = scorer.score_vintage(base_year=2026, current_year=2026)
        assert result.score == 1.0
        assert result.applicable is True
        assert result.dimension == QualityDimension.VINTAGE

    def test_2yr_old_scores_1(self, scorer: QualityScorer) -> None:
        result = scorer.score_vintage(base_year=2024, current_year=2026)
        assert result.score == 1.0

    def test_4yr_old_scores_07(self, scorer: QualityScorer) -> None:
        result = scorer.score_vintage(base_year=2022, current_year=2026)
        assert result.score == 0.7

    def test_7yr_old_scores_04(self, scorer: QualityScorer) -> None:
        result = scorer.score_vintage(base_year=2019, current_year=2026)
        assert result.score == 0.4

    def test_10yr_old_scores_02(self, scorer: QualityScorer) -> None:
        result = scorer.score_vintage(base_year=2016, current_year=2026)
        assert result.score == 0.2

    def test_provenance_populated(self, scorer: QualityScorer) -> None:
        result = scorer.score_vintage(base_year=2022, current_year=2026)
        assert result.inputs_used["base_year"] == 2022
        assert result.inputs_used["current_year"] == 2026
        assert result.inputs_used["age_years"] == 4
        assert len(result.rules_triggered) > 0

    def test_always_applicable(self, scorer: QualityScorer) -> None:
        result = scorer.score_vintage(base_year=2010, current_year=2026)
        assert result.applicable is True

    def test_custom_config_thresholds(self, custom_config: QualityScoringConfig) -> None:
        scorer = QualityScorer(config=custom_config)
        # 1yr old -> first bracket (1, 1.0)
        assert scorer.score_vintage(2025, 2026).score == 1.0
        # 2yr old -> second bracket (3, 0.8)
        assert scorer.score_vintage(2024, 2026).score == 0.8
        # 4yr old -> third bracket (5, 0.5)
        assert scorer.score_vintage(2022, 2026).score == 0.5
        # 10yr old -> last bracket (99, 0.1)
        assert scorer.score_vintage(2016, 2026).score == 0.1

    def test_3yr_old_boundary(self, scorer: QualityScorer) -> None:
        """3yr old: age=3, first bracket where age<=max_age is (4, 0.7)."""
        result = scorer.score_vintage(base_year=2023, current_year=2026)
        assert result.score == 0.7

    def test_rules_triggered_name_reflects_bracket(self, scorer: QualityScorer) -> None:
        result = scorer.score_vintage(base_year=2024, current_year=2026)
        assert any("vintage" in r.lower() for r in result.rules_triggered)


# ===================================================================
# Dimension 2: Mapping
# ===================================================================


class TestScoreMapping:
    """score_mapping: weighted coverage/confidence/residual/unresolved."""

    def test_perfect_score(self, scorer: QualityScorer) -> None:
        result = scorer.score_mapping(
            coverage_pct=1.0,
            confidence_dist={"HIGH": 1.0, "MEDIUM": 0.0, "LOW": 0.0},
            residual_pct=0.0,
            unresolved_pct=0.0,
            unresolved_spend_pct=0.0,
        )
        assert result.score == pytest.approx(1.0)
        assert result.applicable is True
        assert result.dimension == QualityDimension.MAPPING

    def test_low_coverage(self, scorer: QualityScorer) -> None:
        result = scorer.score_mapping(
            coverage_pct=0.5,
            confidence_dist={"HIGH": 1.0, "MEDIUM": 0.0, "LOW": 0.0},
            residual_pct=0.0,
            unresolved_pct=0.0,
            unresolved_spend_pct=0.0,
        )
        # 0.4*0.5 + 0.3*1.0 + 0.2*1.0 + 0.1*1.0 = 0.2 + 0.3 + 0.2 + 0.1 = 0.8
        assert result.score == pytest.approx(0.8)

    def test_mixed_confidence(self, scorer: QualityScorer) -> None:
        result = scorer.score_mapping(
            coverage_pct=0.8,
            confidence_dist={"HIGH": 0.5, "MEDIUM": 0.3, "LOW": 0.2},
            residual_pct=0.1,
            unresolved_pct=0.05,
            unresolved_spend_pct=0.0,
        )
        # 0.4*0.8 + 0.3*0.5 + 0.2*(1-0.1) + 0.1*(1-0.05)
        # = 0.32 + 0.15 + 0.18 + 0.095 = 0.745
        assert result.score == pytest.approx(0.745)

    def test_materiality_waiver_required_above_5pct(self, scorer: QualityScorer) -> None:
        result = scorer.score_mapping(
            coverage_pct=0.9,
            confidence_dist={"HIGH": 0.8, "MEDIUM": 0.2, "LOW": 0.0},
            residual_pct=0.05,
            unresolved_pct=0.05,
            unresolved_spend_pct=6.0,
        )
        severities = [w.severity for w in result.warnings]
        assert QualitySeverity.WAIVER_REQUIRED in severities

    def test_materiality_critical_above_1pct(self, scorer: QualityScorer) -> None:
        result = scorer.score_mapping(
            coverage_pct=0.9,
            confidence_dist={"HIGH": 0.8, "MEDIUM": 0.2, "LOW": 0.0},
            residual_pct=0.05,
            unresolved_pct=0.05,
            unresolved_spend_pct=2.5,
        )
        severities = [w.severity for w in result.warnings]
        assert QualitySeverity.CRITICAL in severities

    def test_materiality_warning_any_unresolved(self, scorer: QualityScorer) -> None:
        result = scorer.score_mapping(
            coverage_pct=0.95,
            confidence_dist={"HIGH": 0.9, "MEDIUM": 0.1, "LOW": 0.0},
            residual_pct=0.02,
            unresolved_pct=0.01,
            unresolved_spend_pct=0.5,
        )
        severities = [w.severity for w in result.warnings]
        assert QualitySeverity.WARNING in severities

    def test_no_warning_zero_spend(self, scorer: QualityScorer) -> None:
        result = scorer.score_mapping(
            coverage_pct=1.0,
            confidence_dist={"HIGH": 1.0, "MEDIUM": 0.0, "LOW": 0.0},
            residual_pct=0.0,
            unresolved_pct=0.0,
            unresolved_spend_pct=0.0,
        )
        assert len(result.warnings) == 0

    def test_provenance(self, scorer: QualityScorer) -> None:
        result = scorer.score_mapping(
            coverage_pct=0.9,
            confidence_dist={"HIGH": 0.7, "MEDIUM": 0.2, "LOW": 0.1},
            residual_pct=0.05,
            unresolved_pct=0.03,
            unresolved_spend_pct=0.0,
        )
        assert result.inputs_used["coverage_pct"] == 0.9
        assert result.inputs_used["residual_pct"] == 0.05
        assert result.inputs_used["unresolved_pct"] == 0.03
        assert result.inputs_used["unresolved_spend_pct"] == 0.0
        assert "confidence_dist" in result.inputs_used
        assert len(result.rules_triggered) > 0


# ===================================================================
# Dimension 3: Assumptions
# ===================================================================


class TestScoreAssumptions:
    """score_assumptions: ranges_coverage + approval_rate blend."""

    def test_perfect_score(self, scorer: QualityScorer) -> None:
        result = scorer.score_assumptions(
            ranges_coverage_pct=1.0,
            approval_rate=1.0,
        )
        assert result.score == pytest.approx(1.0)
        assert result.applicable is True
        assert result.dimension == QualityDimension.ASSUMPTIONS

    def test_partial_score(self, scorer: QualityScorer) -> None:
        result = scorer.score_assumptions(
            ranges_coverage_pct=0.6,
            approval_rate=0.8,
        )
        # 0.5*0.6 + 0.5*0.8 = 0.3 + 0.4 = 0.7
        assert result.score == pytest.approx(0.7)

    def test_zero_score(self, scorer: QualityScorer) -> None:
        result = scorer.score_assumptions(
            ranges_coverage_pct=0.0,
            approval_rate=0.0,
        )
        assert result.score == pytest.approx(0.0)

    def test_provenance(self, scorer: QualityScorer) -> None:
        result = scorer.score_assumptions(
            ranges_coverage_pct=0.8,
            approval_rate=0.9,
        )
        assert result.inputs_used["ranges_coverage_pct"] == 0.8
        assert result.inputs_used["approval_rate"] == 0.9
        assert len(result.rules_triggered) > 0

    def test_always_applicable(self, scorer: QualityScorer) -> None:
        result = scorer.score_assumptions(0.0, 0.0)
        assert result.applicable is True


# ===================================================================
# Dimension 4: Constraints
# ===================================================================


class TestScoreConstraints:
    """score_constraints: weighted confidence mix."""

    def test_all_hard_scores_1(self, scorer: QualityScorer) -> None:
        result = scorer.score_constraints(
            confidence_summary={"HARD": 10, "ESTIMATED": 0, "ASSUMED": 0},
        )
        assert result.score == pytest.approx(1.0)
        assert result.applicable is True
        assert result.dimension == QualityDimension.CONSTRAINTS

    def test_mixed_bag(self, scorer: QualityScorer) -> None:
        result = scorer.score_constraints(
            confidence_summary={"HARD": 5, "ESTIMATED": 3, "ASSUMED": 2},
        )
        # (5*1.0 + 3*0.6 + 2*0.3) / 10 = (5.0 + 1.8 + 0.6) / 10 = 0.74
        assert result.score == pytest.approx(0.74)

    def test_none_not_applicable(self, scorer: QualityScorer) -> None:
        result = scorer.score_constraints(confidence_summary=None)
        assert result.applicable is False
        assert result.score == 0.0

    def test_empty_dict(self, scorer: QualityScorer) -> None:
        result = scorer.score_constraints(confidence_summary={})
        assert result.applicable is False
        assert result.score == 0.0

    def test_provenance(self, scorer: QualityScorer) -> None:
        result = scorer.score_constraints(
            confidence_summary={"HARD": 5, "ESTIMATED": 3, "ASSUMED": 2},
        )
        assert result.inputs_used["confidence_summary"] == {
            "HARD": 5,
            "ESTIMATED": 3,
            "ASSUMED": 2,
        }

    def test_all_estimated(self, scorer: QualityScorer) -> None:
        result = scorer.score_constraints(
            confidence_summary={"HARD": 0, "ESTIMATED": 10, "ASSUMED": 0},
        )
        assert result.score == pytest.approx(0.6)

    def test_all_assumed(self, scorer: QualityScorer) -> None:
        result = scorer.score_constraints(
            confidence_summary={"HARD": 0, "ESTIMATED": 0, "ASSUMED": 10},
        )
        assert result.score == pytest.approx(0.3)


# ===================================================================
# Dimension 5: Workforce
# ===================================================================


class TestScoreWorkforce:
    """score_workforce: maps confidence label to score."""

    def test_high_scores_1(self, scorer: QualityScorer) -> None:
        result = scorer.score_workforce(overall_confidence="HIGH")
        assert result.score == pytest.approx(1.0)
        assert result.applicable is True
        assert result.dimension == QualityDimension.WORKFORCE

    def test_medium_scores_06(self, scorer: QualityScorer) -> None:
        result = scorer.score_workforce(overall_confidence="MEDIUM")
        assert result.score == pytest.approx(0.6)
        assert result.applicable is True

    def test_low_scores_03(self, scorer: QualityScorer) -> None:
        result = scorer.score_workforce(overall_confidence="LOW")
        assert result.score == pytest.approx(0.3)
        assert result.applicable is True

    def test_none_not_applicable(self, scorer: QualityScorer) -> None:
        result = scorer.score_workforce(overall_confidence=None)
        assert result.applicable is False
        assert result.score == 0.0

    def test_provenance(self, scorer: QualityScorer) -> None:
        result = scorer.score_workforce(overall_confidence="HIGH")
        assert result.inputs_used["overall_confidence"] == "HIGH"


# ===================================================================
# Dimension 6: Plausibility
# ===================================================================


class TestScorePlausibility:
    """score_plausibility: multipliers in range percentage."""

    def test_100_pct_scores_1(self, scorer: QualityScorer) -> None:
        result = scorer.score_plausibility(
            multipliers_in_range_pct=100.0,
            flagged_count=0,
        )
        assert result.score == pytest.approx(1.0)
        assert result.applicable is True
        assert result.dimension == QualityDimension.PLAUSIBILITY

    def test_75_pct_scores_075(self, scorer: QualityScorer) -> None:
        result = scorer.score_plausibility(
            multipliers_in_range_pct=75.0,
            flagged_count=3,
        )
        assert result.score == pytest.approx(0.75)

    def test_0_pct_scores_0(self, scorer: QualityScorer) -> None:
        result = scorer.score_plausibility(
            multipliers_in_range_pct=0.0,
            flagged_count=10,
        )
        assert result.score == pytest.approx(0.0)

    def test_flagged_count_tracked(self, scorer: QualityScorer) -> None:
        result = scorer.score_plausibility(
            multipliers_in_range_pct=80.0,
            flagged_count=5,
        )
        assert result.inputs_used["flagged_count"] == 5
        assert result.inputs_used["multipliers_in_range_pct"] == 80.0

    def test_always_applicable(self, scorer: QualityScorer) -> None:
        result = scorer.score_plausibility(0.0, 0)
        assert result.applicable is True


# ===================================================================
# Dimension 7: Freshness
# ===================================================================


class TestScoreFreshness:
    """score_freshness: ratio-based staleness across data sources."""

    def test_all_fresh_ratio_le_1(self, scorer: QualityScorer) -> None:
        sources = [
            SourceAge("GASTAT IO", 300.0, SourceUpdateFrequency.ANNUAL),
            SourceAge("Labor Force", 80.0, SourceUpdateFrequency.QUARTERLY),
        ]
        result = scorer.score_freshness(source_ages=sources)
        assert result.score == pytest.approx(1.0)
        assert result.applicable is True
        assert result.dimension == QualityDimension.FRESHNESS

    def test_stale_ratio_gt_2(self, scorer: QualityScorer) -> None:
        sources = [
            SourceAge("Old Table", 800.0, SourceUpdateFrequency.ANNUAL),
        ]
        result = scorer.score_freshness(source_ages=sources)
        # ratio = 800/365 ~ 2.19 -> bracket (99.0, 0.2)
        assert result.score == pytest.approx(0.2)

    def test_cadence_aware_5yr_6yr_old(self, scorer: QualityScorer) -> None:
        """5yr cadence, 6yr old -> ratio = 6*365/1825 = 1.2 -> bracket (1.5, 0.7)."""
        sources = [
            SourceAge(
                "Census",
                6 * 365.0,
                SourceUpdateFrequency.QUINQUENNIAL,
            ),
        ]
        result = scorer.score_freshness(source_ages=sources)
        # ratio = 2190/1825 = 1.2 -> (1.5, 0.7)
        assert result.score == pytest.approx(0.7)

    def test_per_engagement_excluded(self, scorer: QualityScorer) -> None:
        sources = [
            SourceAge("BoQ Upload", 500.0, SourceUpdateFrequency.PER_ENGAGEMENT),
            SourceAge("Fresh Annual", 100.0, SourceUpdateFrequency.ANNUAL),
        ]
        result = scorer.score_freshness(source_ages=sources)
        # Only Fresh Annual counted: 100/365 ~ 0.27 -> (1.0, 1.0)
        assert result.score == pytest.approx(1.0)

    def test_mixed_sources_averaged(self, scorer: QualityScorer) -> None:
        sources = [
            SourceAge("Fresh", 100.0, SourceUpdateFrequency.ANNUAL),  # ratio 0.27 -> 1.0
            SourceAge("Stale", 800.0, SourceUpdateFrequency.ANNUAL),  # ratio 2.19 -> 0.2
        ]
        result = scorer.score_freshness(source_ages=sources)
        # average: (1.0 + 0.2) / 2 = 0.6
        assert result.score == pytest.approx(0.6)

    def test_no_time_scored_not_applicable(self, scorer: QualityScorer) -> None:
        sources = [
            SourceAge("BoQ Upload", 500.0, SourceUpdateFrequency.PER_ENGAGEMENT),
        ]
        result = scorer.score_freshness(source_ages=sources)
        assert result.applicable is False
        assert result.score == 0.0

    def test_empty_list_not_applicable(self, scorer: QualityScorer) -> None:
        result = scorer.score_freshness(source_ages=[])
        assert result.applicable is False
        assert result.score == 0.0

    def test_provenance_has_source_ratios(self, scorer: QualityScorer) -> None:
        sources = [
            SourceAge("GASTAT IO", 400.0, SourceUpdateFrequency.ANNUAL),
        ]
        result = scorer.score_freshness(source_ages=sources)
        assert "source_ratios" in result.inputs_used
        ratios = result.inputs_used["source_ratios"]
        assert isinstance(ratios, list)
        assert len(ratios) == 1
        assert ratios[0]["source_name"] == "GASTAT IO"
        assert "ratio" in ratios[0]

    def test_custom_freshness_config(
        self, custom_config: QualityScoringConfig
    ) -> None:
        scorer = QualityScorer(config=custom_config)
        # ratio = 400/365 ~ 1.096 -> custom bracket (2.0, 0.5) since >1.0
        sources = [
            SourceAge("GASTAT IO", 400.0, SourceUpdateFrequency.ANNUAL),
        ]
        result = scorer.score_freshness(source_ages=sources)
        assert result.score == pytest.approx(0.5)

    def test_biennial_cadence(self, scorer: QualityScorer) -> None:
        """Biennial = 730 days. 800 day old source -> ratio = 800/730 ~ 1.096 -> (1.5, 0.7)."""
        sources = [
            SourceAge("Biennial Report", 800.0, SourceUpdateFrequency.BIENNIAL),
        ]
        result = scorer.score_freshness(source_ages=sources)
        assert result.score == pytest.approx(0.7)

    def test_triennial_cadence(self, scorer: QualityScorer) -> None:
        """Triennial = 1095 days. 1000 day old -> ratio ~0.91 -> (1.0, 1.0)."""
        sources = [
            SourceAge("Tri Report", 1000.0, SourceUpdateFrequency.TRIENNIAL),
        ]
        result = scorer.score_freshness(source_ages=sources)
        assert result.score == pytest.approx(1.0)
