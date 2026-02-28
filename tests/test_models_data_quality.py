"""Tests for data quality Pydantic models — MVP-13.

All 7 amendments applied:
1. STRUCTURAL_VALIDITY in QualityDimension
2. dimension_weights on InputQualityScore
3. mapping_coverage_pct on RunQualitySummary
4. (Freshness smooth decay — tested in engine)
5. summary_version + summary_hash on RunQualitySummary
6. (force_recompute — tested in API)
7. PublicationGateMode on RunQualitySummary
"""

from datetime import UTC, datetime

import pytest
from uuid_extensions import uuid7

from src.models.common import utc_now

# ---------------------------------------------------------------------------
# QualityDimension enum
# ---------------------------------------------------------------------------


class TestQualityDimension:
    def test_all_values_present(self) -> None:
        from src.models.data_quality import QualityDimension

        expected = {
            "FRESHNESS", "COMPLETENESS", "CONFIDENCE",
            "PROVENANCE", "CONSISTENCY", "STRUCTURAL_VALIDITY",
        }
        assert {v.value for v in QualityDimension} == expected

    def test_is_str_enum(self) -> None:
        from src.models.data_quality import QualityDimension

        assert QualityDimension.FRESHNESS == "FRESHNESS"

    def test_structural_validity_amendment1(self) -> None:
        from src.models.data_quality import QualityDimension

        assert QualityDimension.STRUCTURAL_VALIDITY == "STRUCTURAL_VALIDITY"


# ---------------------------------------------------------------------------
# QualityGrade enum
# ---------------------------------------------------------------------------


class TestQualityGrade:
    def test_all_values_present(self) -> None:
        from src.models.data_quality import QualityGrade

        assert {v.value for v in QualityGrade} == {"A", "B", "C", "D", "F"}

    def test_is_str_enum(self) -> None:
        from src.models.data_quality import QualityGrade

        assert QualityGrade.A == "A"
        assert QualityGrade.F == "F"


# ---------------------------------------------------------------------------
# StalenessLevel enum
# ---------------------------------------------------------------------------


class TestStalenessLevel:
    def test_all_values_present(self) -> None:
        from src.models.data_quality import StalenessLevel

        expected = {"CURRENT", "AGING", "STALE", "EXPIRED"}
        assert {v.value for v in StalenessLevel} == expected

    def test_is_str_enum(self) -> None:
        from src.models.data_quality import StalenessLevel

        assert StalenessLevel.CURRENT == "CURRENT"
        assert StalenessLevel.EXPIRED == "EXPIRED"


# ---------------------------------------------------------------------------
# PublicationGateMode enum (Amendment 7)
# ---------------------------------------------------------------------------


class TestPublicationGateMode:
    def test_all_values_present(self) -> None:
        from src.models.data_quality import PublicationGateMode

        expected = {"PASS", "PASS_WITH_WARNINGS", "FAIL_REQUIRES_WAIVER"}
        assert {v.value for v in PublicationGateMode} == expected


# ---------------------------------------------------------------------------
# FreshnessThresholds
# ---------------------------------------------------------------------------


class TestFreshnessThresholds:
    def test_valid_construction(self) -> None:
        from src.models.data_quality import FreshnessThresholds

        ft = FreshnessThresholds(
            aging_days=365, stale_days=730, expired_days=1095,
        )
        assert ft.aging_days == 365
        assert ft.stale_days == 730
        assert ft.expired_days == 1095

    def test_default_thresholds_io_table(self) -> None:
        from src.models.data_quality import DEFAULT_FRESHNESS_THRESHOLDS

        io = DEFAULT_FRESHNESS_THRESHOLDS["io_table"]
        assert io.aging_days == 3 * 365
        assert io.stale_days == 5 * 365
        assert io.expired_days == 7 * 365

    def test_default_thresholds_coefficients(self) -> None:
        from src.models.data_quality import DEFAULT_FRESHNESS_THRESHOLDS

        c = DEFAULT_FRESHNESS_THRESHOLDS["coefficients"]
        assert c.aging_days == 365
        assert c.stale_days == 2 * 365
        assert c.expired_days == 3 * 365

    def test_default_thresholds_policy(self) -> None:
        from src.models.data_quality import DEFAULT_FRESHNESS_THRESHOLDS

        p = DEFAULT_FRESHNESS_THRESHOLDS["policy"]
        assert p.aging_days == 180
        assert p.stale_days == 365
        assert p.expired_days == 2 * 365

    def test_default_fallback(self) -> None:
        from src.models.data_quality import DEFAULT_FRESHNESS_THRESHOLDS

        d = DEFAULT_FRESHNESS_THRESHOLDS["default"]
        assert d.aging_days == 365


