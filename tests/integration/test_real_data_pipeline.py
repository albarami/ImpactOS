"""Real-data integration test suite (D-5 Task 7).

End-to-end proof that curated data flows through the entire pipeline:
manifest -> loader -> engine -> validator -> quality -> export.

Verifies all D-5 Tasks 1-6 work together with committed curated fixtures.

NOTE: Tests that assert resolved_source == "curated_real" are marked xfail
because ALL current data is synthetic (produced by scripts/materialize_curated_data.py).
These tests document what D-5.1 must deliver — do NOT loosen the assertions.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from src.data.benchmark_validator import BenchmarkValidator
from src.data.manifest import get_dataset, load_manifest, verify_checksum
from src.data.real_io_loader import (
    DataMode,
    load_real_saudi_io_strict,
)
from src.data.workforce.satellite_coeff_loader import load_satellite_coefficients
from src.engine.model_store import ModelStore
from src.export.orchestrator import (
    ExportOrchestrator,
    ExportRequest,
    ExportStatus,
)
from src.models.common import ExportMode
from src.quality.models import RunQualityAssessment
from src.quality.service import QualityAssessmentService


# ---------------------------------------------------------------------------
# Class 1: TestRealDataPipeline — end-to-end curated data verification
# ---------------------------------------------------------------------------


@pytest.mark.real_data
@pytest.mark.integration
class TestRealDataPipeline:
    """Verify curated data flows end-to-end through the full pipeline."""

    # 1. Manifest exists and is parseable with >= 3 datasets
    def test_curated_manifest_exists(self) -> None:
        """Manifest file exists and is parseable with >= 3 datasets."""
        manifest = load_manifest()
        assert len(manifest.datasets) >= 3, (
            f"Expected >= 3 datasets in manifest, got {len(manifest.datasets)}"
        )

    # 2. Saudi IO curated fixture exists on disk
    def test_curated_io_fixture_exists(self) -> None:
        """Saudi IO curated fixture exists on disk."""
        assert Path("data/curated/saudi_io_kapsarc_2018.json").exists(), (
            "Curated IO fixture data/curated/saudi_io_kapsarc_2018.json missing"
        )

    # 3. STRICT_REAL loads curated data without fallback
    @pytest.mark.xfail(
        reason="No real upstream data committed yet — requires D-5.1",
    )
    def test_strict_real_does_not_fallback(self) -> None:
        """STRICT_REAL loads curated data without fallback, dataset_id populated."""
        manifest = load_manifest()
        result = load_real_saudi_io_strict(
            mode=DataMode.STRICT_REAL,
            year=2018,
            manifest=manifest,
        )
        assert result.provenance.resolved_source == "curated_real"
        assert not result.provenance.used_fallback
        assert result.provenance.dataset_id == "saudi_io_kapsarc_2018"

    # 4. Provenance exposes both requested and resolved years
    def test_requested_vs_resolved_year(self) -> None:
        """Provenance exposes both requested and resolved years; both match for 2018."""
        manifest = load_manifest()
        result = load_real_saudi_io_strict(
            mode=DataMode.STRICT_REAL,
            year=2018,
            manifest=manifest,
        )
        assert result.provenance.requested_year == 2018
        assert result.provenance.resolved_year == 2018

    # 5. Curated fixture checksum matches manifest
    def test_checksum_verified(self) -> None:
        """Curated fixture checksum matches manifest SHA-256."""
        manifest = load_manifest()
        entry = get_dataset(manifest, "saudi_io_kapsarc_2018")
        assert entry is not None, "Dataset 'saudi_io_kapsarc_2018' not in manifest"
        assert verify_checksum(Path(entry.path), entry.checksum_sha256), (
            f"Checksum mismatch for {entry.path}"
        )

    # 6. Curated IO model -> register -> Leontief solve -> positive multipliers
    def test_curated_model_registers_and_runs(self) -> None:
        """Curated IO model registers and Leontief solve produces valid multipliers."""
        result = load_real_saudi_io_strict(
            mode=DataMode.STRICT_REAL,
            year=2018,
        )
        store = ModelStore()
        mv = store.register(
            Z=result.io_data.Z,
            x=result.io_data.x,
            sector_codes=result.io_data.sector_codes,
            base_year=result.io_data.base_year,
            source="curated:test",
        )
        loaded = store.get(mv.model_version_id)
        # Every sector: multiplier (col sum of B) >= 1.0
        for i, code in enumerate(result.io_data.sector_codes):
            multiplier = float(loaded.B[:, i].sum())
            assert multiplier >= 1.0, (
                f"Sector {code} multiplier {multiplier} < 1.0"
            )

    # 7. BenchmarkValidator validates against curated benchmark data
    def test_benchmark_validator_uses_curated_benchmarks(self) -> None:
        """BenchmarkValidator validates engine output against curated benchmarks."""
        result = load_real_saudi_io_strict(
            mode=DataMode.STRICT_REAL,
            year=2018,
        )
        store = ModelStore()
        mv = store.register(
            Z=result.io_data.Z,
            x=result.io_data.x,
            sector_codes=result.io_data.sector_codes,
            base_year=result.io_data.base_year,
            source="curated:test",
        )
        loaded = store.get(mv.model_version_id)
        computed = {
            code: float(loaded.B[:, i].sum())
            for i, code in enumerate(result.io_data.sector_codes)
        }

        validator = BenchmarkValidator()
        benchmark = validator.load_benchmark_from_file(
            "data/curated/saudi_type1_multipliers_benchmark.json"
        )
        validation = validator.validate_multipliers(
            computed=computed, benchmark=benchmark,
        )
        assert validation.total_sectors > 0
        assert validation.sectors_within_tolerance > 0

    # 8. Quality assessment surfaces data_mode from provenance
    @pytest.mark.xfail(
        reason="No real upstream data committed yet — requires D-5.1",
    )
    def test_quality_assessment_records_data_mode(self) -> None:
        """Quality assessment surfaces data_mode from IODataProvenance."""
        manifest = load_manifest()
        result = load_real_saudi_io_strict(
            mode=DataMode.STRICT_REAL,
            year=2018,
            manifest=manifest,
        )
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2018,
            current_year=2026,
            data_provenance=result.provenance,
        )
        assert assessment.data_mode == "curated_real"
        assert assessment.used_synthetic_fallback is False

    # 9. Satellite coefficients prefer curated IO ratios
    def test_satellite_coefficients_prefer_curated(self) -> None:
        """load_satellite_coefficients() uses curated IO ratios, no synthetic fallback."""
        result = load_satellite_coefficients(year=2018)
        # With curated IO at data/curated/saudi_io_kapsarc_2018.json,
        # should use real ratios -- no "synthetic fallback" flags for import/VA ratios
        io_synthetic_flags = [
            f for f in result.provenance.fallback_flags
            if ("import_ratio" in f or "va_ratio" in f) and "synthetic" in f.lower()
        ]
        assert len(io_synthetic_flags) == 0, (
            f"Still using synthetic IO ratios: {io_synthetic_flags}"
        )

    # 10. Manifest classifies employment as curated_estimated (when real ILO data wired)
    @pytest.mark.xfail(
        reason="No real upstream data committed yet — requires D-5.1",
    )
    def test_employment_coefficients_classification_honest(self) -> None:
        """Manifest classifies employment coefficients as curated_estimated (requires real ILO data)."""
        manifest = load_manifest()
        entry = get_dataset(manifest, "saudi_employment_coefficients_2019")
        assert entry is not None, (
            "Dataset 'saudi_employment_coefficients_2019' not in manifest"
        )
        assert entry.resolved_source == "curated_estimated"
        assert entry.contains_assumed_components is True

    # 11. PREFER_REAL with missing curated data falls back with honest provenance
    def test_fallback_warns_explicitly(self) -> None:
        """PREFER_REAL with year=2050 (no curated file) falls back to synthetic."""
        result = load_real_saudi_io_strict(
            mode=DataMode.PREFER_REAL,
            year=2050,
        )
        assert result.provenance.resolved_source == "synthetic_fallback"
        assert result.provenance.used_fallback is True
        assert result.provenance.fallback_reason is not None

    # 12. SYNTHETIC_ONLY always returns synthetic, never curated
    def test_synthetic_only_never_uses_curated(self) -> None:
        """SYNTHETIC_ONLY always returns synthetic data even when curated exists."""
        result = load_real_saudi_io_strict(
            mode=DataMode.SYNTHETIC_ONLY,
            year=2018,
        )
        assert result.provenance.resolved_source == "synthetic_only"
        assert result.provenance.dataset_id is None


# ---------------------------------------------------------------------------
# Class 2: TestFallbackHonesty — fallback provenance and governance tests
# ---------------------------------------------------------------------------


@pytest.mark.real_data
@pytest.mark.integration
class TestFallbackHonesty:
    """Verify fallback provenance is honest and governance enforces data quality."""

    # 1. PREFER_REAL always returns provenance regardless of path
    def test_prefer_real_returns_provenance(self) -> None:
        """PREFER_REAL always returns provenance regardless of resolution path."""
        result = load_real_saudi_io_strict(
            mode=DataMode.PREFER_REAL,
            year=2018,
        )
        assert result.provenance is not None
        assert result.provenance.data_mode == DataMode.PREFER_REAL

    # 2. STRICT_REAL raises FileNotFoundError if curated absent
    def test_strict_real_raises_on_missing(self) -> None:
        """STRICT_REAL raises FileNotFoundError when curated data is absent."""
        with tempfile.TemporaryDirectory() as td:
            with pytest.raises(FileNotFoundError):
                load_real_saudi_io_strict(
                    mode=DataMode.STRICT_REAL,
                    year=2018,
                    curated_dir=td,
                )

    # 3. Governed export with synthetic data is BLOCKED
    def test_export_with_synthetic_requires_waiver(self) -> None:
        """Governed export with synthetic fallback data is BLOCKED."""
        assessment = RunQualityAssessment(
            assessment_version=1,
            data_mode="synthetic_fallback",
            used_synthetic_fallback=True,
            fallback_reason="No curated data",
        )
        orch = ExportOrchestrator()
        request = ExportRequest(
            run_id=uuid4(),
            workspace_id=uuid4(),
            mode=ExportMode.GOVERNED,
            export_formats=["excel"],
            pack_data={"title": "Test"},
        )
        result = orch.execute(
            request=request,
            claims=[],
            quality_assessment=assessment,
        )
        assert result.status == ExportStatus.BLOCKED
        assert any("synthetic" in r.lower() for r in result.blocking_reasons)


# ---------------------------------------------------------------------------
# Class 3: TestDataLineageHonesty — no curated_real from synthetic sources
# ---------------------------------------------------------------------------


# Artifacts known to be produced by scripts/materialize_curated_data.py.
# If a manifest entry points to one of these files AND claims curated_real,
# the system is lying about data provenance.
_MATERIALIZER_PRODUCED_FILES = {
    "saudi_io_kapsarc_2018.json",
    "saudi_type1_multipliers_benchmark.json",
    "saudi_employment_coefficients_2019.json",
}


@pytest.mark.real_data
@pytest.mark.integration
class TestDataLineageHonesty:
    """Ensure no curated_real entry was produced by a synthetic constructor."""

    def test_no_curated_real_from_materializer(self) -> None:
        """No manifest entry with resolved_source='curated_real' may point
        to a file produced by scripts/materialize_curated_data.py.

        This prevents the exact failure mode D-5 was designed to catch:
        labeling synthetic data as curated_real.
        """
        manifest = load_manifest()
        violations: list[str] = []

        for entry in manifest.datasets:
            if entry.resolved_source == "curated_real":
                filename = Path(entry.path).name
                if filename in _MATERIALIZER_PRODUCED_FILES:
                    violations.append(
                        f"{entry.dataset_id}: claims curated_real but "
                        f"{filename} is produced by materialize_curated_data.py"
                    )

        assert not violations, (
            "Manifest entries claim curated_real for materializer-produced files:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_curated_real_requires_source_not_materializer(self) -> None:
        """Any curated_real entry must have a source field that does NOT
        reference scripts/materialize_curated_data.py.
        """
        manifest = load_manifest()
        violations: list[str] = []

        for entry in manifest.datasets:
            if entry.resolved_source == "curated_real":
                if "materialize" in entry.source.lower():
                    violations.append(
                        f"{entry.dataset_id}: claims curated_real but source "
                        f"references materializer: '{entry.source}'"
                    )

        assert not violations, (
            "Manifest entries claim curated_real but source references materializer:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_curated_real_file_has_non_synthetic_source_field(self) -> None:
        """Any curated_real entry's JSON artifact must have a source field
        that is NOT 'synthetic_materialized'.
        """
        manifest = load_manifest()
        violations: list[str] = []

        for entry in manifest.datasets:
            if entry.resolved_source != "curated_real":
                continue

            artifact_path = Path(entry.path)
            if not artifact_path.exists():
                continue

            data = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact_source = data.get("source", "")
            if "synthetic" in artifact_source.lower():
                violations.append(
                    f"{entry.dataset_id}: claims curated_real but artifact "
                    f"source='{artifact_source}'"
                )

        assert not violations, (
            "Curated_real artifacts contain synthetic source markers:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
