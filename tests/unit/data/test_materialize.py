"""Tests for materialized curated data artifacts (D-5 Task 3).

Validates the structure and content of:
  - saudi_io_kapsarc_2018.json
  - saudi_type1_multipliers_benchmark.json
  - saudi_employment_coefficients_2019.json
  - manifest.json checksums
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CURATED_DIR = PROJECT_ROOT / "data" / "curated"
IO_PATH = CURATED_DIR / "saudi_io_kapsarc_2018.json"
BENCHMARK_PATH = CURATED_DIR / "saudi_type1_multipliers_benchmark.json"
EMPLOYMENT_PATH = CURATED_DIR / "saudi_employment_coefficients_2019.json"
MANIFEST_PATH = CURATED_DIR / "manifest.json"

ISIC_SECTIONS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def io_data() -> dict:
    """Load the IO model JSON."""
    return json.loads(IO_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def benchmark_data() -> dict:
    """Load the benchmark multipliers JSON."""
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def employment_data() -> dict:
    """Load the employment coefficients JSON."""
    return json.loads(EMPLOYMENT_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def manifest_data() -> dict:
    """Load the manifest JSON."""
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


# ===========================================================================
# 1. IO fixture tests
# ===========================================================================


class TestIOFixture:
    """Tests for saudi_io_kapsarc_2018.json."""

    def test_io_fixture_has_required_fields(self, io_data: dict) -> None:
        """Verify sector_codes, Z, x, base_year, source fields exist."""
        assert "sector_codes" in io_data
        assert "Z" in io_data
        assert "x" in io_data
        assert "base_year" in io_data
        assert "source" in io_data

    def test_io_fixture_filename_matches_loader_pattern(self) -> None:
        """Filename is saudi_io_kapsarc_2018.json — matches what loader searches for."""
        assert IO_PATH.name == "saudi_io_kapsarc_2018.json"
        assert IO_PATH.exists()

    def test_io_fixture_has_20_sectors(self, io_data: dict) -> None:
        """IO model has exactly 20 ISIC sections A-T."""
        assert io_data["sector_codes"] == ISIC_SECTIONS
        assert len(io_data["sector_codes"]) == 20

    def test_io_fixture_z_is_square_20x20(self, io_data: dict) -> None:
        """Z matrix is a 20x20 square matrix."""
        Z = np.array(io_data["Z"])
        assert Z.shape == (20, 20)

    def test_io_fixture_x_has_20_elements(self, io_data: dict) -> None:
        """x vector has 20 elements."""
        x = np.array(io_data["x"])
        assert x.shape == (20,)

    def test_io_fixture_base_year_is_2018(self, io_data: dict) -> None:
        """Base year is 2018."""
        assert io_data["base_year"] == 2018

    def test_io_fixture_source_is_kapsarc(self, io_data: dict) -> None:
        """Source field indicates KAPSARC/GASTAT origin."""
        assert "kapsarc" in io_data["source"].lower()

    def test_io_fixture_z_nonnegative(self, io_data: dict) -> None:
        """All Z matrix entries are non-negative."""
        Z = np.array(io_data["Z"])
        assert np.all(Z >= 0)

    def test_io_fixture_x_positive(self, io_data: dict) -> None:
        """All gross output values are positive."""
        x = np.array(io_data["x"])
        assert np.all(x > 0)

    def test_io_fixture_total_output_realistic(self, io_data: dict) -> None:
        """Total gross output is in a realistic range (~2-3 trillion SAR)."""
        x = np.array(io_data["x"])
        total = x.sum()
        assert 2_000_000 < total < 3_500_000  # SAR millions

    def test_io_fixture_oil_sector_dominant(self, io_data: dict) -> None:
        """Sector B (Mining/Oil) is the largest sector."""
        x = np.array(io_data["x"])
        sector_b_idx = io_data["sector_codes"].index("B")
        assert x[sector_b_idx] == x.max()

    def test_io_fixture_spectral_radius_below_one(self, io_data: dict) -> None:
        """Spectral radius of A is < 1 (productivity condition)."""
        Z = np.array(io_data["Z"])
        x = np.array(io_data["x"])
        A = Z / x[np.newaxis, :]
        eigenvalues = np.linalg.eigvals(A)
        spectral_radius = float(np.max(np.abs(eigenvalues)))
        assert spectral_radius < 1.0

    def test_io_fixture_positive_value_added(self, io_data: dict) -> None:
        """All sectors have positive value-added (column sums of A < 1)."""
        Z = np.array(io_data["Z"])
        x = np.array(io_data["x"])
        A = Z / x[np.newaxis, :]
        col_sums = A.sum(axis=0)
        assert np.all(col_sums < 1.0)

    def test_io_fixture_has_sector_count(self, io_data: dict) -> None:
        """IO model includes sector_count field."""
        assert io_data.get("sector_count") == 20

    def test_io_fixture_loads_with_engine_loader(self) -> None:
        """IO model loads successfully with the engine's JSON loader."""
        from src.data.io_loader import load_from_json

        model = load_from_json(str(IO_PATH))
        assert model.base_year == 2018
        assert len(model.sector_codes) == 20
        assert model.Z.shape == (20, 20)