# ---------------------------------------------------------------------------
# GradeThresholds
# ---------------------------------------------------------------------------


class TestGradeThresholds:
    def test_default_values(self) -> None:
        from src.models.data_quality import GradeThresholds

        gt = GradeThresholds()
        assert gt.a_min == 0.9
        assert gt.b_min == 0.75
        assert gt.c_min == 0.6
        assert gt.d_min == 0.4

    def test_custom_values(self) -> None:
        from src.models.data_quality import GradeThresholds

        gt = GradeThresholds(a_min=0.95, b_min=0.8, c_min=0.65, d_min=0.45)
        assert gt.a_min == 0.95


# ---------------------------------------------------------------------------
# DimensionScore
# ---------------------------------------------------------------------------


class TestDimensionScore:
    def test_valid_construction(self) -> None:
        from src.models.data_quality import DimensionScore, QualityDimension, QualityGrade

        ds = DimensionScore(
            dimension=QualityDimension.FRESHNESS,
            score=0.85,
            grade=QualityGrade.B,
            details="Data is 2 years old",
            penalties=["Approaching aging threshold"],
        )
        assert ds.score == 0.85
        assert ds.grade == QualityGrade.B
        assert len(ds.penalties) == 1

    def test_score_bounds_valid(self) -> None:
        from src.models.data_quality import DimensionScore, QualityDimension, QualityGrade

        ds_low = DimensionScore(
            dimension=QualityDimension.COMPLETENESS,
            score=0.0, grade=QualityGrade.F,
            details="", penalties=[],
        )
        assert ds_low.score == 0.0

        ds_high = DimensionScore(
            dimension=QualityDimension.COMPLETENESS,
            score=1.0, grade=QualityGrade.A,
            details="", penalties=[],
        )
        assert ds_high.score == 1.0

    def test_score_out_of_bounds_raises(self) -> None:
        from src.models.data_quality import DimensionScore, QualityDimension, QualityGrade

        with pytest.raises(Exception):
            DimensionScore(
                dimension=QualityDimension.FRESHNESS,
                score=1.5, grade=QualityGrade.A,
                details="", penalties=[],
            )

    def test_empty_penalties_allowed(self) -> None:
        from src.models.data_quality import DimensionScore, QualityDimension, QualityGrade

        ds = DimensionScore(
            dimension=QualityDimension.CONSISTENCY,
            score=1.0, grade=QualityGrade.A,
            details="Perfect", penalties=[],
        )
        assert ds.penalties == []

    def test_multiple_penalties(self) -> None:
        from src.models.data_quality import DimensionScore, QualityDimension, QualityGrade

        ds = DimensionScore(
            dimension=QualityDimension.PROVENANCE,
            score=0.3, grade=QualityGrade.F,
            details="Weak provenance",
            penalties=["No evidence refs", "No source description", "Is assumption"],
        )
        assert len(ds.penalties) == 3


# ---------------------------------------------------------------------------
# InputQualityScore
# ---------------------------------------------------------------------------


