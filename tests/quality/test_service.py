"""Tests for QualityAssessmentService — orchestrator (MVP-13 Task 9).

Covers: full assessment, minimal (vintage-only), versioning,
warnings inclusion, input gating for mapping/plausibility/freshness,
model-source nowcast info, grade ranges, and no-run-id defaults.

TDD: these tests are written BEFORE the implementation.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.quality.config import QualityScoringConfig
from src.quality.models import (
    QualityDimension,
    QualityGrade,
    QualitySeverity,
    RunQualityAssessment,
    SourceAge,
    SourceUpdateFrequency,
)
from src.quality.service import QualityAssessmentService


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def svc() -> QualityAssessmentService:
    """Default service with standard config."""
    return QualityAssessmentService()


def _perfect_inputs() -> dict:
    """Return keyword arguments that produce perfect scores in all 7 dimensions."""
    return dict(
        base_year=2026,
        current_year=2026,
        # Mapping — perfect
        mapping_coverage_pct=1.0,
        mapping_confidence_dist={"HIGH": 1.0, "MEDIUM": 0.0, "LOW": 0.0},
        mapping_residual_pct=0.0,
        mapping_unresolved_pct=0.0,
        mapping_unresolved_spend_pct=0.0,
        # Assumptions — perfect
        assumption_ranges_coverage_pct=1.0,
        assumption_approval_rate=1.0,
        # Constraints — all HARD
        constraint_confidence_summary={"HARD": 10, "ESTIMATED": 0, "ASSUMED": 0},
        # Workforce — high
        workforce_overall_confidence="HIGH",
        # Plausibility — 100%
        plausibility_in_range_pct=100.0,
        plausibility_flagged_count=0,
        # Freshness — fresh source
        source_ages=[
            SourceAge("GASTAT IO", 100.0, SourceUpdateFrequency.ANNUAL),
        ],
    )


# ===================================================================
# Test 1: Full assessment — all 7 dimensions
# ===================================================================


class TestFullAssessment:
    """All 7 dimensions provided -> composite > 0, grade valid, 7 assessed."""

    def test_full_assessment(self, svc: QualityAssessmentService) -> None:
        result = svc.assess(**_perfect_inputs())

        assert isinstance(result, RunQualityAssessment)
        assert result.composite_score > 0.0
        assert result.grade in list(QualityGrade)
        assert len(result.dimension_assessments) == 7

        assessed_dims = {da.dimension for da in result.dimension_assessments}
        for dim in QualityDimension:
            assert dim in assessed_dims


# ===================================================================
# Test 2: Minimal assessment — only vintage
# ===================================================================


class TestMinimalAssessment:
    """Only vintage assessable (all others None) -> completeness < 50%."""

    def test_minimal_assessment(self, svc: QualityAssessmentService) -> None:
        result = svc.assess(base_year=2024, current_year=2026)

        # Only VINTAGE should be assessed (constraints/workforce pass-through
        # but return not-applicable when None).
        applicable_dims = [da.dimension for da in result.dimension_assessments if da.applicable]
        assert QualityDimension.VINTAGE in applicable_dims

        # Mapping, assumptions, plausibility, freshness should NOT be assessed
        # (their inputs are None so they are skipped entirely).
        # Constraints and workforce are pass-through but not applicable.
        assessed_dim_names = {da.dimension for da in result.dimension_assessments}
        assert QualityDimension.MAPPING not in assessed_dim_names
        assert QualityDimension.ASSUMPTIONS not in assessed_dim_names
        assert QualityDimension.PLAUSIBILITY not in assessed_dim_names
        assert QualityDimension.FRESHNESS not in assessed_dim_names

        # Completeness < 50% (only 1 applicable out of assessed dimensions)
        assert result.completeness_pct < 50.0


# ===================================================================
# Test 3: Versioned assessment — same run_id twice
# ===================================================================


class TestVersionedAssessment:
    """Same run_id called twice -> version increments (1 then 2)."""

    def test_versioned_assessment(self, svc: QualityAssessmentService) -> None:
        run_id = uuid4()
        inputs = _perfect_inputs()
        inputs["run_id"] = run_id

        first = svc.assess(**inputs)
        assert first.assessment_version == 1

        second = svc.assess(**inputs)
        assert second.assessment_version == 2


# ===================================================================
# Test 4: Different run_ids each start at version 1
# ===================================================================


class TestDifferentRunIds:
    """Different run_ids each start at version 1."""

    def test_different_run_ids(self, svc: QualityAssessmentService) -> None:
        inputs_a = _perfect_inputs()
        inputs_a["run_id"] = uuid4()
        inputs_b = _perfect_inputs()
        inputs_b["run_id"] = uuid4()

        result_a = svc.assess(**inputs_a)
        result_b = svc.assess(**inputs_b)

        assert result_a.assessment_version == 1
        assert result_b.assessment_version == 1


# ===================================================================
# Test 5: Warnings included — old model
# ===================================================================


class TestWarningsIncluded:
    """Old model (base_year=2016) -> critical_count > 0 or warning_count > 0."""

    def test_warnings_included(self, svc: QualityAssessmentService) -> None:
        result = svc.assess(base_year=2016, current_year=2026)

        # 10yr old model should trigger vintage warnings
        total_warnings = result.critical_count + result.warning_count
        assert total_warnings > 0


# ===================================================================
# Test 6: Mapping requires ALL inputs
# ===================================================================


class TestMappingRequiresAllInputs:
    """Provide only some mapping inputs -> mapping not scored."""

    def test_mapping_requires_all_inputs(self, svc: QualityAssessmentService) -> None:
        result = svc.assess(
            base_year=2024,
            current_year=2026,
            # Only partial mapping inputs
            mapping_coverage_pct=0.9,
            mapping_confidence_dist={"HIGH": 0.8, "MEDIUM": 0.2, "LOW": 0.0},
            # Missing: mapping_residual_pct, mapping_unresolved_pct, mapping_unresolved_spend_pct
        )

        assessed_dims = {da.dimension for da in result.dimension_assessments}
        assert QualityDimension.MAPPING not in assessed_dims


# ===================================================================
# Test 7: Model source nowcast warning
# ===================================================================


class TestModelSourceNowcastWarning:
    """model_source='balanced-nowcast' -> INFO warning present."""

    def test_model_source_nowcast_warning(self, svc: QualityAssessmentService) -> None:
        result = svc.assess(
            base_year=2024,
            current_year=2026,
            model_source="balanced-nowcast",
        )

        info_warnings = [
            w for w in result.warnings
            if w.severity == QualitySeverity.INFO
        ]
        assert len(info_warnings) > 0
        assert any("nowcast" in w.message.lower() or "balanced" in w.message.lower() for w in info_warnings)


# ===================================================================
# Test 8: Grade A with perfect inputs
# ===================================================================


class TestGradeAPerfectInputs:
    """All perfect inputs -> grade A."""

    def test_grade_a_perfect_inputs(self, svc: QualityAssessmentService) -> None:
        result = svc.assess(**_perfect_inputs())
        assert result.grade == QualityGrade.A


# ===================================================================
# Test 9: Grade degrades with issues
# ===================================================================


class TestGradeDegradesWithIssues:
    """Problematic inputs -> grade < A."""

    def test_grade_degrades_with_issues(self, svc: QualityAssessmentService) -> None:
        inputs = _perfect_inputs()
        # Vintage: 10 years old -> 0.2
        inputs["base_year"] = 2016
        # Mapping: low coverage -> lower score
        inputs["mapping_coverage_pct"] = 0.3
        inputs["mapping_confidence_dist"] = {"HIGH": 0.2, "MEDIUM": 0.3, "LOW": 0.5}
        inputs["mapping_residual_pct"] = 0.3
        inputs["mapping_unresolved_pct"] = 0.2
        inputs["mapping_unresolved_spend_pct"] = 3.0
        # Assumptions: low
        inputs["assumption_ranges_coverage_pct"] = 0.2
        inputs["assumption_approval_rate"] = 0.3
        # Constraints: mostly assumed
        inputs["constraint_confidence_summary"] = {"HARD": 1, "ESTIMATED": 1, "ASSUMED": 8}
        # Workforce: low confidence
        inputs["workforce_overall_confidence"] = "LOW"
        # Plausibility: only 40%
        inputs["plausibility_in_range_pct"] = 40.0
        inputs["plausibility_flagged_count"] = 10
        # Freshness: stale sources
        inputs["source_ages"] = [
            SourceAge("Old Table", 2000.0, SourceUpdateFrequency.ANNUAL),
        ]

        result = svc.assess(**inputs)
        assert result.grade != QualityGrade.A


# ===================================================================
# Test 10: No run_id
# ===================================================================


class TestNoRunId:
    """run_id=None -> assessment_version=1, run_id=None."""

    def test_no_run_id(self, svc: QualityAssessmentService) -> None:
        result = svc.assess(base_year=2024, current_year=2026)

        assert result.assessment_version == 1
        assert result.run_id is None


# ===================================================================
# Test 11: Plausibility requires both inputs
# ===================================================================


class TestPlausibilityRequiresBoth:
    """Only in_range_pct without flagged_count -> plausibility not scored."""

    def test_plausibility_requires_both(self, svc: QualityAssessmentService) -> None:
        result = svc.assess(
            base_year=2024,
            current_year=2026,
            plausibility_in_range_pct=95.0,
            # Missing: plausibility_flagged_count
        )

        assessed_dims = {da.dimension for da in result.dimension_assessments}
        assert QualityDimension.PLAUSIBILITY not in assessed_dims


# ===================================================================
# Test 12: Freshness with empty list -> not scored
# ===================================================================


class TestFreshnessEmptyList:
    """source_ages=[] -> not scored (not applicable)."""

    def test_freshness_empty_list(self, svc: QualityAssessmentService) -> None:
        result = svc.assess(
            base_year=2024,
            current_year=2026,
            source_ages=[],
        )

        assessed_dims = {da.dimension for da in result.dimension_assessments}
        assert QualityDimension.FRESHNESS not in assessed_dims
