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
    QualityGrade,
    QualitySeverity,
    QualityWarning,
    RunQualityAssessment,
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


# ===================================================================
# Composite Score
# ===================================================================


def _make_assessment(
    dimension: QualityDimension,
    score: float,
    *,
    applicable: bool = True,
    warnings: list[QualityWarning] | None = None,
) -> DimensionAssessment:
    """Helper to build a DimensionAssessment for composite tests."""
    return DimensionAssessment(
        dimension=dimension,
        score=score,
        applicable=applicable,
        inputs_used={"test": True},
        rules_triggered=["test_rule"],
        warnings=warnings or [],
    )


class TestCompositeScore:
    """composite_score: weighted aggregate with grade and completeness cap."""

    def test_all_perfect(self, scorer: QualityScorer) -> None:
        """7 dimensions all score 1.0 -> composite 1.0, grade A."""
        assessments = [
            _make_assessment(dim, 1.0)
            for dim in QualityDimension
        ]
        result = scorer.composite_score(assessments)

        assert isinstance(result, RunQualityAssessment)
        assert result.composite_score == pytest.approx(1.0)
        assert result.grade == QualityGrade.A

    def test_completeness_cap_below_50(self, scorer: QualityScorer) -> None:
        """3 dims, only 1 applicable (33%) -> grade capped at D."""
        assessments = [
            _make_assessment(QualityDimension.VINTAGE, 1.0, applicable=True),
            _make_assessment(QualityDimension.MAPPING, 0.0, applicable=False),
            _make_assessment(QualityDimension.ASSUMPTIONS, 0.0, applicable=False),
        ]
        result = scorer.composite_score(assessments)

        # completeness = 1/3 * 100 = 33.3%  -> cap at C (< 50%)
        # But the applicable score is 1.0 which would be A.
        # Capped to C.
        assert result.completeness_pct == pytest.approx(100.0 / 3.0)
        assert result.grade == QualityGrade.C

    def test_completeness_cap_below_30(self, scorer: QualityScorer) -> None:
        """10 dims, 2 applicable (20%) -> grade capped at D."""
        # We can only have 7 real dimensions, so use 7 with 2 applicable.
        # 2/7 = 28.6% < 30 -> cap at D.
        dims = list(QualityDimension)
        assessments = [
            _make_assessment(dims[0], 1.0, applicable=True),
            _make_assessment(dims[1], 1.0, applicable=True),
        ] + [
            _make_assessment(dims[i], 0.0, applicable=False)
            for i in range(2, 7)
        ]
        result = scorer.composite_score(assessments)

        # completeness = 2/7 * 100 = 28.6% < 30 -> cap at D
        assert result.completeness_pct == pytest.approx(200.0 / 7.0)
        assert result.grade == QualityGrade.D

    def test_completeness_50_to_100(self, scorer: QualityScorer) -> None:
        """4 dims, 3 applicable (75%) -> no cap."""
        assessments = [
            _make_assessment(QualityDimension.VINTAGE, 1.0, applicable=True),
            _make_assessment(QualityDimension.MAPPING, 1.0, applicable=True),
            _make_assessment(QualityDimension.ASSUMPTIONS, 1.0, applicable=True),
            _make_assessment(QualityDimension.CONSTRAINTS, 0.0, applicable=False),
        ]
        result = scorer.composite_score(assessments)

        # completeness = 3/4 * 100 = 75% -> no cap
        assert result.completeness_pct == pytest.approx(75.0)
        # All applicable score 1.0 -> grade A, no cap applied
        assert result.grade == QualityGrade.A

    def test_grade_b(self, scorer: QualityScorer) -> None:
        """All applicable, scores around 0.7-0.8 -> grade B."""
        assessments = [
            _make_assessment(QualityDimension.VINTAGE, 0.75),
            _make_assessment(QualityDimension.MAPPING, 0.75),
            _make_assessment(QualityDimension.ASSUMPTIONS, 0.75),
            _make_assessment(QualityDimension.CONSTRAINTS, 0.75),
            _make_assessment(QualityDimension.WORKFORCE, 0.75),
            _make_assessment(QualityDimension.PLAUSIBILITY, 0.75),
            _make_assessment(QualityDimension.FRESHNESS, 0.75),
        ]
        result = scorer.composite_score(assessments)

        # Weighted average = 0.75 (all same). 0.75 >= 0.70 -> B
        assert result.composite_score == pytest.approx(0.75)
        assert result.grade == QualityGrade.B

    def test_grade_f(self, scorer: QualityScorer) -> None:
        """All applicable, scores very low -> grade F."""
        assessments = [
            _make_assessment(dim, 0.1)
            for dim in QualityDimension
        ]
        result = scorer.composite_score(assessments)

        # Weighted average = 0.1. 0.1 < 0.40 -> F
        assert result.composite_score == pytest.approx(0.1)
        assert result.grade == QualityGrade.F

    def test_warnings_aggregated(self, scorer: QualityScorer) -> None:
        """Dims with warnings -> all collected in assessment."""
        w1 = QualityWarning(
            dimension=QualityDimension.MAPPING,
            severity=QualitySeverity.WARNING,
            message="mapping warning",
        )
        w2 = QualityWarning(
            dimension=QualityDimension.MAPPING,
            severity=QualitySeverity.CRITICAL,
            message="mapping critical",
        )
        w3 = QualityWarning(
            dimension=QualityDimension.VINTAGE,
            severity=QualitySeverity.INFO,
            message="vintage info",
        )
        assessments = [
            _make_assessment(QualityDimension.MAPPING, 0.8, warnings=[w1, w2]),
            _make_assessment(QualityDimension.VINTAGE, 0.9, warnings=[w3]),
            _make_assessment(QualityDimension.ASSUMPTIONS, 0.7),
        ]
        result = scorer.composite_score(assessments)

        assert len(result.warnings) == 3
        assert result.warning_count == 1
        assert result.critical_count == 1
        assert result.info_count == 1

    def test_assessment_version_defaults_to_1(self, scorer: QualityScorer) -> None:
        """First assessment has version 1."""
        assessments = [
            _make_assessment(QualityDimension.VINTAGE, 0.9),
        ]
        result = scorer.composite_score(assessments)
        assert result.assessment_version == 1

    def test_applicable_dimensions_tracked(self, scorer: QualityScorer) -> None:
        """applicable/assessed/missing lists correct."""
        assessments = [
            _make_assessment(QualityDimension.VINTAGE, 1.0, applicable=True),
            _make_assessment(QualityDimension.MAPPING, 0.8, applicable=True),
            _make_assessment(QualityDimension.CONSTRAINTS, 0.0, applicable=False),
        ]
        result = scorer.composite_score(assessments)

        assert QualityDimension.VINTAGE in result.applicable_dimensions
        assert QualityDimension.MAPPING in result.applicable_dimensions
        assert QualityDimension.CONSTRAINTS not in result.applicable_dimensions

        # assessed = all dimensions that were provided
        assert QualityDimension.VINTAGE in result.assessed_dimensions
        assert QualityDimension.MAPPING in result.assessed_dimensions
        assert QualityDimension.CONSTRAINTS in result.assessed_dimensions

        # missing = dimensions in the full set not provided
        assert QualityDimension.ASSUMPTIONS in result.missing_dimensions
        assert QualityDimension.WORKFORCE in result.missing_dimensions
        assert QualityDimension.PLAUSIBILITY in result.missing_dimensions
        assert QualityDimension.FRESHNESS in result.missing_dimensions

    def test_empty_assessments(self, scorer: QualityScorer) -> None:
        """Empty list -> grade F, composite 0.0."""
        result = scorer.composite_score([])

        assert result.composite_score == pytest.approx(0.0)
        assert result.grade == QualityGrade.F
        assert result.completeness_pct == pytest.approx(0.0)