class TestInputQualityScore:
    def test_valid_construction(self) -> None:
        from src.models.data_quality import (
            DimensionScore,
            InputQualityScore,
            QualityDimension,
            QualityGrade,
        )

        ds = DimensionScore(
            dimension=QualityDimension.FRESHNESS,
            score=0.9, grade=QualityGrade.A,
            details="Fresh", penalties=[],
        )
        iqs = InputQualityScore(
            input_type="io_table",
            input_version_id=uuid7(),
            dimension_scores=[ds],
            overall_score=0.9,
            overall_grade=QualityGrade.A,
            dimension_weights={"FRESHNESS": 1.0},
        )
        assert iqs.overall_score == 0.9
        assert iqs.overall_grade == QualityGrade.A
        assert iqs.input_type == "io_table"

    def test_dimension_weights_stored_amendment2(self) -> None:
        """Amendment 2: dimension_weights stored for auditability."""
        from src.models.data_quality import (
            DimensionScore,
            InputQualityScore,
            QualityDimension,
            QualityGrade,
        )

        ds = DimensionScore(
            dimension=QualityDimension.COMPLETENESS,
            score=0.8, grade=QualityGrade.B,
            details="", penalties=[],
        )
        weights = {"COMPLETENESS": 0.4, "CONFIDENCE": 0.6}
        iqs = InputQualityScore(
            input_type="mapping",
            input_version_id=uuid7(),
            dimension_scores=[ds],
            overall_score=0.8,
            overall_grade=QualityGrade.B,
            dimension_weights=weights,
        )
        assert iqs.dimension_weights == weights

    def test_input_version_id_nullable(self) -> None:
        from src.models.data_quality import (
            DimensionScore,
            InputQualityScore,
            QualityDimension,
            QualityGrade,
        )

        ds = DimensionScore(
            dimension=QualityDimension.FRESHNESS,
            score=0.5, grade=QualityGrade.D,
            details="", penalties=[],
        )
        iqs = InputQualityScore(
            input_type="io_table",
            input_version_id=None,
            dimension_scores=[ds],
            overall_score=0.5,
            overall_grade=QualityGrade.D,
            dimension_weights={"FRESHNESS": 1.0},
        )
        assert iqs.input_version_id is None

    def test_computed_at_defaults(self) -> None:
        from src.models.data_quality import (
            DimensionScore,
            InputQualityScore,
            QualityDimension,
            QualityGrade,
        )

        ds = DimensionScore(
            dimension=QualityDimension.FRESHNESS,
            score=0.7, grade=QualityGrade.C,
            details="", penalties=[],
        )
        iqs = InputQualityScore(
            input_type="io_table",
            dimension_scores=[ds],
            overall_score=0.7,
            overall_grade=QualityGrade.C,
            dimension_weights={"FRESHNESS": 1.0},
        )
        assert iqs.computed_at is not None

    def test_grade_a_threshold(self) -> None:
        from src.models.data_quality import InputQualityScore, QualityGrade

        iqs = InputQualityScore(
            input_type="io_table",
            dimension_scores=[],
            overall_score=0.95,
            overall_grade=QualityGrade.A,
            dimension_weights={},
        )
        assert iqs.overall_grade == QualityGrade.A

    def test_grade_f_threshold(self) -> None:
        from src.models.data_quality import InputQualityScore, QualityGrade

        iqs = InputQualityScore(
            input_type="io_table",
            dimension_scores=[],
            overall_score=0.2,
            overall_grade=QualityGrade.F,
            dimension_weights={},
        )
        assert iqs.overall_grade == QualityGrade.F

    def test_empty_dimension_scores_allowed(self) -> None:
        from src.models.data_quality import InputQualityScore, QualityGrade

        iqs = InputQualityScore(
            input_type="io_table",
            dimension_scores=[],
            overall_score=0.0,
            overall_grade=QualityGrade.F,
            dimension_weights={},
        )
        assert iqs.dimension_scores == []


# ---------------------------------------------------------------------------
# FreshnessCheck
# ---------------------------------------------------------------------------


