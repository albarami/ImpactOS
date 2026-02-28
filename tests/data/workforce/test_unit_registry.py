"""Tests for unit denomination registry (D-4 Task 1b)."""

from __future__ import annotations

import numpy as np
import pytest

from src.data.workforce.unit_registry import (
    EmploymentCoefficient,
    EmploymentCoefficientSet,
    OutputDenomination,
    QualityConfidence,
    SectorGranularity,
    build_satellite_jobs_coeff,
    denomination_factor,
)
from src.models.common import ConstraintConfidence


class TestDenominationFactor:
    """Unit conversion between SAR, SAR_THOUSANDS, SAR_MILLIONS."""

    def test_same_denomination(self) -> None:
        assert denomination_factor(OutputDenomination.SAR, OutputDenomination.SAR) == 1.0

    def test_sar_to_millions(self) -> None:
        f = denomination_factor(OutputDenomination.SAR, OutputDenomination.SAR_MILLIONS)
        assert f == pytest.approx(1e-6)

    def test_millions_to_sar(self) -> None:
        f = denomination_factor(OutputDenomination.SAR_MILLIONS, OutputDenomination.SAR)
        assert f == pytest.approx(1e6)

    def test_thousands_to_millions(self) -> None:
        f = denomination_factor(OutputDenomination.SAR_THOUSANDS, OutputDenomination.SAR_MILLIONS)
        assert f == pytest.approx(0.001)

    def test_roundtrip(self) -> None:
        """Converting there and back should give factor = 1.0."""
        f1 = denomination_factor(OutputDenomination.SAR_THOUSANDS, OutputDenomination.SAR_MILLIONS)
        f2 = denomination_factor(OutputDenomination.SAR_MILLIONS, OutputDenomination.SAR_THOUSANDS)
        assert f1 * f2 == pytest.approx(1.0)


class TestEmploymentCoefficient:
    """EmploymentCoefficient dataclass."""

    def test_create_coefficient(self) -> None:
        c = EmploymentCoefficient(
            sector_code="F",
            granularity=SectorGranularity.SECTION,
            year=2019,
            total_employment=2_460_000,
            gross_output=136_667.0,
            output_denomination=OutputDenomination.SAR_MILLIONS,
            jobs_per_unit_output=18.0,
            saudi_share=0.08,
            source="ilo+kapsarc_io_2019",
            denominator_source="kapsarc_io_x_vector",
            source_confidence=ConstraintConfidence.ESTIMATED,
            quality_confidence=QualityConfidence.HIGH,
        )
        assert c.sector_code == "F"
        assert c.jobs_per_unit_output == 18.0
        assert c.output_denomination == OutputDenomination.SAR_MILLIONS

    def test_frozen(self) -> None:
        c = EmploymentCoefficient(
            sector_code="A", granularity=SectorGranularity.SECTION,
            year=2019, total_employment=100, gross_output=10.0,
            output_denomination=OutputDenomination.SAR_MILLIONS,
            jobs_per_unit_output=10.0, saudi_share=None,
            source="test", denominator_source="test",
            source_confidence=ConstraintConfidence.ASSUMED,
            quality_confidence=QualityConfidence.LOW,
        )
        with pytest.raises(AttributeError):
            c.sector_code = "B"  # type: ignore[misc]


class TestBuildSatelliteJobsCoeff:
    """Build jobs_coeff vector from EmploymentCoefficientSet."""

    def _make_set(self) -> EmploymentCoefficientSet:
        return EmploymentCoefficientSet(
            year=2019,
            coefficients=[
                EmploymentCoefficient(
                    sector_code="A", granularity=SectorGranularity.SECTION,
                    year=2019, total_employment=250_000, gross_output=10_000.0,
                    output_denomination=OutputDenomination.SAR_MILLIONS,
                    jobs_per_unit_output=25.0, saudi_share=0.08,
                    source="test", denominator_source="test",
                    source_confidence=ConstraintConfidence.ESTIMATED,
                    quality_confidence=QualityConfidence.HIGH,
                ),
                EmploymentCoefficient(
                    sector_code="B", granularity=SectorGranularity.SECTION,
                    year=2019, total_employment=40_000, gross_output=20_000.0,
                    output_denomination=OutputDenomination.SAR_MILLIONS,
                    jobs_per_unit_output=2.0, saudi_share=0.45,
                    source="test", denominator_source="test",
                    source_confidence=ConstraintConfidence.ESTIMATED,
                    quality_confidence=QualityConfidence.HIGH,
                ),
            ],
            metadata={},
        )

    def test_same_denomination(self) -> None:
        """No unit conversion needed."""
        s = self._make_set()
        result = build_satellite_jobs_coeff(
            s, ["A", "B"], OutputDenomination.SAR_MILLIONS,
        )
        np.testing.assert_array_almost_equal(result, [25.0, 2.0])

    def test_unit_normalization(self) -> None:
        """Coefficient in SAR_MILLIONS, model in SAR_THOUSANDS."""
        s = self._make_set()
        result = build_satellite_jobs_coeff(
            s, ["A", "B"], OutputDenomination.SAR_THOUSANDS,
        )
        # jobs_per_million * factor(thousands -> millions) = jobs_per_thousand
        # 25.0 * 0.001 = 0.025 jobs per thousand SAR
        np.testing.assert_array_almost_equal(result, [0.025, 0.002])

    def test_missing_sector_gives_zero(self) -> None:
        """Sector not in coefficient set produces zero."""
        s = self._make_set()
        result = build_satellite_jobs_coeff(
            s, ["A", "B", "C"], OutputDenomination.SAR_MILLIONS,
        )
        assert result[2] == 0.0

    def test_positive_reasonable_range(self) -> None:
        """All coefficients positive and in reasonable range for SAR_MILLIONS."""
        s = self._make_set()
        result = build_satellite_jobs_coeff(
            s, ["A", "B"], OutputDenomination.SAR_MILLIONS,
        )
        assert all(r >= 0 for r in result)
        assert all(r <= 100 for r in result)  # 1-100 jobs/M SAR reasonable