# ===========================================================================
# 2. Benchmark tests
# ===========================================================================


class TestBenchmark:
    """Tests for saudi_type1_multipliers_benchmark.json."""

    def test_benchmark_has_sectors_format(self, benchmark_data: dict) -> None:
        """Verify {"sectors": [...]} format with sector_code + output_multiplier."""
        assert "sectors" in benchmark_data
        sectors = benchmark_data["sectors"]
        assert isinstance(sectors, list)
        assert len(sectors) == 20

        for entry in sectors:
            assert "sector_code" in entry
            assert "output_multiplier" in entry
            assert isinstance(entry["sector_code"], str)
            assert isinstance(entry["output_multiplier"], (int, float))

    def test_benchmark_sector_codes_match_isic(self, benchmark_data: dict) -> None:
        """Benchmark sectors match ISIC sections A-T."""
        codes = [s["sector_code"] for s in benchmark_data["sectors"]]
        assert codes == ISIC_SECTIONS

    def test_benchmark_multipliers_greater_than_one(self, benchmark_data: dict) -> None:
        """All Type I output multipliers are >= 1.0 (mathematical requirement)."""
        for entry in benchmark_data["sectors"]:
            assert entry["output_multiplier"] >= 1.0, (
                f"Sector {entry['sector_code']} has multiplier "
                f"{entry['output_multiplier']} < 1.0"
            )

    def test_benchmark_multipliers_reasonable_range(self, benchmark_data: dict) -> None:
        """All multipliers are in reasonable range [1.0, 5.0]."""
        for entry in benchmark_data["sectors"]:
            assert 1.0 <= entry["output_multiplier"] <= 5.0, (
                f"Sector {entry['sector_code']} has multiplier "
                f"{entry['output_multiplier']} outside [1.0, 5.0]"
            )

    def test_benchmark_loads_with_validator(self) -> None:
        """Benchmark loads with BenchmarkValidator.load_benchmark_from_file()."""
        from src.data.benchmark_validator import BenchmarkValidator

        validator = BenchmarkValidator()
        result = validator.load_benchmark_from_file(str(BENCHMARK_PATH))
        assert isinstance(result, dict)
        assert len(result) == 20
        assert "A" in result
        assert "B" in result
        assert all(v >= 1.0 for v in result.values())


# ===========================================================================
# 3. Employment coefficients tests
# ===========================================================================


