"""Tests for quality module enums, dataclasses, and Pydantic models.

Covers: enum members and StrEnum behavior, SourceAge frozen dataclass,
QualityWarning defaults, DimensionAssessment defaults,
RunQualityAssessment defaults and frozen behavior.
"""

import dataclasses
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.quality.models import (
    DimensionAssessment,
    NowcastStatus,
    PlausibilityStatus,
    QualityDimension,
    QualityGrade,
    QualitySeverity,
    QualityWarning,
    RunQualityAssessment,
    SourceAge,
    SourceUpdateFrequency,
)


# ===================================================================
# QualitySeverity enum
# ===================================================================


class TestQualitySeverity:
    """QualitySeverity has exactly 4 members and is StrEnum."""

    def test_member_count(self) -> None:
        assert len(QualitySeverity) == 4

    def test_values(self) -> None:
        assert QualitySeverity.INFO == "INFO"
        assert QualitySeverity.WARNING == "WARNING"
        assert QualitySeverity.CRITICAL == "CRITICAL"
        assert QualitySeverity.WAIVER_REQUIRED == "WAIVER_REQUIRED"

    def test_is_str(self) -> None:
        for member in QualitySeverity:
            assert isinstance(member, str)


# ===================================================================
# QualityGrade enum
# ===================================================================


class TestQualityGrade:
    """QualityGrade has exactly 5 members and is StrEnum."""

    def test_member_count(self) -> None:
        assert len(QualityGrade) == 5

    def test_values(self) -> None:
        assert QualityGrade.A == "A"
        assert QualityGrade.B == "B"
        assert QualityGrade.C == "C"
        assert QualityGrade.D == "D"
        assert QualityGrade.F == "F"

    def test_is_str(self) -> None:
        for member in QualityGrade:
            assert isinstance(member, str)


# ===================================================================
# QualityDimension enum
# ===================================================================


class TestQualityDimension:
    """QualityDimension has exactly 7 members and is StrEnum."""

    def test_member_count(self) -> None:
        assert len(QualityDimension) == 7

    def test_values(self) -> None:
        assert QualityDimension.VINTAGE == "VINTAGE"
        assert QualityDimension.MAPPING == "MAPPING"
        assert QualityDimension.ASSUMPTIONS == "ASSUMPTIONS"
        assert QualityDimension.CONSTRAINTS == "CONSTRAINTS"
        assert QualityDimension.WORKFORCE == "WORKFORCE"
        assert QualityDimension.PLAUSIBILITY == "PLAUSIBILITY"
        assert QualityDimension.FRESHNESS == "FRESHNESS"

    def test_is_str(self) -> None:
        for member in QualityDimension:
            assert isinstance(member, str)


# ===================================================================
# NowcastStatus enum
# ===================================================================


class TestNowcastStatus:
    """NowcastStatus has exactly 3 members and is StrEnum."""

    def test_member_count(self) -> None:
        assert len(NowcastStatus) == 3

    def test_values(self) -> None:
        assert NowcastStatus.DRAFT == "DRAFT"
        assert NowcastStatus.APPROVED == "APPROVED"
        assert NowcastStatus.REJECTED == "REJECTED"

    def test_is_str(self) -> None:
        for member in NowcastStatus:
            assert isinstance(member, str)


# ===================================================================
# PlausibilityStatus enum
# ===================================================================


class TestPlausibilityStatus:
    """PlausibilityStatus has exactly 4 members and is StrEnum."""

    def test_member_count(self) -> None:
        assert len(PlausibilityStatus) == 4

    def test_values(self) -> None:
        assert PlausibilityStatus.IN_RANGE == "IN_RANGE"
        assert PlausibilityStatus.ABOVE_RANGE == "ABOVE_RANGE"
        assert PlausibilityStatus.BELOW_RANGE == "BELOW_RANGE"
        assert PlausibilityStatus.NO_BENCHMARK == "NO_BENCHMARK"

    def test_is_str(self) -> None:
        for member in PlausibilityStatus:
            assert isinstance(member, str)


# ===================================================================
# SourceUpdateFrequency enum
# ===================================================================


