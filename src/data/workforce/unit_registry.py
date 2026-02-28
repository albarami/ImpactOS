"""Unit denomination registry and employment coefficient model (D-4 Task 1b).

Handles explicit denomination tracking to prevent silent 10^6 errors
between SAR, SAR_THOUSANDS, and SAR_MILLIONS conventions.

All employment coefficients carry their denomination explicitly.
The build_satellite_jobs_coeff() function normalizes to any target denomination.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from src.models.common import ConstraintConfidence


class QualityConfidence(StrEnum):
    """Quality confidence for a data point (Amendment 1, dimension 2).

    How reliable is the resulting data point?
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class OutputDenomination(StrEnum):
    """Unit denomination for monetary values."""

    SAR = "SAR"
    SAR_THOUSANDS = "SAR_THOUSANDS"
    SAR_MILLIONS = "SAR_MILLIONS"


# Conversion factors to base unit (SAR)
_TO_SAR: dict[OutputDenomination, float] = {
    OutputDenomination.SAR: 1.0,
    OutputDenomination.SAR_THOUSANDS: 1_000.0,
    OutputDenomination.SAR_MILLIONS: 1_000_000.0,
}


def denomination_factor(
    from_denom: OutputDenomination,
    to_denom: OutputDenomination,
) -> float:
    """Get the multiplicative factor to convert from one denomination to another.

    Example: denomination_factor(SAR_THOUSANDS, SAR_MILLIONS) = 0.001
    (1 thousand SAR = 0.001 million SAR)
    """
    return _TO_SAR[from_denom] / _TO_SAR[to_denom]


class SectorGranularity(StrEnum):
    """Granularity level of a sector code (Amendment 3)."""

    SECTION = "section"      # A-T (20 sectors)
    DIVISION = "division"    # 01-99 (84 active divisions)


@dataclass(frozen=True)
class EmploymentCoefficient:
    """Jobs per unit of gross output for a given sector.

    The denominator MUST be gross output (x), NOT GDP/value-added.
    See D-4 spec section 1a for methodology rationale.
    """

    sector_code: str
    granularity: SectorGranularity
    year: int
    total_employment: float
    gross_output: float
    output_denomination: OutputDenomination
    jobs_per_unit_output: float
    saudi_share: float | None
    source: str
    denominator_source: str
    source_confidence: ConstraintConfidence
    quality_confidence: QualityConfidence
    notes: str | None = None


@dataclass(frozen=True)
class EmploymentCoefficientSet:
    """Complete set of employment coefficients for all sectors."""

    year: int
    coefficients: list[EmploymentCoefficient]
    metadata: dict[str, object]

    def get_coefficient(self, sector_code: str) -> EmploymentCoefficient | None:
        """Look up coefficient by sector code."""
        for c in self.coefficients:
            if c.sector_code == sector_code:
                return c
        return None

    def get_by_granularity(
        self, granularity: SectorGranularity,
    ) -> list[EmploymentCoefficient]:
        """Filter coefficients by granularity level."""
        return [c for c in self.coefficients if c.granularity == granularity]

    @property
    def sector_codes(self) -> list[str]:
        """All sector codes in the set."""
        return [c.sector_code for c in self.coefficients]


def build_satellite_jobs_coeff(
    coefficients: EmploymentCoefficientSet,
    sector_codes: list[str],
    model_denomination: OutputDenomination,
) -> np.ndarray:
    """Convert employment coefficients to jobs_coeff vector for SatelliteCoefficients.

    Normalizes units so that jobs_coeff * delta_x produces correct job counts
    regardless of what denomination the model uses.

    Args:
        coefficients: D-4 curated employment coefficients.
        sector_codes: Ordered sector codes matching the model dimensions.
        model_denomination: The denomination used by the IO model.

    Returns:
        np.ndarray of length len(sector_codes), ready for SatelliteCoefficients.jobs_coeff.
    """
    n = len(sector_codes)
    result = np.zeros(n, dtype=np.float64)

    for i, code in enumerate(sector_codes):
        coeff = coefficients.get_coefficient(code)
        if coeff is None:
            continue
        # Normalize: convert jobs_per_unit_output to model's denomination
        # If coeff is in SAR_THOUSANDS and model is SAR_MILLIONS:
        #   jobs_per_thousand * (1000 / 1_000_000) = jobs_per_million
        #   Or equivalently: multiply by factor(model_denom -> coeff_denom)
        factor = denomination_factor(model_denomination, coeff.output_denomination)
        result[i] = coeff.jobs_per_unit_output * factor

    return result