class TestEmploymentCoefficients:
    """Tests for saudi_employment_coefficients_2019.json."""

    def test_employment_uses_existing_format(self, employment_data: dict) -> None:
        """Verify coefficients, year, sector_code, jobs_per_unit_output, source fields."""
        assert "coefficients" in employment_data
        assert "year" in employment_data
        coefficients = employment_data["coefficients"]
        assert isinstance(coefficients, list)
        assert len(coefficients) == 20

        for entry in coefficients:
            assert "sector_code" in entry
            assert "jobs_per_unit_output" in entry
            assert "source" in entry
            assert isinstance(entry["jobs_per_unit_output"], (int, float))
            assert entry["jobs_per_unit_output"] > 0

    def test_employment_year_is_2019(self, employment_data: dict) -> None:
        """Employment coefficients are for year 2019."""
        assert employment_data["year"] == 2019

    def test_employment_has_provenance(self, employment_data: dict) -> None:
        """Employment data includes _provenance block (Amendment 4)."""
        assert "_provenance" in employment_data
        prov = employment_data["_provenance"]
        assert "builder" in prov
        assert "method" in prov

    def test_employment_sector_codes_match_isic(self, employment_data: dict) -> None:
        """Employment coefficients cover all ISIC sections A-T."""
        codes = [c["sector_code"] for c in employment_data["coefficients"]]
        assert codes == ISIC_SECTIONS

    def test_employment_loads_with_builder(self) -> None:
        """Employment coefficients load with load_employment_coefficients()."""
        from src.data.workforce.build_employment_coefficients import (
            load_employment_coefficients,
        )

        result = load_employment_coefficients(str(EMPLOYMENT_PATH))
        assert result.year == 2019
        assert len(result.coefficients) == 20

    def test_employment_has_quality_confidence(self, employment_data: dict) -> None:
        """Each coefficient has quality_confidence field."""
        for entry in employment_data["coefficients"]:
            assert "quality_confidence" in entry
            assert entry["quality_confidence"] in ("high", "medium", "low")


# ===========================================================================
# 4. Manifest tests
# ===========================================================================


class TestManifest:
    """Tests for manifest.json checksums."""

    def test_manifest_checksums_not_empty(self, manifest_data: dict) -> None:
        """After materialization, checksums should be populated for generated files."""
        datasets = manifest_data["datasets"]

        # The three files we generated should have non-empty checksums
        generated_ids = {
            "saudi_io_kapsarc_2018",
            "saudi_type1_multipliers_benchmark",
            "saudi_employment_coefficients_2019",
        }

        for ds in datasets:
            if ds["dataset_id"] in generated_ids:
                assert ds["checksum_sha256"] != "", (
                    f"Checksum is empty for {ds['dataset_id']}"
                )
                assert len(ds["checksum_sha256"]) == 64, (
                    f"Checksum for {ds['dataset_id']} is not a valid SHA-256 hex digest"
                )

    def test_manifest_has_io_entry(self, manifest_data: dict) -> None:
        """Manifest contains an entry for the IO model."""
        ids = [ds["dataset_id"] for ds in manifest_data["datasets"]]
        assert "saudi_io_kapsarc_2018" in ids

    def test_manifest_has_benchmark_entry(self, manifest_data: dict) -> None:
        """Manifest contains an entry for the benchmark multipliers."""
        ids = [ds["dataset_id"] for ds in manifest_data["datasets"]]
        assert "saudi_type1_multipliers_benchmark" in ids

    def test_manifest_has_employment_entry(self, manifest_data: dict) -> None:
        """Manifest contains an entry for the employment coefficients."""
        ids = [ds["dataset_id"] for ds in manifest_data["datasets"]]
        assert "saudi_employment_coefficients_2019" in ids

    def test_manifest_loads_with_loader(self) -> None:
        """Manifest loads with the manifest loader."""
        from src.data.manifest import load_manifest

        manifest = load_manifest(MANIFEST_PATH)
        assert manifest.manifest_version == "1.0"
        assert len(manifest.datasets) >= 3


# ===========================================================================
# 5. Strict loader integration test
# ===========================================================================


class TestStrictLoaderIntegration:
    """Integration test: strict loader can find and validate curated data."""

    @pytest.mark.xfail(
        reason="No real upstream data committed yet — requires D-5.1",
    )
    def test_strict_real_loads_curated_io(self) -> None:
        """STRICT_REAL mode loads the curated IO model without fallback."""
        from src.data.manifest import load_manifest
        from src.data.real_io_loader import (
            DataMode,
            load_real_saudi_io_strict,
        )

        manifest = load_manifest(MANIFEST_PATH)
        result = load_real_saudi_io_strict(
            mode=DataMode.STRICT_REAL,
            year=2018,
            manifest=manifest,
        )

        assert not result.provenance.used_fallback
        assert result.provenance.resolved_source == "curated_real"
        assert result.provenance.checksum_verified
        assert result.io_data.base_year == 2018
        assert len(result.io_data.sector_codes) == 20