class TestFreshnessCheck:
    def test_valid_construction(self) -> None:
        from src.models.data_quality import FreshnessCheck, StalenessLevel

        fc = FreshnessCheck(
            source_name="GASTAT IO Table 2019",
            source_type="io_table",
            last_updated=datetime(2019, 1, 1, tzinfo=UTC),
            checked_at=utc_now(),
            staleness=StalenessLevel.STALE,
            days_since_update=2557,
            recommended_action="Consider nowcasting update",
        )
        assert fc.staleness == StalenessLevel.STALE
        assert fc.days_since_update == 2557

    def test_current_source(self) -> None:
        from src.models.data_quality import FreshnessCheck, StalenessLevel

        fc = FreshnessCheck(
            source_name="Recent data",
            source_type="coefficients",
            last_updated=utc_now(),
            checked_at=utc_now(),
            staleness=StalenessLevel.CURRENT,
            days_since_update=0,
            recommended_action="No action needed",
        )
        assert fc.staleness == StalenessLevel.CURRENT

    def test_fields_present(self) -> None:
        from src.models.data_quality import FreshnessCheck, StalenessLevel

        fc = FreshnessCheck(
            source_name="test",
            source_type="policy",
            last_updated=utc_now(),
            checked_at=utc_now(),
            staleness=StalenessLevel.CURRENT,
            days_since_update=10,
            recommended_action="OK",
        )
        assert fc.source_name == "test"
        assert fc.source_type == "policy"
        assert fc.recommended_action == "OK"


# ---------------------------------------------------------------------------
# FreshnessReport
# ---------------------------------------------------------------------------


class TestFreshnessReport:
    def test_valid_construction(self) -> None:
        from src.models.data_quality import FreshnessCheck, FreshnessReport, StalenessLevel

        check = FreshnessCheck(
            source_name="IO Table",
            source_type="io_table",
            last_updated=utc_now(),
            checked_at=utc_now(),
            staleness=StalenessLevel.CURRENT,
            days_since_update=30,
            recommended_action="OK",
        )
        report = FreshnessReport(
            checks=[check],
            stale_count=0,
            expired_count=0,
            overall_freshness=StalenessLevel.CURRENT,
        )
        assert len(report.checks) == 1
        assert report.stale_count == 0

    def test_worst_of_checks(self) -> None:
        from src.models.data_quality import FreshnessReport, StalenessLevel

        report = FreshnessReport(
            checks=[],
            stale_count=1,
            expired_count=0,
            overall_freshness=StalenessLevel.STALE,
        )
        assert report.overall_freshness == StalenessLevel.STALE

    def test_empty_checks(self) -> None:
        from src.models.data_quality import FreshnessReport, StalenessLevel

        report = FreshnessReport(
            checks=[],
            stale_count=0,
            expired_count=0,
            overall_freshness=StalenessLevel.CURRENT,
        )
        assert len(report.checks) == 0

    def test_expired_count_tracked(self) -> None:
        from src.models.data_quality import FreshnessReport, StalenessLevel

        report = FreshnessReport(
            checks=[],
            stale_count=2,
            expired_count=1,
            overall_freshness=StalenessLevel.EXPIRED,
        )
        assert report.expired_count == 1


# ---------------------------------------------------------------------------
# RunQualitySummary (frozen)
# ---------------------------------------------------------------------------


