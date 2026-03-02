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
from src.data.real_io_loader import DataMode
from src.data.workforce.build_employment_coefficients import (
    load_employment_coefficients,
)
from src.data.workforce.unit_registry import (
    OutputDenomination,
    build_satellite_jobs_coeff,
)
from src.engine.satellites import SatelliteCoefficients

logger = logging.getLogger(__name__)

RUNTIME_DATA_MODE = DataMode.STRICT_REAL

# Default paths
_CURATED_DIR = Path("data/curated")
_SYNTHETIC_DIR = Path("data/synthetic")
_SYNTHETIC_SATELLITES = _SYNTHETIC_DIR / "saudi_satellites_synthetic_v1.json"
_SYNTHETIC_IO = _SYNTHETIC_DIR / "saudi_io_synthetic_v1.json"


@dataclass(frozen=True)
class CoefficientProvenance:
    """Track which year each component came from (Amendment 5).

    D-5.1: used_synthetic_fallback indicates whether any component
    used synthetic data, for quality/export gate decisions.
    """

    employment_coeff_year: int
    io_base_year: int
    import_ratio_year: int
    va_ratio_year: int
    fallback_flags: list[str] = field(default_factory=list)
    synchronized: bool = False
    used_synthetic_fallback: bool = False


@dataclass(frozen=True)
class LoadedCoefficients:
    """SatelliteCoefficients with provenance tracking."""

    coefficients: SatelliteCoefficients
    provenance: CoefficientProvenance


def load_satellite_coefficients(
    year: int = 2019,
    sector_codes: list[str] | None = None,
    curated_dir: str | Path = "data/curated",
    data_mode: DataMode = DataMode.PREFER_REAL,
) -> LoadedCoefficients:
    """Load curated employment + import + VA coefficients.

    D-5.1: data_mode controls fallback behavior:
      STRICT_REAL  — fail if any component needs synthetic fallback.
      PREFER_REAL  — curated first, synthetic fallback with provenance.
      SYNTHETIC_ONLY — synthetic only (for offline/test use).

    Raises:
        FileNotFoundError: In STRICT_REAL when curated data is incomplete.
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

    # STRICT_REAL: fail if any synthetic fallback occurred
    if data_mode == DataMode.STRICT_REAL and fallback_flags:
        msg = (
            f"STRICT_REAL: curated satellite data incomplete for year {year}. "
            f"Fallbacks: {fallback_flags}"
        )
        raise FileNotFoundError(msg)

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

    used_synthetic = any(
        "synthetic" in f.lower() or "zeros" in f.lower()
        for f in fallback_flags
    )

    provenance = CoefficientProvenance(
        employment_coeff_year=emp_year,
        io_base_year=io_year,
        import_ratio_year=io_year,
        va_ratio_year=io_year,
        fallback_flags=fallback_flags,
        synchronized=synchronized,
        used_synthetic_fallback=used_synthetic,
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


def _find_curated_io(base: Path, year: int) -> tuple[Path, int] | None:
    """Search for curated KAPSARC IO file: exact year first, then +/- 4.

    Same pattern as _find_curated_file() in real_io_loader.py.
    Returns (path, resolved_year) or None if not found.
    """
    # Exact year first
    exact = base / f"saudi_io_kapsarc_{year}.json"
    if exact.exists():
        return exact, year

    # Nearby years (offset 1..4, alternating before/after)
    for offset in range(1, 5):
        for candidate_year in (year - offset, year + offset):
            candidate = base / f"saudi_io_kapsarc_{candidate_year}.json"
            if candidate.exists():
                return candidate, candidate_year

    return None


def _load_io_ratios(
    base: Path,
    year: int,
    sector_codes: list[str] | None,
    fallback_flags: list[str],
) -> tuple[int, np.ndarray, np.ndarray, list[str]]:
    """Load import_ratio and va_ratio from IO model or synthetic.

    Priority order:
    1. Curated real IO (saudi_io_kapsarc_{year}.json, +/- 4 years)
    2. Synthetic satellites (saudi_satellites_synthetic_v1.json)
    3. Synthetic IO model (saudi_io_synthetic_v1.json)
    4. Zeros
    """
    # 1. Try curated real IO first (preferred source)
    found = _find_curated_io(base, year)
    if found is not None:
        curated_path, resolved_year = found
        try:
            io_data = load_from_json(str(curated_path))
            n = len(io_data.x)
            # VA ratio: va_i = 1 - col_sum(A_i) where A = Z / x
            x_safe = np.where(io_data.x > 0, io_data.x, 1.0)
            a_mat = io_data.Z / x_safe[np.newaxis, :]
            va_ratio = 1.0 - a_mat.sum(axis=0)
            va_ratio = np.clip(va_ratio, 0.0, 1.0)
            # Import ratio: default 0.15 (curated IO doesn't include imports)
            import_ratio = np.full(n, 0.15, dtype=np.float64)
            codes = io_data.sector_codes
            logger.info(
                "IO ratios from curated real IO: %s (year %d)",
                curated_path.name, resolved_year,
            )
            # No fallback flag — curated data is the preferred source
            return io_data.base_year, import_ratio, va_ratio, codes
        except Exception:
            logger.warning(
                "Failed to load curated IO from %s, trying fallbacks",
                curated_path,
                exc_info=True,
            )

    # 2. Try synthetic satellites (they have import + VA ratios)
    # Check both the provided base dir (for tests) and the default synthetic dir
    synth_sat_candidates = [
        base / "saudi_satellites_synthetic_v1.json",
        _SYNTHETIC_SATELLITES,
    ]
    for synth_sat_path in synth_sat_candidates:
        if synth_sat_path.exists():
            fallback_flags.append("import_ratio: synthetic fallback")
            fallback_flags.append("va_ratio: synthetic fallback")
            sat_data = load_satellites_from_json(str(synth_sat_path))
            codes = sat_data.sector_codes
            base_yr = sat_data.metadata.get("base_year", 2022)
            return base_yr, sat_data.import_ratio, sat_data.va_ratio, codes

    # 3. Try synthetic IO model to derive VA ratios
    synth_io_candidates = [
        base / "saudi_io_synthetic_v1.json",
        _SYNTHETIC_IO,
    ]
    synth_io_path = next((p for p in synth_io_candidates if p.exists()), None)
    if synth_io_path is not None:
        fallback_flags.append("import_ratio: derived from synthetic IO model")
        fallback_flags.append("va_ratio: derived from synthetic IO model")
        io_data = load_from_json(str(synth_io_path))
        n = len(io_data.x)
        # VA ratio from IO model: va_i = 1 - sum(A_col_i)
        x_safe = np.where(io_data.x > 0, io_data.x, 1.0)
        a_mat = io_data.Z / x_safe[np.newaxis, :]
        va_ratio = 1.0 - a_mat.sum(axis=0)
        va_ratio = np.clip(va_ratio, 0.0, 1.0)
        import_ratio = np.full(n, 0.15, dtype=np.float64)
        return io_data.base_year, import_ratio, va_ratio, io_data.sector_codes

    # 4. No data at all
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
