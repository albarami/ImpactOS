"""Tests for provenance fields on RunQualityAssessment + service integration.

D-5 Task 5: Verifies that RunQualityAssessment carries data-provenance
metadata and that QualityAssessmentService.assess() propagates IODataProvenance
into the returned assessment.
"""

from __future__ import annotations

from src.data.real_io_loader import DataMode, IODataProvenance
from src.quality.models import (
    QualitySeverity,
    RunQualityAssessment,
)
from src.quality.service import QualityAssessmentService


class TestQualityProvenanceFields:
    """RunQualityAssessment model-level provenance field tests."""

    def test_run_quality_assessment_has_provenance_fields(self) -> None:
        assessment = RunQualityAssessment(
            assessment_version=1,
            data_mode="curated_real",
            used_synthetic_fallback=False,
            data_source_id="saudi_io_kapsarc_2018",
            checksum_verified=True,
        )
        assert assessment.data_mode == "curated_real"
        assert assessment.used_synthetic_fallback is False
        assert assessment.data_source_id == "saudi_io_kapsarc_2018"

    def test_provenance_fields_default_to_none_false(self) -> None:
        assessment = RunQualityAssessment(assessment_version=1)
        assert assessment.data_mode is None
        assert assessment.used_synthetic_fallback is False
        assert assessment.fallback_reason is None
        assert assessment.data_source_id is None
        assert assessment.checksum_verified is False


class TestQualityServiceWithProvenance:
    """QualityAssessmentService.assess() provenance integration tests."""

    def test_assess_accepts_data_provenance(self) -> None:
        svc = QualityAssessmentService()
        prov = IODataProvenance(
            data_mode=DataMode.STRICT_REAL,
            resolved_source="curated_real",
            used_fallback=False,
            dataset_id="saudi_io_kapsarc_2018",
            requested_year=2018,
            resolved_year=2018,
            checksum_verified=True,
            fallback_reason=None,
            manifest_entry=None,
        )
        result = svc.assess(base_year=2018, current_year=2026, data_provenance=prov)
        assert result.data_mode == "curated_real"
        assert result.used_synthetic_fallback is False
        assert result.data_source_id == "saudi_io_kapsarc_2018"
        assert result.checksum_verified is True

    def test_assess_with_synthetic_fallback_adds_warning(self) -> None:
        svc = QualityAssessmentService()
        prov = IODataProvenance(
            data_mode=DataMode.PREFER_REAL,
            resolved_source="synthetic_fallback",
            used_fallback=True,
            dataset_id=None,
            requested_year=2019,
            resolved_year=None,
            checksum_verified=False,
            fallback_reason="No curated IO model found",
            manifest_entry=None,
        )
        result = svc.assess(base_year=2018, current_year=2026, data_provenance=prov)
        assert result.used_synthetic_fallback is True
        assert result.data_mode == "synthetic_fallback"
        fallback_warnings = [
            w for w in result.warnings if "synthetic" in w.message.lower()
        ]
        assert len(fallback_warnings) > 0
        assert any(
            w.severity == QualitySeverity.WAIVER_REQUIRED for w in fallback_warnings
        )

    def test_assess_without_provenance_backward_compat(self) -> None:
        svc = QualityAssessmentService()
        result = svc.assess(base_year=2018, current_year=2026)
        assert result.data_mode is None
        assert result.used_synthetic_fallback is False
