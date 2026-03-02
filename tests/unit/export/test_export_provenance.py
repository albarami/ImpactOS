"""Tests for provenance wiring in ExportOrchestrator (D-5 Task 6).

Verifies that ExportOrchestrator enforces synthetic-fallback blocking
for both GOVERNED and SANDBOX exports when used_synthetic_fallback is True.
"""

from uuid import uuid4

from src.export.orchestrator import ExportOrchestrator, ExportRequest, ExportStatus
from src.models.common import ExportMode
from src.quality.models import RunQualityAssessment


def _make_request(mode: ExportMode = ExportMode.SANDBOX) -> ExportRequest:
    return ExportRequest(
        run_id=uuid4(),
        workspace_id=uuid4(),
        mode=mode,
        export_formats=["excel"],
        pack_data={"title": "Test"},
    )


class TestExportWithProvenance:
    def test_execute_accepts_quality_assessment(self) -> None:
        orch = ExportOrchestrator()
        assessment = RunQualityAssessment(
            assessment_version=1,
            data_mode="curated_real",
            used_synthetic_fallback=False,
        )
        result = orch.execute(
            request=_make_request(ExportMode.SANDBOX),
            claims=[],
            quality_assessment=assessment,
        )
        assert result.status == ExportStatus.COMPLETED

    def test_sandbox_with_synthetic_blocked(self) -> None:
        orch = ExportOrchestrator()
        assessment = RunQualityAssessment(
            assessment_version=1,
            data_mode="synthetic_fallback",
            used_synthetic_fallback=True,
            fallback_reason="No curated data",
        )
        result = orch.execute(
            request=_make_request(ExportMode.SANDBOX),
            claims=[],
            quality_assessment=assessment,
        )
        assert result.status == ExportStatus.BLOCKED
        assert any("synthetic" in r.lower() for r in result.blocking_reasons)

    def test_governed_with_synthetic_blocked(self) -> None:
        orch = ExportOrchestrator()
        assessment = RunQualityAssessment(
            assessment_version=1,
            data_mode="synthetic_fallback",
            used_synthetic_fallback=True,
            fallback_reason="No curated data",
        )
        result = orch.execute(
            request=_make_request(ExportMode.GOVERNED),
            claims=[],
            quality_assessment=assessment,
        )
        assert result.status == ExportStatus.BLOCKED
        assert any("synthetic" in r.lower() for r in result.blocking_reasons)

    def test_governed_with_curated_real_exports(self) -> None:
        orch = ExportOrchestrator()
        assessment = RunQualityAssessment(
            assessment_version=1,
            data_mode="curated_real",
            used_synthetic_fallback=False,
        )
        result = orch.execute(
            request=_make_request(ExportMode.GOVERNED),
            claims=[],
            quality_assessment=assessment,
        )
        assert result.status == ExportStatus.COMPLETED

    def test_execute_without_quality_assessment_backward_compat(self) -> None:
        orch = ExportOrchestrator()
        result = orch.execute(
            request=_make_request(ExportMode.SANDBOX),
            claims=[],
        )
        assert result.status == ExportStatus.BLOCKED
