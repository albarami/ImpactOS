"""D-5.1 Tests: Provenance into quality + export gate.

Zero-synthetic runtime: both sandbox and governed block synthetic provenance.
Governed also blocks when quality assessment is missing.
"""

from uuid_extensions import uuid7

from src.data.real_io_loader import IODataProvenance, DataMode
from src.export.orchestrator import (
    ExportOrchestrator,
    ExportRequest,
    ExportStatus,
)
from src.models.common import ExportMode
from src.quality.models import RunQualityAssessment
from src.quality.service import QualityAssessmentService


class TestQualityServiceProvenance:
    """Quality service propagates provenance fields into assessment."""

    def test_real_provenance_flows_through(self):
        svc = QualityAssessmentService()
        prov = IODataProvenance(
            data_mode=DataMode.STRICT_REAL,
            resolved_source="curated_real",
            used_fallback=False,
            dataset_id="saudi_io_kapsarc_2018",
            requested_year=2019,
            resolved_year=2018,
            checksum_verified=True,
            fallback_reason=None,
            manifest_entry=None,
        )
        result = svc.assess(
            base_year=2018, current_year=2026, data_provenance=prov,
        )
        assert result.data_mode == "curated_real"
        assert result.used_synthetic_fallback is False
        assert result.data_source_id == "saudi_io_kapsarc_2018"
        assert result.checksum_verified is True

    def test_synthetic_fallback_sets_flag_and_warning(self):
        svc = QualityAssessmentService()
        prov = IODataProvenance(
            data_mode=DataMode.PREFER_REAL,
            resolved_source="synthetic_fallback",
            used_fallback=True,
            dataset_id=None,
            requested_year=2019,
            resolved_year=2019,
            checksum_verified=False,
            fallback_reason="Curated not found",
            manifest_entry=None,
        )
        result = svc.assess(
            base_year=2019, current_year=2026, data_provenance=prov,
        )
        assert result.used_synthetic_fallback is True
        waiver_warnings = [
            w for w in result.warnings
            if w.severity.value == "WAIVER_REQUIRED"
        ]
        assert len(waiver_warnings) >= 1


class TestExportGateZeroSynthetic:
    """Both sandbox and governed block synthetic provenance in runtime."""

    def _make_request(self, mode: ExportMode) -> ExportRequest:
        return ExportRequest(
            run_id=uuid7(),
            workspace_id=uuid7(),
            mode=mode,
            export_formats=["excel"],
            pack_data={},
        )

    def test_governed_blocked_with_synthetic(self):
        orch = ExportOrchestrator()
        quality = RunQualityAssessment.model_construct(
            used_synthetic_fallback=True,
        )
        record = orch.execute(
            request=self._make_request(ExportMode.GOVERNED),
            claims=[],
            quality_assessment=quality,
        )
        assert record.status == ExportStatus.BLOCKED
        assert any("synthetic" in r.lower() for r in record.blocking_reasons)

    def test_sandbox_blocked_with_synthetic(self):
        """Sandbox must also reject synthetic provenance in runtime."""
        orch = ExportOrchestrator()
        quality = RunQualityAssessment.model_construct(
            used_synthetic_fallback=True,
        )
        record = orch.execute(
            request=self._make_request(ExportMode.SANDBOX),
            claims=[],
            quality_assessment=quality,
        )
        assert record.status == ExportStatus.BLOCKED
        assert any("synthetic" in r.lower() for r in record.blocking_reasons)

    def test_governed_blocked_when_quality_missing(self):
        orch = ExportOrchestrator()
        record = orch.execute(
            request=self._make_request(ExportMode.GOVERNED),
            claims=[],
            quality_assessment=None,
        )
        assert record.status == ExportStatus.BLOCKED

    def test_governed_allowed_with_real_data(self):
        orch = ExportOrchestrator()
        quality = RunQualityAssessment.model_construct(
            used_synthetic_fallback=False,
        )
        record = orch.execute(
            request=self._make_request(ExportMode.GOVERNED),
            claims=[],
            quality_assessment=quality,
        )
        assert record.status == ExportStatus.COMPLETED

    def test_sandbox_allowed_with_real_data(self):
        orch = ExportOrchestrator()
        quality = RunQualityAssessment.model_construct(
            used_synthetic_fallback=False,
        )
        record = orch.execute(
            request=self._make_request(ExportMode.SANDBOX),
            claims=[],
            quality_assessment=quality,
        )
        assert record.status == ExportStatus.COMPLETED
