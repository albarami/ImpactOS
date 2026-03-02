"""D-5.1 Tests: Satellite coefficient loader DataMode enforcement.

TDD — strict-real mode, provenance tracking, and zero-synthetic runtime.
"""

import json
from pathlib import Path

import pytest

from src.data.real_io_loader import DataMode


def _write_curated_io(tmp_path: Path, year: int):
    """Write a minimal curated IO JSON for testing."""
    import numpy as np
    n = 3
    data = {
        "Z": (np.eye(n, dtype=float) * 10.0).tolist(),
        "x": [100.0] * n,
        "sector_codes": ["A", "B", "C"],
        "base_year": year,
        "source": "test-curated",
    }
    path = tmp_path / f"saudi_io_kapsarc_{year}.json"
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_employment(tmp_path: Path, year: int):
    """Write minimal employment coefficients JSON matching real schema."""
    data = {
        "year": year,
        "metadata": {},
        "coefficients": [
            {
                "sector_code": code,
                "granularity": "section",
                "year": year,
                "total_employment": 100000,
                "gross_output": 10000.0,
                "output_denomination": "SAR_MILLIONS",
                "jobs_per_unit_output": 0.01,
                "source": "test",
                "denominator_source": "test",
                "source_confidence": "HARD",
                "quality_confidence": "high",
            }
            for code in ["A", "B", "C"]
        ],
    }
    path = tmp_path / f"saudi_employment_coefficients_{year}.json"
    path.write_text(json.dumps(data), encoding="utf-8")


class TestSatelliteStrictReal:
    """STRICT_REAL fails when curated data is missing."""

    def test_strict_real_fails_when_curated_missing(self, tmp_path):
        from src.data.workforce.satellite_coeff_loader import (
            load_satellite_coefficients,
        )
        with pytest.raises(FileNotFoundError, match="STRICT_REAL"):
            load_satellite_coefficients(
                year=2019,
                curated_dir=str(tmp_path),
                data_mode=DataMode.STRICT_REAL,
            )

    def test_strict_real_succeeds_with_curated_data(self, tmp_path):
        from src.data.workforce.satellite_coeff_loader import (
            load_satellite_coefficients,
        )
        _write_curated_io(tmp_path, year=2019)
        _write_employment(tmp_path, year=2019)

        result = load_satellite_coefficients(
            year=2019,
            curated_dir=str(tmp_path),
            data_mode=DataMode.STRICT_REAL,
        )
        assert result.provenance.used_synthetic_fallback is False
        assert len(result.provenance.fallback_flags) == 0


class TestSatellitePreferReal:
    """PREFER_REAL tracks fallback provenance when it falls back."""

    def test_prefer_real_tracks_fallback(self, tmp_path):
        from src.data.workforce.satellite_coeff_loader import (
            load_satellite_coefficients,
        )
        result = load_satellite_coefficients(
            year=2019,
            curated_dir=str(tmp_path),
            data_mode=DataMode.PREFER_REAL,
        )
        assert result.provenance.used_synthetic_fallback is True
        assert len(result.provenance.fallback_flags) > 0


class TestSatelliteProvenanceField:
    """CoefficientProvenance exposes used_synthetic_fallback boolean."""

    def test_provenance_has_field(self):
        from src.data.workforce.satellite_coeff_loader import (
            CoefficientProvenance,
        )
        p = CoefficientProvenance(
            employment_coeff_year=2019,
            io_base_year=2019,
            import_ratio_year=2019,
            va_ratio_year=2019,
            fallback_flags=[],
            synchronized=True,
            used_synthetic_fallback=False,
        )
        assert p.used_synthetic_fallback is False