class TestSourceUpdateFrequency:
    """SourceUpdateFrequency has exactly 6 members and is StrEnum."""

    def test_member_count(self) -> None:
        assert len(SourceUpdateFrequency) == 6

    def test_values(self) -> None:
        assert SourceUpdateFrequency.QUARTERLY == "QUARTERLY"
        assert SourceUpdateFrequency.ANNUAL == "ANNUAL"
        assert SourceUpdateFrequency.BIENNIAL == "BIENNIAL"
        assert SourceUpdateFrequency.TRIENNIAL == "TRIENNIAL"
        assert SourceUpdateFrequency.QUINQUENNIAL == "QUINQUENNIAL"
        assert SourceUpdateFrequency.PER_ENGAGEMENT == "PER_ENGAGEMENT"

    def test_is_str(self) -> None:
        for member in SourceUpdateFrequency:
            assert isinstance(member, str)


# ===================================================================
# SourceAge frozen dataclass
# ===================================================================


class TestSourceAge:
    """SourceAge is a frozen dataclass with expected fields."""

    def test_creation(self) -> None:
        sa = SourceAge(
            source_name="GASTAT I-O Tables",
            age_days=730.0,
            expected_frequency=SourceUpdateFrequency.ANNUAL,
        )
        assert sa.source_name == "GASTAT I-O Tables"
        assert sa.age_days == 730.0
        assert sa.expected_frequency == SourceUpdateFrequency.ANNUAL

    def test_is_frozen(self) -> None:
        sa = SourceAge(
            source_name="Test",
            age_days=100.0,
            expected_frequency=SourceUpdateFrequency.QUARTERLY,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            sa.source_name = "Changed"  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(SourceAge)


# ===================================================================
# QualityWarning Pydantic model
# ===================================================================


class TestQualityWarning:
    """QualityWarning creates with defaults and validates correctly."""

    def test_creation_with_defaults(self) -> None:
        w = QualityWarning(
            dimension=QualityDimension.VINTAGE,
            severity=QualitySeverity.WARNING,
            message="Table vintage is 4 years old.",
        )
        assert isinstance(w.warning_id, UUID)
        assert w.dimension == QualityDimension.VINTAGE
        assert w.severity == QualitySeverity.WARNING
        assert w.message == "Table vintage is 4 years old."
        assert w.detail is None
        assert w.recommendation is None

    def test_creation_with_all_fields(self) -> None:
        w = QualityWarning(
            dimension=QualityDimension.MAPPING,
            severity=QualitySeverity.CRITICAL,
            message="Unmapped sectors detected.",
            detail="3 sectors have no mapping.",
            recommendation="Review sector concordance.",
        )
        assert w.detail == "3 sectors have no mapping."
        assert w.recommendation == "Review sector concordance."

    def test_uuid_is_generated(self) -> None:
        w1 = QualityWarning(
            dimension=QualityDimension.FRESHNESS,
            severity=QualitySeverity.INFO,
            message="Data is fresh.",
        )
        w2 = QualityWarning(
            dimension=QualityDimension.FRESHNESS,
            severity=QualitySeverity.INFO,
            message="Data is fresh.",
        )
        assert w1.warning_id != w2.warning_id


# ===================================================================
# DimensionAssessment Pydantic model
# ===================================================================


class TestDimensionAssessment:
    """DimensionAssessment creates with defaults and validates score bounds."""

    def test_creation_with_defaults(self) -> None:
        da = DimensionAssessment(
            dimension=QualityDimension.VINTAGE,
            score=0.85,
            applicable=True,
        )
        assert da.dimension == QualityDimension.VINTAGE
        assert da.score == 0.85
        assert da.applicable is True
        assert da.inputs_used == {}
        assert da.rules_triggered == []
        assert da.warnings == []

    def test_score_lower_bound(self) -> None:
        da = DimensionAssessment(
            dimension=QualityDimension.MAPPING,
            score=0.0,
            applicable=True,
        )
        assert da.score == 0.0

    def test_score_upper_bound(self) -> None:
        da = DimensionAssessment(
            dimension=QualityDimension.MAPPING,
            score=1.0,
            applicable=True,
        )
        assert da.score == 1.0

    def test_score_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DimensionAssessment(
                dimension=QualityDimension.MAPPING,
                score=-0.1,
                applicable=True,
            )

    def test_score_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DimensionAssessment(
                dimension=QualityDimension.MAPPING,
                score=1.1,
                applicable=True,
            )

    def test_with_warnings(self) -> None:
        warning = QualityWarning(
            dimension=QualityDimension.VINTAGE,
            severity=QualitySeverity.WARNING,
            message="Old vintage.",
        )
        da = DimensionAssessment(
            dimension=QualityDimension.VINTAGE,
            score=0.5,
            applicable=True,
            warnings=[warning],
        )
        assert len(da.warnings) == 1
        assert da.warnings[0].message == "Old vintage."

    def test_with_inputs_and_rules(self) -> None:
        da = DimensionAssessment(
            dimension=QualityDimension.ASSUMPTIONS,
            score=0.7,
            applicable=True,
            inputs_used={"assumption_count": 5, "approved_count": 3},
            rules_triggered=["assumption_approval_ratio"],
        )
        assert da.inputs_used["assumption_count"] == 5
        assert len(da.rules_triggered) == 1


# ===================================================================
# RunQualityAssessment Pydantic model
# ===================================================================


class TestRunQualityAssessment:
    """RunQualityAssessment creates with defaults and is frozen."""

    def test_creation_with_all_defaults(self) -> None:
        rqa = RunQualityAssessment(assessment_version=1)
        assert isinstance(rqa.assessment_id, UUID)
        assert rqa.assessment_version == 1
        assert rqa.run_id is None
        assert rqa.dimension_assessments == []
        assert rqa.applicable_dimensions == []
        assert rqa.assessed_dimensions == []
        assert rqa.missing_dimensions == []
        assert rqa.completeness_pct == 0.0
        assert rqa.composite_score == 0.0
        assert rqa.grade == QualityGrade.F
        assert rqa.warnings == []
        assert rqa.waiver_required_count == 0
        assert rqa.critical_count == 0
        assert rqa.warning_count == 0
        assert rqa.info_count == 0
        assert rqa.known_gaps == []
        assert rqa.notes is None
        assert rqa.created_at is not None
        assert rqa.created_at.tzinfo is not None

    def test_is_frozen(self) -> None:
        rqa = RunQualityAssessment(assessment_version=1)
        with pytest.raises(ValidationError):
            rqa.grade = QualityGrade.A  # type: ignore[misc]

    def test_frozen_run_id(self) -> None:
        rqa = RunQualityAssessment(assessment_version=1)
        with pytest.raises(ValidationError):
            rqa.run_id = None  # type: ignore[misc]

    def test_version_must_be_ge_1(self) -> None:
        with pytest.raises(ValidationError):
            RunQualityAssessment(assessment_version=0)

    def test_composite_score_bounds(self) -> None:
        rqa = RunQualityAssessment(
            assessment_version=1,
            composite_score=0.85,
        )
        assert rqa.composite_score == 0.85

    def test_composite_score_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RunQualityAssessment(
                assessment_version=1,
                composite_score=-0.1,
            )

    def test_composite_score_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RunQualityAssessment(
                assessment_version=1,
                composite_score=1.1,
            )

    def test_uuid_is_generated(self) -> None:
        rqa1 = RunQualityAssessment(assessment_version=1)
        rqa2 = RunQualityAssessment(assessment_version=1)
        assert rqa1.assessment_id != rqa2.assessment_id

    def test_with_dimension_assessments(self) -> None:
        da = DimensionAssessment(
            dimension=QualityDimension.VINTAGE,
            score=0.85,
            applicable=True,
        )
        rqa = RunQualityAssessment(
            assessment_version=1,
            dimension_assessments=[da],
            applicable_dimensions=[QualityDimension.VINTAGE],
            assessed_dimensions=[QualityDimension.VINTAGE],
            completeness_pct=100.0,
            composite_score=0.85,
            grade=QualityGrade.A,
        )
        assert len(rqa.dimension_assessments) == 1
        assert rqa.composite_score == 0.85
        assert rqa.grade == QualityGrade.A
