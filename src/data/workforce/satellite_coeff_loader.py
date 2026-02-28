"""Satellite coefficient loader — bridge between D-4 data and engine (D-4 Task 1e/5a).

This is the KEY DELIVERABLE connecting D-4 curated data to the
existing SatelliteCoefficients in src/engine/satellites.py.

Loads:
- D-4 employment coefficients (jobs_coeff)
- D-3 IO model data (import_ratio, va_ratio)

Returns a SatelliteCoefficients object ready for SatelliteAccounts.compute().
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from uuid_extensions import uuid7

from src.data.io_loader import load_from_json, load_satellites_from_json
from src.data.workforce.build_employment_coefficients import (
    load_employment_coefficients,
)
from src.data.workforce.unit_registry import (
    OutputDenomination,
    build_satellite_jobs_coeff,
)
from src.engine.satellites import SatelliteCoefficients

logger = logging.getLogger(__name__)

# Default paths
_CURATED_DIR = Path("data/curated")
_SYNTHETIC_SATELLITES = _CURATED_DIR / "saudi_satellites_synthetic_v1.json"
_SYNTHETIC_IO = _CURATED_DIR / "saudi_io_synthetic_v1.json"


@dataclass(frozen=True)
class CoefficientProvenance:
    """Track which year each component came from (Amendment 5)."""

    employment_coeff_year: int
    io_base_year: int
    import_ratio_year: int
    va_ratio_year: int
    fallback_flags: list[str] = field(default_factory=list)
    synchronized: bool = False


@dataclass(frozen=True)
class LoadedCoefficients:
    """SatelliteCoefficients with provenance tracking."""

    coefficients: SatelliteCoefficients
    provenance: CoefficientProvenance


def load_satellite_coefficients(
    year: int = 2019,
    sector_codes: list[str] | None = None,
    curated_dir: str | Path = "data/curated",
) -> LoadedCoefficients:
    """Load curated employment + import + VA coefficients into SatelliteCoefficients.

    Reads D-4 employment coefficients + D-3 IO data to build a complete
    SatelliteCoefficients object compatible with SatelliteAccounts.compute().

    Falls back to synthetic if curated data unavailable.
    Logs which sources were used for each component.

    Args:
        year: Target year.
        sector_codes: Ordered sector codes matching model dimensions.
            If None, uses codes from IO model.
        curated_dir: Path to curated data directory.

    Returns:
        LoadedCoefficients with SatelliteCoefficients + provenance.
    """
    base = Path(curated_dir)
    fallback_flags: list[str] = []

    # 1. Load employment coefficients (D-4)
    emp_year, jobs_coeff = _load_jobs_coeff(
        base, year, sector_codes, fallback_flags,
    )

    # 2. Load import and VA ratios (D-3 IO model or synthetic)
    io_year, import_ratio, va_ratio, resolved_codes = _load_io_ratios(
        base, year, sector_codes, fallback_flags,
    )

    # Use resolved sector codes if not provided
    if sector_codes is None:
        sector_codes = resolved_codes

    # Ensure all vectors have correct length
    n = len(sector_codes)
    if len(jobs_coeff) != n:
        jobs_coeff = _resize_vector(jobs_coeff, n, "jobs_coeff", fallback_flags)
    if len(import_ratio) != n:
        import_ratio = _resize_vector(import_ratio, n, "import_ratio", fallback_flags)
    if len(va_ratio) != n:
        va_ratio = _resize_vector(va_ratio, n, "va_ratio", fallback_flags)

    # Year synchronization check (Amendment 5)
    synchronized = (emp_year == io_year)
    if not synchronized:
        msg = (
            f"Year mismatch: employment coefficients from {emp_year}, "
            f"IO ratios from {io_year}"
        )
        warnings.warn(msg, stacklevel=2)
        logger.warning(msg)

    provenance = CoefficientProvenance(
        employment_coeff_year=emp_year,
        io_base_year=io_year,
        import_ratio_year=io_year,
        va_ratio_year=io_year,
        fallback_flags=fallback_flags,
        synchronized=synchronized,
    )

    coefficients = SatelliteCoefficients(
        jobs_coeff=jobs_coeff,
        import_ratio=import_ratio,
        va_ratio=va_ratio,
        version_id=uuid7(),
    )

    logger.info(
        "Loaded satellite coefficients: emp_year=%d, io_year=%d, "
        "sectors=%d, fallbacks=%d",
        emp_year, io_year, n, len(fallback_flags),
    )

    return LoadedCoefficients(
        coefficients=coefficients,
        provenance=provenance,
    )


def _load_jobs_coeff(
    base: Path,
    year: int,
    sector_codes: list[str] | None,
    fallback_flags: list[str],
) -> tuple[int, np.ndarray]:
    """Load jobs_coeff from D-4 employment coefficients or synthetic fallback."""
    # Try D-4 curated coefficients
    coeff_path = base / f"saudi_employment_coefficients_{year}.json"
    if coeff_path.exists():
        coeff_set = load_employment_coefficients(coeff_path)
        if sector_codes is not None:
            jobs = build_satellite_jobs_coeff(
                coeff_set,
                sector_codes,
                OutputDenomination.SAR_MILLIONS,
            )
        else:
            jobs = np.array(
                [c.jobs_per_unit_output for c in coeff_set.coefficients],
                dtype=np.float64,
            )
        return year, jobs

    # Fallback: synthetic satellite data
    if _SYNTHETIC_SATELLITES.exists():
        fallback_flags.append("jobs_coeff: synthetic fallback")
        sat_data = load_satellites_from_json(str(_SYNTHETIC_SATELLITES))
        return 2022, sat_data.jobs_coeff

    fallback_flags.append("jobs_coeff: zeros (no data)")
    n = len(sector_codes) if sector_codes else 20
    return year, np.zeros(n, dtype=np.float64)


def _load_io_ratios(
    base: Path,
    year: int,
    sector_codes: list[str] | None,
    fallback_flags: list[str],
) -> tuple[int, np.ndarray, np.ndarray, list[str]]:
    """Load import_ratio and va_ratio from IO model or synthetic."""
    # Try synthetic satellites first (they have import + VA ratios)
    if _SYNTHETIC_SATELLITES.exists():
        sat_data = load_satellites_from_json(str(_SYNTHETIC_SATELLITES))
        codes = sat_data.sector_codes
        return 2022, sat_data.import_ratio, sat_data.va_ratio, codes

    # Try IO model to derive VA ratios
    io_path = _SYNTHETIC_IO
    if io_path.exists():
        fallback_flags.append("import_ratio: derived from IO model")
        io_data = load_from_json(str(io_path))
        n = len(io_data.x)
        # VA ratio from IO model: va_i = 1 - sum(A_col_i)
        x_safe = np.where(io_data.x > 0, io_data.x, 1.0)
        a_mat = io_data.Z / x_safe[np.newaxis, :]
        va_ratio = 1.0 - a_mat.sum(axis=0)
        va_ratio = np.clip(va_ratio, 0.0, 1.0)
        import_ratio = np.full(n, 0.15, dtype=np.float64)
        return io_data.base_year, import_ratio, va_ratio, io_data.sector_codes

    # No data at all
    fallback_flags.append("import_ratio: zeros (no data)")
    fallback_flags.append("va_ratio: zeros (no data)")
    n = len(sector_codes) if sector_codes else 20
    codes = sector_codes or [f"S{i}" for i in range(n)]
    return year, np.zeros(n), np.zeros(n), codes


def _resize_vector(
    vec: np.ndarray,
    target_n: int,
    name: str,
    fallback_flags: list[str],
) -> np.ndarray:
    """Resize a vector to target length (pad with zeros or truncate)."""
    current_n = len(vec)
    if current_n < target_n:
        fallback_flags.append(f"{name}: padded from {current_n} to {target_n}")
        return np.pad(vec, (0, target_n - current_n))
    fallback_flags.append(f"{name}: truncated from {current_n} to {target_n}")
    return vec[:target_n]
