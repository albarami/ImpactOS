"""D-5.1 Runtime enforcement: zero-synthetic across all API paths.

Tests:
- Sandbox + governed export blocked when quality/provenance missing
- Satellite loader function default is STRICT_REAL
- Satellite loader RUNTIME_DATA_MODE constant is STRICT_REAL
- Seed default profile is curated_real
- No runtime src/api/ module imports PREFER_REAL/SYNTHETIC_ONLY or fallback loaders
- DataMode enum documents PREFER_REAL/SYNTHETIC_ONLY as non-runtime
"""

import inspect
from pathlib import Path

from uuid_extensions import uuid7

from src.data.real_io_loader import DataMode
from src.export.orchestrator import (
    ExportOrchestrator,
    ExportRequest,
    ExportStatus,
)
from src.models.common import ExportMode


class TestExportBlocksMissingProvenance:
    """Both sandbox and governed block when quality/provenance missing."""

    def test_sandbox_blocked_when_quality_missing(self):
        orch = ExportOrchestrator()
        request = ExportRequest(
            run_id=uuid7(), workspace_id=uuid7(),
            mode=ExportMode.SANDBOX,
            export_formats=["excel"], pack_data={},
        )
        record = orch.execute(
            request=request, claims=[], quality_assessment=None,
        )
        assert record.status == ExportStatus.BLOCKED
        assert any(
            "provenance" in r.lower() or "quality" in r.lower()
            for r in record.blocking_reasons
        )

    def test_governed_blocked_when_quality_missing(self):
        orch = ExportOrchestrator()
        request = ExportRequest(
            run_id=uuid7(), workspace_id=uuid7(),
            mode=ExportMode.GOVERNED,
            export_formats=["excel"], pack_data={},
        )
        record = orch.execute(
            request=request, claims=[], quality_assessment=None,
        )
        assert record.status == ExportStatus.BLOCKED


class TestSatelliteLoaderRuntimeDefault:
    """Satellite loader defaults must be STRICT_REAL."""

    def test_runtime_constant_is_strict_real(self):
        from src.data.workforce.satellite_coeff_loader import (
            RUNTIME_DATA_MODE,
        )
        assert RUNTIME_DATA_MODE == DataMode.STRICT_REAL

    def test_function_default_is_strict_real(self):
        from src.data.workforce.satellite_coeff_loader import (
            load_satellite_coefficients,
        )
        sig = inspect.signature(load_satellite_coefficients)
        default = sig.parameters["data_mode"].default
        assert default == DataMode.STRICT_REAL


class TestIOLoaderRuntimeDefault:
    """IO loader strict function requires explicit mode (no default)."""

    def test_strict_loader_has_no_default_mode(self):
        from src.data.real_io_loader import load_real_saudi_io_strict
        sig = inspect.signature(load_real_saudi_io_strict)
        default = sig.parameters["mode"].default
        assert default is inspect.Parameter.empty


class TestNoSyntheticInRuntimeAPI:
    """Runtime API modules must not import fallback loaders or modes."""

    def test_api_modules_do_not_import_prefer_real(self):
        api_dir = Path("src/api")
        for py_file in api_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            assert "PREFER_REAL" not in content, (
                f"{py_file.name} references PREFER_REAL"
            )
            assert "SYNTHETIC_ONLY" not in content, (
                f"{py_file.name} references SYNTHETIC_ONLY"
            )

    def test_api_modules_do_not_import_fallback_loader(self):
        api_dir = Path("src/api")
        for py_file in api_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            assert "load_real_saudi_io(" not in content or \
                "load_real_saudi_io_strict" in content, (
                f"{py_file.name} imports non-runtime loader"
            )


class TestSeedDefaultProfile:
    """Operational seed default is curated_real."""

    def test_seed_default_is_curated_real(self):
        from scripts.seed import SEED_DEFAULT_PROFILE
        assert SEED_DEFAULT_PROFILE == "curated_real"


class TestDataModeDocumentation:
    """DataMode enum documents non-runtime modes clearly."""

    def test_prefer_real_is_non_runtime(self):
        assert "non-runtime" in DataMode.__doc__.lower() or \
            "dev/test" in DataMode.__doc__.lower()