class TestRunQualitySummary:
    def _make_summary(self, **overrides):  # noqa: ANN003
        from src.models.data_quality import (
            FreshnessReport,
            PublicationGateMode,
            QualityGrade,
            RunQualitySummary,
            StalenessLevel,
        )

        defaults = {
            "run_id": uuid7(),
            "workspace_id": uuid7(),
            "base_table_vintage": "GASTAT 2019 IO Table",
            "base_table_year": 2019,
            "years_since_base": 7,
            "input_scores": [],
            "overall_run_score": 0.75,
            "overall_run_grade": QualityGrade.B,
            "freshness_report": FreshnessReport(
                checks=[], stale_count=0, expired_count=0,
                overall_freshness=StalenessLevel.CURRENT,
            ),
            "coverage_pct": 0.85,
            "mapping_coverage_pct": 0.90,
            "key_gaps": [],
            "key_strengths": ["Strong IO table provenance"],
            "recommendation": "Suitable for governed publication",
            "publication_gate_pass": True,
            "publication_gate_mode": PublicationGateMode.PASS,
            "summary_version": "1.0.0",
            "summary_hash": "abc123",
        }
        defaults.update(overrides)
        return RunQualitySummary(**defaults)

    def test_valid_construction(self) -> None:
        s = self._make_summary()
        assert s.base_table_year == 2019
        assert s.overall_run_grade == "B"

    def test_frozen_immutability(self) -> None:
        s = self._make_summary()
        with pytest.raises(Exception):
            s.overall_run_score = 0.5  # type: ignore[misc]

    def test_key_gaps_is_list(self) -> None:
        s = self._make_summary(key_gaps=["Missing sector F data", "No bridge"])
        assert len(s.key_gaps) == 2

    def test_key_strengths_is_list(self) -> None:
        s = self._make_summary(key_strengths=["Recent coefficients"])
        assert s.key_strengths == ["Recent coefficients"]

    def test_created_at_defaults(self) -> None:
        s = self._make_summary()
        assert s.created_at is not None

    def test_publication_gate_pass_bool(self) -> None:
        s = self._make_summary(publication_gate_pass=True)
        assert s.publication_gate_pass is True

    def test_mapping_coverage_pct_amendment3(self) -> None:
        """Amendment 3: mapping_coverage_pct stored."""
        s = self._make_summary(mapping_coverage_pct=0.65)
        assert s.mapping_coverage_pct == 0.65

    def test_mapping_coverage_pct_nullable(self) -> None:
        """Amendment 3: mapping_coverage_pct can be None."""
        s = self._make_summary(mapping_coverage_pct=None)
        assert s.mapping_coverage_pct is None

    def test_summary_version_amendment5(self) -> None:
        """Amendment 5: summary_version for audit."""
        s = self._make_summary(summary_version="1.0.0")
        assert s.summary_version == "1.0.0"

    def test_summary_hash_amendment5(self) -> None:
        """Amendment 5: summary_hash for audit."""
        s = self._make_summary(summary_hash="sha256_digest")
        assert s.summary_hash == "sha256_digest"

    def test_publication_gate_mode_pass_amendment7(self) -> None:
        """Amendment 7: PASS mode."""
        from src.models.data_quality import PublicationGateMode

        s = self._make_summary(
            publication_gate_mode=PublicationGateMode.PASS,
        )
        assert s.publication_gate_mode == "PASS"

    def test_publication_gate_mode_warnings_amendment7(self) -> None:
        """Amendment 7: PASS_WITH_WARNINGS mode."""
        from src.models.data_quality import PublicationGateMode

        s = self._make_summary(
            publication_gate_mode=PublicationGateMode.PASS_WITH_WARNINGS,
        )
        assert s.publication_gate_mode == "PASS_WITH_WARNINGS"

    def test_publication_gate_mode_fail_amendment7(self) -> None:
        """Amendment 7: FAIL_REQUIRES_WAIVER mode."""
        from src.models.data_quality import PublicationGateMode

        s = self._make_summary(
            publication_gate_mode=PublicationGateMode.FAIL_REQUIRES_WAIVER,
            publication_gate_pass=False,
        )
        assert s.publication_gate_mode == "FAIL_REQUIRES_WAIVER"
        assert s.publication_gate_pass is False

    def test_grade_values_a_through_f(self) -> None:
        from src.models.data_quality import QualityGrade

        for grade in QualityGrade:
            s = self._make_summary(overall_run_grade=grade)
            assert s.overall_run_grade == grade
