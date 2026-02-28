"""Tests for WarningEngine — severity-based checks across all dimensions.

Covers: vintage, mapping, assumptions, constraints, freshness, nowcast
warnings with proper severity levels and aggregation via check_all.

TDD: these tests are written BEFORE the implementation.
"""

from __future__ import annotations

import pytest

from src.quality.config import QualityScoringConfig
from src.quality.models import (
    DimensionAssessment,
    QualityDimension,
    QualitySeverity,
    QualityWarning,
    SourceAge,
    SourceUpdateFrequency,
)
from src.quality.scorer import QualityScorer
from src.quality.warnings import WarningEngine


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def engine() -> WarningEngine:
    """Default warning engine with standard config."""
    return WarningEngine()


@pytest.fixture
def scorer() -> QualityScorer:
    """Default scorer for building DimensionAssessments."""
    return QualityScorer()


# ===================================================================
# Vintage warnings
# ===================================================================


class TestCheckVintage:
    """check_vintage: age-based warning escalation."""

    def test_no_warning_for_fresh_model(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Age <= 4 should produce no warnings."""
        da = scorer.score_vintage(base_year=2024, current_year=2026)
        warnings = engine.check_vintage(da)
        assert len(warnings) == 0

    def test_no_warning_at_4yr(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Exactly 4 years old: no warning."""
        da = scorer.score_vintage(base_year=2022, current_year=2026)
        warnings = engine.check_vintage(da)
        assert len(warnings) == 0

    def test_warning_at_5yr(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """5 years old: WARNING severity."""
        da = scorer.score_vintage(base_year=2021, current_year=2026)
        warnings = engine.check_vintage(da)
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.WARNING
        assert "5" in warnings[0].message
        assert warnings[0].dimension == QualityDimension.VINTAGE

    def test_warning_at_7yr(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """7 years old: still WARNING (below CRITICAL threshold)."""
        da = scorer.score_vintage(base_year=2019, current_year=2026)
        warnings = engine.check_vintage(da)
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.WARNING
        assert "7" in warnings[0].message

    def test_critical_at_8yr(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """8 years old: CRITICAL severity."""
        da = scorer.score_vintage(base_year=2018, current_year=2026)
        warnings = engine.check_vintage(da)
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.CRITICAL
        assert "8" in warnings[0].message

    def test_critical_at_12yr(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """12 years old: CRITICAL severity."""
        da = scorer.score_vintage(base_year=2014, current_year=2026)
        warnings = engine.check_vintage(da)
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.CRITICAL
        assert "12" in warnings[0].message

    def test_recommendation_present(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Warnings should include a recommendation."""
        da = scorer.score_vintage(base_year=2018, current_year=2026)
        warnings = engine.check_vintage(da)
        assert len(warnings) == 1
        assert warnings[0].recommendation is not None
        assert "updating" in warnings[0].recommendation.lower()


# ===================================================================
# Mapping warnings
# ===================================================================


class TestCheckMapping:
    """check_mapping: spend-based and coverage-based warnings."""

    def test_waiver_required_above_5pct(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """unresolved_spend_pct > 5.0 -> WAIVER_REQUIRED."""
        da = scorer.score_mapping(
            coverage_pct=0.9,
            confidence_dist={"HIGH": 0.8, "MEDIUM": 0.2, "LOW": 0.0},
            residual_pct=0.05,
            unresolved_pct=0.05,
            unresolved_spend_pct=6.0,
        )
        warnings = engine.check_mapping(da)
        severities = [w.severity for w in warnings]
        assert QualitySeverity.WAIVER_REQUIRED in severities

    def test_critical_above_1pct(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """unresolved_spend_pct > 1.0 -> CRITICAL."""
        da = scorer.score_mapping(
            coverage_pct=0.9,
            confidence_dist={"HIGH": 0.8, "MEDIUM": 0.2, "LOW": 0.0},
            residual_pct=0.05,
            unresolved_pct=0.05,
            unresolved_spend_pct=2.5,
        )
        warnings = engine.check_mapping(da)
        severities = [w.severity for w in warnings]
        assert QualitySeverity.CRITICAL in severities

    def test_warning_above_0pct(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """unresolved_spend_pct > 0.0 -> WARNING."""
        da = scorer.score_mapping(
            coverage_pct=0.95,
            confidence_dist={"HIGH": 0.9, "MEDIUM": 0.1, "LOW": 0.0},
            residual_pct=0.02,
            unresolved_pct=0.01,
            unresolved_spend_pct=0.5,
        )
        warnings = engine.check_mapping(da)
        severities = [w.severity for w in warnings]
        assert QualitySeverity.WARNING in severities

    def test_no_warning_zero_spend(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """unresolved_spend_pct == 0 and good coverage -> no warnings."""
        da = scorer.score_mapping(
            coverage_pct=1.0,
            confidence_dist={"HIGH": 1.0, "MEDIUM": 0.0, "LOW": 0.0},
            residual_pct=0.0,
            unresolved_pct=0.0,
            unresolved_spend_pct=0.0,
        )
        warnings = engine.check_mapping(da)
        assert len(warnings) == 0

    def test_warning_message_contains_pct(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Warning message should contain the percentage."""
        da = scorer.score_mapping(
            coverage_pct=0.9,
            confidence_dist={"HIGH": 0.8, "MEDIUM": 0.2, "LOW": 0.0},
            residual_pct=0.0,
            unresolved_pct=0.0,
            unresolved_spend_pct=6.0,
        )
        warnings = engine.check_mapping(da)
        spend_warnings = [
            w for w in warnings if "spend" in w.message.lower() or "mapping" in w.message.lower()
        ]
        assert len(spend_warnings) >= 1
        assert "6" in spend_warnings[0].message

    def test_low_coverage_warning(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """coverage_pct < 0.8 -> WARNING about low coverage."""
        da = scorer.score_mapping(
            coverage_pct=0.7,
            confidence_dist={"HIGH": 0.8, "MEDIUM": 0.2, "LOW": 0.0},
            residual_pct=0.05,
            unresolved_pct=0.05,
            unresolved_spend_pct=0.0,
        )
        warnings = engine.check_mapping(da)
        assert len(warnings) >= 1
        coverage_warnings = [w for w in warnings if "coverage" in w.message.lower()]
        assert len(coverage_warnings) == 1
        assert coverage_warnings[0].severity == QualitySeverity.WARNING

    def test_good_coverage_no_coverage_warning(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """coverage_pct >= 0.8 -> no coverage warning."""
        da = scorer.score_mapping(
            coverage_pct=0.85,
            confidence_dist={"HIGH": 0.8, "MEDIUM": 0.2, "LOW": 0.0},
            residual_pct=0.05,
            unresolved_pct=0.05,
            unresolved_spend_pct=0.0,
        )
        warnings = engine.check_mapping(da)
        coverage_warnings = [w for w in warnings if "coverage" in w.message.lower()]
        assert len(coverage_warnings) == 0


# ===================================================================
# Assumptions warnings
# ===================================================================


class TestCheckAssumptions:
    """check_assumptions: ranges coverage warning."""

    def test_warning_below_50pct_ranges(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """ranges_coverage_pct < 0.5 -> WARNING."""
        da = scorer.score_assumptions(
            ranges_coverage_pct=0.3,
            approval_rate=0.9,
        )
        warnings = engine.check_assumptions(da)
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.WARNING
        assert warnings[0].recommendation is not None
        assert "ranges" in warnings[0].recommendation.lower() or "sensitivity" in warnings[0].recommendation.lower()

    def test_no_warning_at_80pct_ranges(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """ranges_coverage_pct >= 0.5 -> no warning."""
        da = scorer.score_assumptions(
            ranges_coverage_pct=0.8,
            approval_rate=0.9,
        )
        warnings = engine.check_assumptions(da)
        assert len(warnings) == 0

    def test_warning_at_exactly_49pct(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """49% < 50% -> WARNING."""
        da = scorer.score_assumptions(
            ranges_coverage_pct=0.49,
            approval_rate=1.0,
        )
        warnings = engine.check_assumptions(da)
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.WARNING

    def test_no_warning_at_exactly_50pct(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Exactly 50% -> no warning (threshold is < 0.5)."""
        da = scorer.score_assumptions(
            ranges_coverage_pct=0.5,
            approval_rate=1.0,
        )
        warnings = engine.check_assumptions(da)
        assert len(warnings) == 0

    def test_message_contains_percentage(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Warning message should include the percentage."""
        da = scorer.score_assumptions(
            ranges_coverage_pct=0.3,
            approval_rate=0.9,
        )
        warnings = engine.check_assumptions(da)
        assert len(warnings) == 1
        assert "30" in warnings[0].message


# ===================================================================
# Constraints warnings
# ===================================================================


class TestCheckConstraints:
    """check_constraints: high ASSUMED percentage warning."""

    def test_warning_over_50pct_assumed(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """>50% ASSUMED -> WARNING."""
        da = scorer.score_constraints(
            confidence_summary={"HARD": 2, "ESTIMATED": 2, "ASSUMED": 6},
        )
        warnings = engine.check_constraints(da)
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.WARNING
        assert "50%" in warnings[0].message or "assumed" in warnings[0].message.lower()

    def test_no_warning_below_50pct_assumed(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """<=50% ASSUMED -> no warning."""
        da = scorer.score_constraints(
            confidence_summary={"HARD": 5, "ESTIMATED": 3, "ASSUMED": 2},
        )
        warnings = engine.check_constraints(da)
        assert len(warnings) == 0

    def test_not_applicable_returns_empty(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Not-applicable dimension -> empty list."""
        da = scorer.score_constraints(confidence_summary=None)
        assert da.applicable is False
        warnings = engine.check_constraints(da)
        assert len(warnings) == 0

    def test_exactly_50pct_assumed_no_warning(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Exactly 50% ASSUMED -> no warning (threshold is >50%)."""
        da = scorer.score_constraints(
            confidence_summary={"HARD": 0, "ESTIMATED": 5, "ASSUMED": 5},
        )
        warnings = engine.check_constraints(da)
        assert len(warnings) == 0

    def test_all_assumed_triggers_warning(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """100% ASSUMED -> WARNING."""
        da = scorer.score_constraints(
            confidence_summary={"HARD": 0, "ESTIMATED": 0, "ASSUMED": 10},
        )
        warnings = engine.check_constraints(da)
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.WARNING


# ===================================================================
# Freshness warnings
# ===================================================================


class TestCheckFreshness:
    """check_freshness: ratio-based source staleness warnings."""

    def test_critical_for_ratio_above_2(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Source ratio > 2.0 -> CRITICAL."""
        sources = [
            SourceAge("Old Table", 800.0, SourceUpdateFrequency.ANNUAL),
        ]
        da = scorer.score_freshness(source_ages=sources)
        warnings = engine.check_freshness(da)
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.CRITICAL
        assert "Old Table" in warnings[0].message

    def test_warning_for_ratio_above_1_5(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Source ratio > 1.5 but <= 2.0 -> WARNING."""
        # 600/365 = 1.644 -> WARNING
        sources = [
            SourceAge("Aging Source", 600.0, SourceUpdateFrequency.ANNUAL),
        ]
        da = scorer.score_freshness(source_ages=sources)
        warnings = engine.check_freshness(da)
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.WARNING
        assert "Aging Source" in warnings[0].message

    def test_no_warning_for_fresh_source(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Ratio <= 1.5 -> no warning."""
        sources = [
            SourceAge("Fresh Source", 300.0, SourceUpdateFrequency.ANNUAL),
        ]
        da = scorer.score_freshness(source_ages=sources)
        warnings = engine.check_freshness(da)
        assert len(warnings) == 0

    def test_not_applicable_returns_empty(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Not-applicable freshness dimension -> empty list."""
        sources = [
            SourceAge("BoQ Upload", 500.0, SourceUpdateFrequency.PER_ENGAGEMENT),
        ]
        da = scorer.score_freshness(source_ages=sources)
        assert da.applicable is False
        warnings = engine.check_freshness(da)
        assert len(warnings) == 0

    def test_multiple_sources_multiple_warnings(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Multiple stale sources -> multiple warnings."""
        sources = [
            SourceAge("Very Old", 800.0, SourceUpdateFrequency.ANNUAL),  # ratio 2.19 -> CRITICAL
            SourceAge("Somewhat Old", 600.0, SourceUpdateFrequency.ANNUAL),  # ratio 1.64 -> WARNING
            SourceAge("Fresh", 100.0, SourceUpdateFrequency.ANNUAL),  # ratio 0.27 -> none
        ]
        da = scorer.score_freshness(source_ages=sources)
        warnings = engine.check_freshness(da)
        assert len(warnings) == 2
        severities = {w.severity for w in warnings}
        assert QualitySeverity.CRITICAL in severities
        assert QualitySeverity.WARNING in severities

    def test_overdue_message(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Warning message should mention 'overdue'."""
        sources = [
            SourceAge("Stale Data", 800.0, SourceUpdateFrequency.ANNUAL),
        ]
        da = scorer.score_freshness(source_ages=sources)
        warnings = engine.check_freshness(da)
        assert len(warnings) == 1
        assert "overdue" in warnings[0].message.lower()


# ===================================================================
# Nowcast warnings
# ===================================================================


class TestCheckNowcast:
    """check_nowcast: model source classification."""

    def test_info_when_nowcast(self, engine: WarningEngine) -> None:
        """Source containing 'nowcast' -> INFO."""
        warnings = engine.check_nowcast("gastat_nowcast_2024")
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.INFO
        assert "nowcast" in warnings[0].message.lower() or "balanced" in warnings[0].message.lower()

    def test_info_when_balanced(self, engine: WarningEngine) -> None:
        """Source containing 'balanced' -> INFO."""
        warnings = engine.check_nowcast("balanced_table_v2")
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.INFO

    def test_no_warning_for_regular_source(self, engine: WarningEngine) -> None:
        """Regular model source -> no warning."""
        warnings = engine.check_nowcast("gastat_official_2023")
        assert len(warnings) == 0

    def test_no_warning_for_none(self, engine: WarningEngine) -> None:
        """None model_source -> no warning."""
        warnings = engine.check_nowcast(None)
        assert len(warnings) == 0

    def test_case_insensitive(self, engine: WarningEngine) -> None:
        """Should match case-insensitively."""
        warnings = engine.check_nowcast("NOWCAST_MODEL")
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.INFO


# ===================================================================
# check_all aggregation
# ===================================================================


class TestCheckAll:
    """check_all: aggregates all checks across dimensions."""

    def test_aggregates_vintage_and_mapping(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Aggregates warnings from vintage and mapping assessments."""
        vintage_da = scorer.score_vintage(base_year=2018, current_year=2026)  # 8yr -> CRITICAL
        mapping_da = scorer.score_mapping(
            coverage_pct=0.9,
            confidence_dist={"HIGH": 0.8, "MEDIUM": 0.2, "LOW": 0.0},
            residual_pct=0.05,
            unresolved_pct=0.05,
            unresolved_spend_pct=6.0,  # WAIVER_REQUIRED
        )
        warnings = engine.check_all([vintage_da, mapping_da])
        severities = {w.severity for w in warnings}
        assert QualitySeverity.CRITICAL in severities
        assert QualitySeverity.WAIVER_REQUIRED in severities

    def test_handles_all_dimensions(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Routes each dimension to the right check method."""
        das = [
            scorer.score_vintage(base_year=2018, current_year=2026),
            scorer.score_mapping(
                coverage_pct=1.0,
                confidence_dist={"HIGH": 1.0},
                residual_pct=0.0,
                unresolved_pct=0.0,
                unresolved_spend_pct=0.0,
            ),
            scorer.score_assumptions(ranges_coverage_pct=0.3, approval_rate=0.9),
            scorer.score_constraints(confidence_summary={"HARD": 1, "ASSUMED": 9}),
            scorer.score_freshness(
                source_ages=[
                    SourceAge("Old", 800.0, SourceUpdateFrequency.ANNUAL),
                ],
            ),
        ]
        warnings = engine.check_all(das)
        # Expect vintage CRITICAL, assumptions WARNING, constraints WARNING, freshness CRITICAL
        assert len(warnings) >= 4

    def test_includes_nowcast(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """check_all also runs check_nowcast when model_source provided."""
        vintage_da = scorer.score_vintage(base_year=2024, current_year=2026)
        warnings = engine.check_all([vintage_da], model_source="nowcast_v1")
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.INFO

    def test_empty_list_with_nowcast(self, engine: WarningEngine) -> None:
        """Empty dimension list + nowcast -> only nowcast warning."""
        warnings = engine.check_all([], model_source="balanced_2024")
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.INFO

    def test_empty_list_no_nowcast(self, engine: WarningEngine) -> None:
        """Empty dimension list, no nowcast -> empty list."""
        warnings = engine.check_all([])
        assert len(warnings) == 0

    def test_skips_inapplicable_dimensions(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Not-applicable dimensions should be skipped."""
        constraints_da = scorer.score_constraints(confidence_summary=None)
        freshness_da = scorer.score_freshness(source_ages=[])
        warnings = engine.check_all([constraints_da, freshness_da])
        assert len(warnings) == 0

    def test_mixed_dims_correct_count(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """Mixed applicable/inapplicable with different severities."""
        das = [
            scorer.score_vintage(base_year=2021, current_year=2026),  # 5yr -> WARNING
            scorer.score_constraints(confidence_summary=None),  # not applicable
            scorer.score_assumptions(ranges_coverage_pct=0.8, approval_rate=0.9),  # no warning
        ]
        warnings = engine.check_all(das)
        assert len(warnings) == 1
        assert warnings[0].severity == QualitySeverity.WARNING


# ===================================================================
# count_by_severity
# ===================================================================


class TestCountBySeverity:
    """count_by_severity: severity counting utility."""

    def test_counts_each_severity(self, engine: WarningEngine) -> None:
        """Counts are keyed by severity value."""
        warnings = [
            QualityWarning(
                dimension=QualityDimension.VINTAGE,
                severity=QualitySeverity.CRITICAL,
                message="test critical",
            ),
            QualityWarning(
                dimension=QualityDimension.MAPPING,
                severity=QualitySeverity.WARNING,
                message="test warning 1",
            ),
            QualityWarning(
                dimension=QualityDimension.MAPPING,
                severity=QualitySeverity.WARNING,
                message="test warning 2",
            ),
            QualityWarning(
                dimension=QualityDimension.FRESHNESS,
                severity=QualitySeverity.INFO,
                message="test info",
            ),
            QualityWarning(
                dimension=QualityDimension.MAPPING,
                severity=QualitySeverity.WAIVER_REQUIRED,
                message="test waiver",
            ),
        ]
        counts = engine.count_by_severity(warnings)
        assert counts["CRITICAL"] == 1
        assert counts["WARNING"] == 2
        assert counts["INFO"] == 1
        assert counts["WAIVER_REQUIRED"] == 1

    def test_empty_list(self, engine: WarningEngine) -> None:
        """Empty warning list -> all zero counts."""
        counts = engine.count_by_severity([])
        assert counts.get("CRITICAL", 0) == 0
        assert counts.get("WARNING", 0) == 0

    def test_single_severity(self, engine: WarningEngine) -> None:
        """All warnings of same severity."""
        warnings = [
            QualityWarning(
                dimension=QualityDimension.VINTAGE,
                severity=QualitySeverity.WARNING,
                message="warn 1",
            ),
            QualityWarning(
                dimension=QualityDimension.MAPPING,
                severity=QualitySeverity.WARNING,
                message="warn 2",
            ),
        ]
        counts = engine.count_by_severity(warnings)
        assert counts["WARNING"] == 2

    def test_integration_with_check_all(
        self, engine: WarningEngine, scorer: QualityScorer
    ) -> None:
        """count_by_severity works with check_all output."""
        das = [
            scorer.score_vintage(base_year=2018, current_year=2026),  # CRITICAL
            scorer.score_assumptions(ranges_coverage_pct=0.3, approval_rate=0.9),  # WARNING
        ]
        warnings = engine.check_all(das, model_source="nowcast_v1")  # INFO
        counts = engine.count_by_severity(warnings)
        assert counts.get("CRITICAL", 0) >= 1
        assert counts.get("WARNING", 0) >= 1
        assert counts.get("INFO", 0) >= 1
