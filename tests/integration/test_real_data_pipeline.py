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
# Class 4: TestSyntheticConstructorIsolation — glob-based curated-real guard
# ---------------------------------------------------------------------------


@pytest.mark.real_data
@pytest.mark.integration
class TestSyntheticConstructorIsolation:
    """Ensure no script in scripts/ can overwrite curated-real data.

    Uses glob to scan ALL scripts/*.py — new scripts are caught
    automatically without updating a hardcoded list.
    """

    @staticmethod
    def _get_all_scripts() -> list[Path]:
        """Return all .py scripts in scripts/, excluding package boilerplate."""
        scripts_dir = Path("scripts")
        return sorted(
            p for p in scripts_dir.glob("*.py")
            if p.name not in ("__init__.py", "__main__.py")
        )

    @staticmethod
    def _extract_code_strings(source: str) -> list[str]:
        """AST-parse source, return non-docstring string constants."""
        import ast

        tree = ast.parse(source)

        # Identify docstring node IDs
        docstring_ids: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
                if (node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    docstring_ids.add(id(node.body[0].value))

        return [
            node.value
            for node in ast.walk(tree)
            if (isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstring_ids)
        ]

    def test_no_script_overwrites_curated_real_filenames(self) -> None:
        """No script/*.py may produce JSON files whose names collide
        with curated_real manifest entries.

        Glob-based: catches any new script automatically.
        """
        manifest = load_manifest()
        curated_real_filenames: set[str] = {
            Path(e.path).name
            for e in manifest.datasets
            if e.resolved_source == "curated_real"
        }

        violations: list[str] = []

        for script in self._get_all_scripts():
            source = script.read_text(encoding="utf-8")
            try:
                code_strings = self._extract_code_strings(source)
            except SyntaxError:
                violations.append(f"{script}: SyntaxError — cannot parse")
                continue

            json_filenames = {s for s in code_strings if s.endswith(".json")}
            collisions = json_filenames & curated_real_filenames
            for c in sorted(collisions):
                violations.append(
                    f"{script}: output filename '{c}' collides with "
                    f"a curated_real manifest entry"
                )

        assert not violations, (
            "Scripts output filenames that collide with curated_real entries:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    @staticmethod
    def _is_synthetic_generator(script: Path, code_strings: list[str]) -> bool:
        """Identify scripts that generate synthetic data.

        A script is a synthetic generator if:
        - Its filename contains 'synthetic', OR
        - It uses 'synthetic' as a path component (e.g., Path(...) / 'synthetic'), OR
        - It writes .json files with 'synthetic' in the filename.

        Dict keys like 'is_synthetic' do NOT count — those are schema fields.
        """
        if "synthetic" in script.name.lower():
            return True
        if any(s == "synthetic" for s in code_strings):
            return True
        if any(
            "synthetic" in s.lower() and s.endswith(".json")
            for s in code_strings
        ):
            return True
        return False

    def test_synthetic_scripts_never_target_curated(self) -> None:
        """Scripts with synthetic data logic must target data/synthetic/,
        never data/curated/.

        Identifies synthetic scripts by filename, path components, or
        synthetic .json output filenames.
        Glob-based: catches any new synthetic script automatically.
        """
        violations: list[str] = []

        for script in self._get_all_scripts():
            source = script.read_text(encoding="utf-8")
            try:
                code_strings = self._extract_code_strings(source)
            except SyntaxError:
                continue

            # Is this a synthetic generator script?
            if not self._is_synthetic_generator(script, code_strings):
                continue

            # Check code-level strings for data/curated/ references
            for s in code_strings:
                if "data/curated" in s or "data\\curated" in s:
                    violations.append(
                        f"{script}: synthetic script references "
                        f"data/curated/: '{s}'"
                    )
                    break

            # Check for "curated" as Path() component
            if any(s == "curated" for s in code_strings):
                violations.append(
                    f"{script}: synthetic script uses 'curated' "
                    f"as path component"
                )

        assert not violations, (
            "Synthetic constructors target curated paths:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_synthetic_scripts_target_synthetic_dir(self) -> None:
        """Synthetic scripts must reference data/synthetic/ as output dir.

        Glob-based: catches any new synthetic script automatically.
        """
        violations: list[str] = []

        for script in self._get_all_scripts():
            source = script.read_text(encoding="utf-8")
            try:
                code_strings = self._extract_code_strings(source)
            except SyntaxError:
                continue

            # Is this a synthetic generator script?
            if not self._is_synthetic_generator(script, code_strings):
                continue

            # Must reference data/synthetic/ as output dir
            has_synthetic_dir = any(
                s == "synthetic" or "data/synthetic" in s
                or "data\\synthetic" in s
                for s in code_strings
            )
            if not has_synthetic_dir:
                violations.append(
                    f"{script}: synthetic script does not reference "
                    f"data/synthetic/ — output dir may be misconfigured"
                )

        assert not violations, (
            "Synthetic scripts missing data/synthetic/ reference:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
