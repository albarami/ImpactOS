"""Real-data integration test suite (D-5 Task 7).

End-to-end proof that curated data flows through the entire pipeline:
manifest -> loader -> engine -> validator -> quality -> export.

Verifies all D-5 Tasks 1-6 work together with committed curated fixtures.

D-5.1 delivered real upstream data from KAPSARC, ILO, and World Bank.
All curated_real assertions now pass against genuine data.
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
# Class 3: TestDataLineageHonesty — curated_real must trace to data/raw/
# ---------------------------------------------------------------------------


# Known real upstream sources and their expected raw data directories.
# Every curated_real manifest entry must trace to one of these.
_REAL_UPSTREAM_SOURCES = {
    "KAPSARC": Path("data/raw/kapsarc"),
    "ILO": Path("data/raw/ilo"),
    "World Bank": Path("data/raw/worldbank"),
    "WDI": Path("data/raw/worldbank"),
}


@pytest.mark.real_data
@pytest.mark.integration
class TestDataLineageHonesty:
    """Ensure every curated_real entry traces to committed data/raw/ artifacts."""

    def test_curated_real_traces_to_raw_data(self) -> None:
        """Every curated_real manifest entry must have a corresponding
        committed data/raw/ directory from a known upstream source.

        This is the primary lineage guard: curated_real means the data
        was fetched from a real API (KAPSARC, ILO, WDI) and the raw
        response is committed in data/raw/.
        """
        manifest = load_manifest()
        violations: list[str] = []

        for entry in manifest.datasets:
            if entry.resolved_source != "curated_real":
                continue

            # Check that at least one known upstream source is referenced
            source_lower = entry.source.lower()
            matched_raw_dir = None
            for source_name, raw_dir in _REAL_UPSTREAM_SOURCES.items():
                if source_name.lower() in source_lower:
                    matched_raw_dir = raw_dir
                    break

            if matched_raw_dir is None:
                violations.append(
                    f"{entry.dataset_id}: claims curated_real but source "
                    f"'{entry.source}' does not reference a known upstream "
                    f"({', '.join(_REAL_UPSTREAM_SOURCES.keys())})"
                )
                continue

            # Verify the raw data directory exists and has files
            if not matched_raw_dir.exists():
                violations.append(
                    f"{entry.dataset_id}: claims curated_real from "
                    f"{matched_raw_dir} but that directory does not exist"
                )
            elif not any(matched_raw_dir.iterdir()):
                violations.append(
                    f"{entry.dataset_id}: claims curated_real from "
                    f"{matched_raw_dir} but that directory is empty"
                )

        assert not violations, (
            "Curated_real entries without raw data lineage:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_curated_real_source_not_synthetic(self) -> None:
        """Any curated_real entry must have a source field that does NOT
        reference synthetic generators or materializers.
        """
        manifest = load_manifest()
        violations: list[str] = []
        synthetic_markers = {"synthetic", "materialize", "generated", "hardcoded"}

        for entry in manifest.datasets:
            if entry.resolved_source == "curated_real":
                source_lower = entry.source.lower()
                for marker in synthetic_markers:
                    if marker in source_lower:
                        violations.append(
                            f"{entry.dataset_id}: claims curated_real but source "
                            f"contains '{marker}': '{entry.source}'"
                        )
                        break

        assert not violations, (
            "Manifest entries claim curated_real but reference synthetic sources:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_curated_real_file_has_non_synthetic_source_field(self) -> None:
        """Any curated_real entry's JSON artifact must have a source field
        that is NOT 'synthetic_materialized' or 'synthetic_generated'.
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

    def test_curated_real_not_in_synthetic_dir(self) -> None:
        """No curated_real entry may point to a file in data/synthetic/.

        Curated real data lives in data/curated/; synthetic fixtures
        live in data/synthetic/. These must never be confused.
        """
        manifest = load_manifest()
        violations: list[str] = []

        for entry in manifest.datasets:
            if entry.resolved_source == "curated_real":
                if "data/synthetic" in entry.path.replace("\\", "/"):
                    violations.append(
                        f"{entry.dataset_id}: claims curated_real but "
                        f"path is in data/synthetic/: '{entry.path}'"
                    )

        assert not violations, (
            "Curated_real entries point to data/synthetic/:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


# ---------------------------------------------------------------------------
# Class 4: TestSyntheticConstructorIsolation — prevent overwrite of real data
# ---------------------------------------------------------------------------


@pytest.mark.real_data
@pytest.mark.integration
class TestSyntheticConstructorIsolation:
    """Ensure synthetic constructors cannot target curated-real paths.

    Scans scripts/generate_synthetic_fixtures.py for output paths and
    verifies none of them collide with curated_real manifest entries.
    This is a CI-safe test that prevents the D-5.0 failure mode:
    running a synthetic constructor that overwrites real upstream data.
    """

    _SYNTHETIC_SCRIPTS = [
        Path("scripts/generate_synthetic_fixtures.py"),
    ]

    def test_synthetic_scripts_never_target_curated_real(self) -> None:
        """Synthetic constructor output paths must not collide with
        any manifest entry that has resolved_source='curated_real'.

        Parses the script source to extract all file paths it writes to,
        then checks none of them appear in manifest.json as curated_real.
        """
        import ast
        import re

        manifest = load_manifest()
        curated_real_paths: set[str] = set()
        for entry in manifest.datasets:
            if entry.resolved_source == "curated_real":
                curated_real_paths.add(Path(entry.path).name)

        violations: list[str] = []

        for script_path in self._SYNTHETIC_SCRIPTS:
            if not script_path.exists():
                continue

            source = script_path.read_text(encoding="utf-8")

            # Parse AST to extract string literals from CODE (not docstrings)
            try:
                tree = ast.parse(source)
            except SyntaxError:
                violations.append(
                    f"{script_path}: SyntaxError — cannot parse"
                )
                continue

            # Identify docstring nodes (module/class/function body[0])
            docstring_ids: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                    if (node.body
                            and isinstance(node.body[0], ast.Expr)
                            and isinstance(node.body[0].value, ast.Constant)
                            and isinstance(node.body[0].value.value, str)):
                        docstring_ids.add(id(node.body[0].value))

            # Collect non-docstring string constants
            code_strings: list[str] = []
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant)
                        and isinstance(node.value, str)
                        and id(node) not in docstring_ids):
                    code_strings.append(node.value)

            # Strategy 1: Check for code-level paths referencing data/curated/
            for s in code_strings:
                if "data/curated" in s or "data\\curated" in s:
                    violations.append(
                        f"{script_path}: code string literal references "
                        f"data/curated/: '{s}' — synthetic constructors "
                        f"must write to data/synthetic/ only"
                    )
                    break
            # Also check for "curated" as a Path() component
            curated_component = [
                s for s in code_strings
                if s == "curated"
            ]
            if curated_component:
                violations.append(
                    f"{script_path}: contains string 'curated' as "
                    f"path component — synthetic constructors must "
                    f"write to data/synthetic/ only"
                )

            # Strategy 2: Check for filename collisions with curated_real entries
            json_filenames = {
                s for s in code_strings
                if s.endswith(".json")
            }
            collisions = json_filenames & curated_real_paths
            for collision in sorted(collisions):
                violations.append(
                    f"{script_path}: output filename '{collision}' collides "
                    f"with a curated_real manifest entry"
                )

        assert not violations, (
            "Synthetic constructors target curated-real paths:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_synthetic_scripts_write_to_synthetic_dir(self) -> None:
        """Synthetic constructors must target data/synthetic/, not data/curated/.

        Verifies the output directory constant in each script points to
        data/synthetic/.
        """
        import re

        violations: list[str] = []

        for script_path in self._SYNTHETIC_SCRIPTS:
            if not script_path.exists():
                continue

            source = script_path.read_text(encoding="utf-8")

            # Check that the script defines an output dir pointing to synthetic
            has_synthetic_dir = bool(re.search(
                r'["\']synthetic["\']|data.*synthetic', source,
            ))
            has_curated_dir_output = bool(re.search(
                r'(?:CURATED_DIR|data.*curated).*(?:write_text|open\(|mkdir)',
                source,
            ))

            if has_curated_dir_output:
                violations.append(
                    f"{script_path}: appears to write to data/curated/ — "
                    f"synthetic output must go to data/synthetic/"
                )

            if not has_synthetic_dir:
                violations.append(
                    f"{script_path}: does not reference data/synthetic/ — "
                    f"synthetic output directory may be misconfigured"
                )

        assert not violations, (
            "Synthetic constructor directory violations:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
