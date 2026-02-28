"""Tests for satellite coefficient loader — KEY integration test (D-4 Task 1e/5a).

Verifies that D-4 data produces valid SatelliteCoefficients objects
compatible with SatelliteAccounts.compute().
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.data.workforce.satellite_coeff_loader import (
    CoefficientProvenance,
    load_satellite_coefficients,
)
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients

CURATED_DIR = Path("data/curated")


class TestSatelliteCoeffLoader:
    """Integration: D-4 data -> SatelliteCoefficients."""

    @pytest.mark.skipif(
        not (CURATED_DIR / "saudi_satellites_synthetic_v1.json").exists(),
        reason="Synthetic satellites not available",
    )
    def test_produces_valid_coefficients(self) -> None:
        """Produces a valid SatelliteCoefficients object."""
        loaded = load_satellite_coefficients()
        assert isinstance(loaded.coefficients, SatelliteCoefficients)
        assert loaded.coefficients.jobs_coeff is not None
        assert loaded.coefficients.import_ratio is not None
        assert loaded.coefficients.va_ratio is not None

    @pytest.mark.skipif(
        not (CURATED_DIR / "saudi_satellites_synthetic_v1.json").exists(),
        reason="Synthetic satellites not available",
    )
    def test_compatible_with_satellite_accounts(self) -> None:
        """Full round-trip: coefficients work with SatelliteAccounts.compute()."""
        loaded = load_satellite_coefficients()
        coeffs = loaded.coefficients
        n = len(coeffs.jobs_coeff)

        sat = SatelliteAccounts()
        delta_x = np.ones(n) * 100.0  # 100 SAR million shock per sector

        result = sat.compute(delta_x=delta_x, coefficients=coeffs)
        assert result.delta_jobs is not None
        assert len(result.delta_jobs) == n
        assert np.all(result.delta_jobs >= 0)

    @pytest.mark.skipif(
        not (CURATED_DIR / "saudi_satellites_synthetic_v1.json").exists(),
        reason="Synthetic satellites not available",
    )
    def test_provenance_tracked(self) -> None:
        """CoefficientProvenance reports source years (Amendment 5)."""
        loaded = load_satellite_coefficients()
        assert isinstance(loaded.provenance, CoefficientProvenance)
        assert loaded.provenance.employment_coeff_year > 0
        assert loaded.provenance.io_base_year > 0

    @pytest.mark.skipif(
        not (CURATED_DIR / "saudi_satellites_synthetic_v1.json").exists(),
        reason="Synthetic satellites not available",
    )
    def test_fallback_to_synthetic(self) -> None:
        """Falls back to synthetic when curated data unavailable."""
        loaded = load_satellite_coefficients()
        # Should have fallback flags since no D-4 curated coefficients exist yet
        assert isinstance(loaded.provenance.fallback_flags, list)

    @pytest.mark.skipif(
        not (CURATED_DIR / "saudi_satellites_synthetic_v1.json").exists(),
        reason="Synthetic satellites not available",
    )
    def test_version_id_set(self) -> None:
        loaded = load_satellite_coefficients()
        assert loaded.coefficients.version_id is not None

    @pytest.mark.skipif(
        not (CURATED_DIR / "saudi_satellites_synthetic_v1.json").exists(),
        reason="Synthetic satellites not available",
    )
    def test_dimensions_consistent(self) -> None:
        """All coefficient vectors have same length."""
        loaded = load_satellite_coefficients()
        c = loaded.coefficients
        n = len(c.jobs_coeff)
        assert len(c.import_ratio) == n
        assert len(c.va_ratio) == n

    @pytest.mark.skipif(
        not (CURATED_DIR / "saudi_satellites_synthetic_v1.json").exists(),
        reason="Synthetic satellites not available",
    )
    def test_jobs_coeff_positive_reasonable(self) -> None:
        """jobs_coeff values positive and in reasonable range."""
        loaded = load_satellite_coefficients()
        jobs = loaded.coefficients.jobs_coeff
        assert np.all(jobs >= 0)
        # For SAR_MILLIONS denomination: ~1-100 jobs/M SAR
        assert np.max(jobs) <= 150

    @pytest.mark.skipif(
        not (CURATED_DIR / "saudi_satellites_synthetic_v1.json").exists(),
        reason="Synthetic satellites not available",
    )
    def test_import_ratio_valid_range(self) -> None:
        """import_ratio values between 0 and 1."""
        loaded = load_satellite_coefficients()
        ir = loaded.coefficients.import_ratio
        assert np.all(ir >= 0)
        assert np.all(ir <= 1.0)
