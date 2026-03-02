"""D-5.1 Runtime enforcement: zero-synthetic across all API paths.

TDD tests for:
- Sandbox export blocked when quality/provenance missing
- Satellite loader default is not PREFER_REAL in runtime context
- Seed default profile is curated_real
"""

from uuid_extensions import uuid7

from src.export.orchestrator import (
    ExportOrchestrator,
    ExportRequest,
    ExportStatus,
)
from src.models.common import ExportMode


class TestSandboxBlocksMissingProvenance:
    """Sandbox must also block when quality/provenance is missing."""

    def test_sandbox_blocked_when_quality_missing(self):
        orch = ExportOrchestrator()
        request = ExportRequest(
            run_id=uuid7(),
            workspace_id=uuid7(),
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data={},
        )
        record = orch.execute(
            request=request, claims=[], quality_assessment=None,
        )
        assert record.status == ExportStatus.BLOCKED
        assert any(
            "provenance" in r.lower() or "quality" in r.lower()
            for r in record.blocking_reasons
        )


class TestSatelliteLoaderRuntimeDefault:
    """Runtime default must not be PREFER_REAL."""

    def test_default_data_mode_is_strict_real(self):
        """Verify the runtime-intended default is STRICT_REAL."""
        from src.data.real_io_loader import DataMode
        from src.data.workforce.satellite_coeff_loader import (
            RUNTIME_DATA_MODE,
        )
        assert RUNTIME_DATA_MODE == DataMode.STRICT_REAL


class TestSeedDefaultProfile:
    """Operational seed default must be curated_real."""

    def test_seed_default_is_curated_real(self):
        from scripts.seed import SEED_DEFAULT_PROFILE
        assert SEED_DEFAULT_PROFILE == "curated_real"
