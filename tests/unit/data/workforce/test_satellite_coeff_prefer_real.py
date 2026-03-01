"""Tests that satellite_coeff_loader prefers curated real IO over synthetic.

Correction 4: Test through PUBLIC API load_satellite_coefficients() only.
D-5 Task 4.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from src.data.workforce.satellite_coeff_loader import load_satellite_coefficients


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _write_curated_io(curated_dir, year=2018):
    """Write a minimal curated IO model fixture (saudi_io_kapsarc_{year}.json).

    Uses a 3-sector model with known column sums so VA ratios are predictable.
    VA ratio = 1 - col_sum(A), where A = Z / x.

    Sector F: col_sum(A) = (10+3+2)/100 = 0.15 -> VA = 0.85
    Sector C: col_sum(A) = (5+20+3)/200 = 0.14 -> VA = 0.86
    Sector G: col_sum(A) = (2+4+15)/150 = 0.14 -> VA = 0.86
    """
    Z = [[10, 5, 2], [3, 20, 4], [2, 3, 15]]
    x = [100.0, 200.0, 150.0]
    fixture = {
        "sector_codes": ["F", "C", "G"],
        "Z": Z,
        "x": x,
        "base_year": year,
        "source": f"curated_{year}",
    }
    (curated_dir / f"saudi_io_kapsarc_{year}.json").write_text(
        json.dumps(fixture), encoding="utf-8",
    )


def _write_synthetic_satellites(curated_dir, *, import_ratio=None, va_ratio=None):
    """Write a synthetic satellites file with obviously wrong values.

    Uses the real format expected by load_satellites_from_json().
    """
    sat = {
        "sector_codes": ["F", "C", "G"],
        "employment": {
            "jobs_per_sar_million": [10.0, 5.0, 8.0],
            "confidence": ["low", "low", "low"],
        },
        "import_ratios": {
            "values": import_ratio or [0.99, 0.99, 0.99],
            "confidence": ["low", "low", "low"],
        },
        "va_ratios": {
            "values": va_ratio or [0.01, 0.01, 0.01],
            "confidence": ["low", "low", "low"],
        },
    }
    (curated_dir / "saudi_satellites_synthetic_v1.json").write_text(
        json.dumps(sat), encoding="utf-8",
    )


def _write_employment_coefficients(curated_dir, year=2018):
    """Write minimal employment coefficients so jobs_coeff loads cleanly."""
    # Matches the format expected by load_employment_coefficients
    from src.data.workforce.build_employment_coefficients import (
        CoefficientSet,
        SectorCoefficient,
    )
    coeffs = CoefficientSet(
        base_year=year,
        denomination="SAR_MILLIONS",
        coefficients=[
            SectorCoefficient(
                sector_code="F",
                sector_name="Construction",
                jobs_per_unit_output=13.0,
                confidence="medium",
                source="test",
            ),
            SectorCoefficient(
                sector_code="C",
                sector_name="Manufacturing",
                jobs_per_unit_output=6.5,
                confidence="medium",
                source="test",
            ),
            SectorCoefficient(
                sector_code="G",
                sector_name="Trade",
                jobs_per_unit_output=10.0,
                confidence="medium",
                source="test",
            ),
        ],
    )
    import dataclasses
    data = dataclasses.asdict(coeffs)
    (curated_dir / f"saudi_employment_coefficients_{year}.json").write_text(
        json.dumps(data), encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSatellitePrefersCuratedIO:
    """Test through PUBLIC API load_satellite_coefficients() per Correction 4."""

    def test_prefers_curated_io_over_synthetic_satellites(self, tmp_path):
        """When curated IO exists, ratios should come from it, not synthetic."""
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        _write_curated_io(curated_dir, 2018)

        # Write synthetic satellites with obviously wrong values
        _write_synthetic_satellites(curated_dir)

        result = load_satellite_coefficients(
            year=2018,
            sector_codes=["F", "C", "G"],
            curated_dir=str(curated_dir),
        )

        # VA ratios from real IO should NOT be [0.01, 0.01, 0.01]
        # They should be ~0.85, 0.86, 0.86 based on the curated IO fixture
        va = result.coefficients.va_ratio
        assert all(v > 0.05 for v in va), f"Still using synthetic? {va}"
        # More specifically, they should be close to the computed values
        # col_sum(A) for F: (10+3+2)/100 = 0.15 -> VA = 0.85
        assert va[0] == pytest.approx(0.85, abs=0.01)

    def test_provenance_flags_curated_io(self, tmp_path):
        """Provenance should not have synthetic fallback for IO ratios."""
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        _write_curated_io(curated_dir, 2018)

        result = load_satellite_coefficients(
            year=2018,
            sector_codes=["F", "C", "G"],
            curated_dir=str(curated_dir),
        )

        io_fallbacks = [
            f
            for f in result.provenance.fallback_flags
            if "import_ratio" in f or "va_ratio" in f
        ]
        synthetic_fallbacks = [
            f for f in io_fallbacks if "synthetic" in f.lower()
        ]
        assert len(synthetic_fallbacks) == 0, (
            f"Should have no synthetic fallbacks for IO ratios: {synthetic_fallbacks}"
        )

    def test_falls_back_to_synthetic_when_no_curated_io(self, tmp_path):
        """Without curated IO, should still fall back to synthetic satellites."""
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        # Only write synthetic satellites, no curated IO
        _write_synthetic_satellites(
            curated_dir,
            import_ratio=[0.3, 0.25, 0.2],
            va_ratio=[0.4, 0.5, 0.6],
        )

        result = load_satellite_coefficients(
            year=2018,
            sector_codes=["F", "C", "G"],
            curated_dir=str(curated_dir),
        )

        # Should still work, just from synthetic
        assert result.coefficients.va_ratio is not None
        assert len(result.coefficients.va_ratio) == 3
        # Values should match synthetic
        np.testing.assert_allclose(
            result.coefficients.va_ratio, [0.4, 0.5, 0.6], atol=0.01,
        )

    def test_curated_io_year_fuzzy_match(self, tmp_path):
        """Curated IO should be found with +/- 4 year fuzzy match."""
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        # Write curated IO for 2018 but request year 2020
        _write_curated_io(curated_dir, 2018)

        # Write synthetic with wrong values so we can detect source
        _write_synthetic_satellites(curated_dir)

        result = load_satellite_coefficients(
            year=2020,
            sector_codes=["F", "C", "G"],
            curated_dir=str(curated_dir),
        )

        # Should find the 2018 file (within +/- 4 range)
        va = result.coefficients.va_ratio
        assert all(v > 0.05 for v in va), (
            f"Should use curated IO via fuzzy match, not synthetic: {va}"
        )

    def test_import_ratio_default_when_curated_io(self, tmp_path):
        """When curated IO is used, import ratios should get a reasonable default."""
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        _write_curated_io(curated_dir, 2018)

        result = load_satellite_coefficients(
            year=2018,
            sector_codes=["F", "C", "G"],
            curated_dir=str(curated_dir),
        )

        # Import ratios should be the 0.15 default, NOT 0.99 from synthetic
        import_r = result.coefficients.import_ratio
        assert all(v < 0.5 for v in import_r), (
            f"Import ratios should not be from synthetic: {import_r}"
        )

    def test_io_base_year_from_curated(self, tmp_path):
        """Provenance io_base_year should reflect the curated IO file year."""
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        _write_curated_io(curated_dir, 2018)

        result = load_satellite_coefficients(
            year=2018,
            sector_codes=["F", "C", "G"],
            curated_dir=str(curated_dir),
        )

        assert result.provenance.io_base_year == 2018
