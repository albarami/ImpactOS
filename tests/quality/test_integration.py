"""End-to-end integration tests for data quality automation (MVP-13 Task 10).

Exercises the full quality pipeline: ModelStore -> PlausibilityChecker ->
SourceFreshnessRegistry -> QualityAssessmentService -> SingleRunResult,
verifying that components compose correctly.

Deterministic -- no LLM calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.engine.batch import SingleRunResult
from src.engine.model_store import ModelStore
from src.models.common import MappingConfidenceBand, new_uuid7
from src.models.run import ResultSet, RunSnapshot
from src.observability.quality import QualityMetrics
from src.quality.models import (
    QualityDimension,
    QualityGrade,
    QualitySeverity,
    SourceAge,
    SourceUpdateFrequency,
)
from src.quality.nowcast import NowcastingService, TargetTotalProvenance
from src.quality.plausibility import PlausibilityChecker
from src.quality.service import QualityAssessmentService
from src.quality.source_registry import SourceFreshnessRegistry


# ===================================================================
# Helpers
# ===================================================================


def _make_snapshot() -> RunSnapshot:
    """Create a minimal RunSnapshot with dummy version refs."""
    return RunSnapshot(
        run_id=new_uuid7(),
        model_version_id=new_uuid7(),
        taxonomy_version_id=new_uuid7(),
        concordance_version_id=new_uuid7(),
        mapping_library_version_id=new_uuid7(),
        assumption_library_version_id=new_uuid7(),
        prompt_pack_version_id=new_uuid7(),
    )


def _make_result_set(run_id: UUID) -> ResultSet:
    """Create a minimal ResultSet for a given run_id."""
    return ResultSet(
        run_id=run_id,
        metric_type="total_output",
        values={"S01": 100.0, "S02": 200.0},
    )


def _register_2x2_model(store: ModelStore) -> tuple:
    """Register a simple 2x2 I-O model and return (model_version, loaded_model).

    Z = [[0.1, 0.2],
         [0.3, 0.1]]
    x = [1.0, 1.0]
    sector_codes = ["S01", "S02"]
    """
    Z = np.array([[0.1, 0.2], [0.3, 0.1]], dtype=np.float64)
    x = np.array([1.0, 1.0], dtype=np.float64)
    sector_codes = ["S01", "S02"]
    mv = store.register(Z=Z, x=x, sector_codes=sector_codes, base_year=2021, source="test")
    loaded = store.get(mv.model_version_id)
    return mv, loaded


# ===================================================================
# Test 1: SingleRunResult quality_assessment_id field
# ===================================================================


class TestSingleRunResultQualityField:
    """Verify the quality_assessment_id field on SingleRunResult."""

    def test_default_none(self) -> None:
        """SingleRunResult without quality_assessment_id has None."""
        snapshot = _make_snapshot()
        rs = _make_result_set(snapshot.run_id)
        result = SingleRunResult(snapshot=snapshot, result_sets=[rs])

        assert result.quality_assessment_id is None

    def test_with_assessment_id(self) -> None:
        """SingleRunResult with quality_assessment_id stores it."""
        snapshot = _make_snapshot()
        rs = _make_result_set(snapshot.run_id)
        assessment_id = new_uuid7()
        result = SingleRunResult(
            snapshot=snapshot,
            result_sets=[rs],
            quality_assessment_id=assessment_id,
        )

        assert result.quality_assessment_id == assessment_id
        assert isinstance(result.quality_assessment_id, UUID)


# ===================================================================
# Test 2: End-to-end pipeline
# ===================================================================


class TestEndToEndPipeline:
    """Full pipeline: ModelStore -> Plausibility -> Freshness -> Assess."""

    def test_full_pipeline(self) -> None:
        """Complete flow through all quality components."""
        # a. Create ModelStore, register 2x2 model
        store = ModelStore()
        mv, loaded = _register_2x2_model(store)

        # b. Run PlausibilityChecker on B matrix
        checker = PlausibilityChecker()
        benchmarks = {
            "S01": (1.0, 3.0),
            "S02": (1.0, 3.0),
        }
        plaus_result = checker.check(
            B_matrix=loaded.B,
            sector_codes=loaded.sector_codes,
            benchmarks=benchmarks,
            model_version_id=str(mv.model_version_id),
        )

        # c. Create SourceFreshnessRegistry with seed defaults
        registry = SourceFreshnessRegistry.with_seed_defaults()

        # d. Get source_ages from registry
        as_of = datetime(2026, 2, 28, tzinfo=timezone.utc)
        source_ages = registry.to_source_ages(as_of)

        # e. Run QualityAssessmentService.assess() with all inputs
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=mv.base_year,
            current_year=2026,
            mapping_coverage_pct=0.95,
            mapping_confidence_dist={"HIGH": 0.8, "MEDIUM": 0.15, "LOW": 0.05},
            mapping_residual_pct=0.05,
            mapping_unresolved_pct=0.02,
            mapping_unresolved_spend_pct=0.5,
            assumption_ranges_coverage_pct=0.9,
            assumption_approval_rate=0.85,
            constraint_confidence_summary={"HARD": 5, "ESTIMATED": 3, "ASSUMED": 2},
            workforce_overall_confidence="MEDIUM",
            plausibility_in_range_pct=plaus_result.multipliers_in_range_pct,
            plausibility_flagged_count=len(plaus_result.flagged_sectors),
            source_ages=source_ages,
            run_id=new_uuid7(),
        )

        # f. Assert: composite_score > 0, grade valid, 7 dimension assessments, all applicable
        assert assessment.composite_score > 0.0
        assert assessment.grade in list(QualityGrade)
        assert len(assessment.dimension_assessments) == 7

        for da in assessment.dimension_assessments:
            assert da.applicable is True

    def test_pipeline_with_missing_dimensions(self) -> None:
        """Only vintage + mapping -> partial assessment, completeness < 100%."""
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2021,
            current_year=2026,
            # Only mapping provided (in addition to vintage which is always scored)
            mapping_coverage_pct=0.9,
            mapping_confidence_dist={"HIGH": 0.7, "MEDIUM": 0.2, "LOW": 0.1},
            mapping_residual_pct=0.1,
            mapping_unresolved_pct=0.05,
            mapping_unresolved_spend_pct=1.0,
        )

        # Should have vintage + mapping + constraints (not applicable) + workforce (not applicable)
        assessed_dims = {da.dimension for da in assessment.dimension_assessments}
        assert QualityDimension.VINTAGE in assessed_dims
        assert QualityDimension.MAPPING in assessed_dims

        # Missing dimensions should exist (assumptions, plausibility, freshness not provided)
        assert QualityDimension.ASSUMPTIONS not in assessed_dims
        assert QualityDimension.PLAUSIBILITY not in assessed_dims
        assert QualityDimension.FRESHNESS not in assessed_dims

        # Completeness < 100% since not all dimensions are applicable
        assert assessment.completeness_pct < 100.0

    def test_assessment_stored_on_run_result(self) -> None:
        """Create assessment, attach assessment_id to SingleRunResult."""
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2024,
            current_year=2026,
            run_id=new_uuid7(),
        )

        snapshot = _make_snapshot()
        rs = _make_result_set(snapshot.run_id)
        run_result = SingleRunResult(
            snapshot=snapshot,
            result_sets=[rs],
            quality_assessment_id=assessment.assessment_id,
        )

        assert run_result.quality_assessment_id == assessment.assessment_id
        assert isinstance(run_result.quality_assessment_id, UUID)


# ===================================================================
# Test 3: Nowcast-then-assess
# ===================================================================


class TestNowcastThenAssess:
    """Create model -> nowcast -> approve -> assess with fresher model."""

    def test_nowcast_then_assess(self) -> None:
        """Nowcasting produces a fresher model that passes quality assessment."""
        # Create and register base model with larger totals relative to Z
        # (mirrors the pattern in test_nowcast.py to keep spectral radius < 1)
        store = ModelStore()
        Z = np.array([[10.0, 5.0], [3.0, 8.0]], dtype=np.float64)
        x = np.array([30.0, 20.0], dtype=np.float64)
        mv = store.register(
            Z=Z, x=x, sector_codes=["S01", "S02"], base_year=2021, source="test",
        )

        # Create nowcast service and nowcast to a newer year
        nowcast_svc = NowcastingService(model_store=store)
        target_row_totals = np.array([35.0, 22.0], dtype=np.float64)
        target_col_totals = np.array([35.0, 22.0], dtype=np.float64)
        provenance = [
            TargetTotalProvenance(
                sector_code="S01",
                target_value=35.0,
                source="GDP projection",
                evidence_refs=["ref-001"],
            ),
            TargetTotalProvenance(
                sector_code="S02",
                target_value=22.0,
                source="GDP projection",
                evidence_refs=["ref-002"],
            ),
        ]

        nowcast_result = nowcast_svc.create_nowcast(
            base_model_version_id=mv.model_version_id,
            target_row_totals=target_row_totals,
            target_col_totals=target_col_totals,
            target_year=2025,
            provenance=provenance,
        )

        # Approve the nowcast
        approved_mv = nowcast_svc.approve_nowcast(nowcast_result.nowcast_id)
        assert approved_mv.base_year == 2025

        # Assess quality with the nowcast model (fresher base_year)
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=approved_mv.base_year,
            current_year=2026,
            model_source=approved_mv.source,
            run_id=new_uuid7(),
        )

        # Assessment should work with the fresher base_year
        assert assessment.composite_score > 0.0
        assert assessment.grade in list(QualityGrade)

        # The vintage score should be better with a 2025 base_year (1yr gap)
        # than with the original 2021 base_year (5yr gap).
        vintage_da = next(
            da for da in assessment.dimension_assessments
            if da.dimension == QualityDimension.VINTAGE
        )
        assert vintage_da.score > 0.5  # 1-year-old model should score well

        # model_source='balanced-nowcast' should trigger an info warning
        info_warnings = [
            w for w in assessment.warnings
            if w.severity == QualitySeverity.INFO
        ]
        assert any(
            "nowcast" in w.message.lower() or "balanced" in w.message.lower()
            for w in info_warnings
        )


# ===================================================================
# Test 4: Governed export gate (advisory)
# ===================================================================


class TestGovernedExportGate:
    """Advisory warning checks for governed publication gate."""

    def test_advisory_warning_for_blockers(self) -> None:
        """Assessment with WAIVER_REQUIRED warnings has waiver_required_count > 0."""
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2024,
            current_year=2026,
            # Mapping with very high unresolved spend -> triggers WAIVER_REQUIRED
            mapping_coverage_pct=0.5,
            mapping_confidence_dist={"HIGH": 0.3, "MEDIUM": 0.3, "LOW": 0.4},
            mapping_residual_pct=0.2,
            mapping_unresolved_pct=0.15,
            mapping_unresolved_spend_pct=10.0,  # Way above waiver threshold
        )

        assert assessment.waiver_required_count > 0

        # Check that WAIVER_REQUIRED warnings exist in the warnings list
        waiver_warnings = [
            w for w in assessment.warnings
            if w.severity == QualitySeverity.WAIVER_REQUIRED
        ]
        assert len(waiver_warnings) > 0


# ===================================================================
# Test 5: Quality metrics integration
# ===================================================================


class TestQualityMetricsIntegration:
    """Use QualityMetrics.confidence_distribution() to feed quality assessment."""

    def test_mapping_confidence_from_quality_metrics(self) -> None:
        """Compute confidence dist via QualityMetrics, feed to assess()."""
        # Simulate a list of mapping confidence bands from an engagement
        confidences = [
            MappingConfidenceBand.HIGH,
            MappingConfidenceBand.HIGH,
            MappingConfidenceBand.HIGH,
            MappingConfidenceBand.MEDIUM,
            MappingConfidenceBand.LOW,
        ]

        # Compute confidence distribution using QualityMetrics
        conf_dist = QualityMetrics.confidence_distribution(confidences)

        # Verify the distribution is correct
        assert conf_dist["HIGH"] == pytest.approx(0.6)
        assert conf_dist["MEDIUM"] == pytest.approx(0.2)
        assert conf_dist["LOW"] == pytest.approx(0.2)

        # Feed the distribution into the quality assessment service
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2024,
            current_year=2026,
            mapping_coverage_pct=0.9,
            mapping_confidence_dist=conf_dist,
            mapping_residual_pct=0.05,
            mapping_unresolved_pct=0.03,
            mapping_unresolved_spend_pct=0.5,
        )

        # The mapping dimension should be assessed and reflect the confidence distribution
        mapping_da = next(
            da for da in assessment.dimension_assessments
            if da.dimension == QualityDimension.MAPPING
        )
        assert mapping_da.applicable is True
        assert mapping_da.score > 0.0

        # The HIGH confidence weight (0.3 * 0.6 = 0.18) should be part of the score
        # Full formula: 0.4*0.9 + 0.3*0.6 + 0.2*(1-0.05) + 0.1*(1-0.03) = 0.36+0.18+0.19+0.097 = 0.827
        assert mapping_da.score == pytest.approx(0.827, abs=0.01)
