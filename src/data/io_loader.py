"""IO model loader — loads curated JSON/Excel into ModelStore-compatible format.

Provides:
  load_from_json(path) -> IOModelData
  load_from_excel(path, config) -> IOModelData (stub for GASTAT)
  validate_model(Z, x, sector_codes) -> ValidationResult
  load_satellites_from_json(path) -> SatelliteData

D-1: Saudi Base IO Model Loading.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import linalg as scipy_linalg

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IOModelData:
    """Loaded IO model data ready for registration with ModelStore."""

    Z: np.ndarray
    x: np.ndarray
    sector_codes: list[str]
    sector_names: dict[str, str]
    base_year: int
    source: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class ValidationResult:
    """Comprehensive IO model validation diagnostics."""

    is_valid: bool
    spectral_radius: float
    all_z_nonnegative: bool
    all_x_positive: bool
    all_va_positive: bool
    b_nonnegative: bool
    output_multipliers: dict[str, float]
    va_ratios: dict[str, float]
    column_sums_a: dict[str, float]
    total_output: float
    total_value_added: float
    errors: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class SatelliteData:
    """Loaded satellite coefficient data with per-sector confidence."""

    sector_codes: list[str]
    jobs_coeff: np.ndarray
    import_ratio: np.ndarray
    va_ratio: np.ndarray
    employment_confidence: list[str]
    import_confidence: list[str]
    va_confidence: list[str]
    metadata: dict[str, object]


@dataclass(frozen=True)
class ExcelSheetConfig:
    """Configuration for loading IO model from Excel (GASTAT format).

    Amendment 6: Typed config instead of raw dict.
    """

    z_sheet: str
    z_start_row: int
    z_start_col: int
    sector_count: int
    sector_header_row: int | None = None
    x_location: str = "last_row"
    denomination: str = "SAR_MILLIONS"


# ---------------------------------------------------------------------------
# JSON loaders
# ---------------------------------------------------------------------------


def load_from_json(path: str | Path) -> IOModelData:
    """Load a curated IO model from JSON.

    Validates structure and types but does NOT validate economic properties
    (use validate_model() for that).

    Raises:
        FileNotFoundError: If path does not exist.
        ValueError: If JSON is missing required fields or has dimension mismatches.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Required fields
    if "Z" not in data and "z_matrix" not in data:
        msg = f"Missing 'Z' or 'z_matrix' in {path.name}"
        raise ValueError(msg)
    if "x" not in data and "x_vector" not in data:
        msg = f"Missing 'x' or 'x_vector' in {path.name}"
        raise ValueError(msg)

    z_raw = data.get("Z") or data.get("z_matrix")
    x_raw = data.get("x") or data.get("x_vector")
    sector_codes = data.get("sector_codes", [])

    z_arr = np.array(z_raw, dtype=np.float64)
    x_arr = np.array(x_raw, dtype=np.float64)

    n = len(x_arr)
    if z_arr.ndim != 2 or z_arr.shape[0] != z_arr.shape[1]:
        msg = f"Z must be a square matrix, got shape {z_arr.shape}"
        raise ValueError(msg)
    if z_arr.shape[0] != n:
        msg = f"Dimension mismatch: Z is {z_arr.shape[0]}x{z_arr.shape[1]} but x has {n} elements"
        raise ValueError(msg)
    if sector_codes and len(sector_codes) != n:
        msg = f"sector_codes length ({len(sector_codes)}) != dimension ({n})"
        raise ValueError(msg)

    sector_names = data.get("sector_names", {})
    base_year = data.get("base_year", 0)
    source = data.get("source", data.get("model_id", path.stem))

    metadata = {
        k: v for k, v in data.items()
        if k not in {"Z", "z_matrix", "x", "x_vector", "sector_codes", "sector_names"}
    }

    return IOModelData(
        Z=z_arr,
        x=x_arr,
        sector_codes=sector_codes,
        sector_names=sector_names,
        base_year=base_year,
        source=source,
        metadata=metadata,
    )


def load_from_excel(
    path: str | Path,  # noqa: ARG001
    config: ExcelSheetConfig | None = None,  # noqa: ARG001
) -> IOModelData:
    """Load IO model from Excel (stub for future GASTAT integration).

    Raises:
        NotImplementedError: Always — Excel loading planned for GASTAT integration.
    """
    raise NotImplementedError(
        "Excel loading is planned for GASTAT integration. "
        "Use load_from_json() with curated data for now."
    )


def load_satellites_from_json(path: str | Path) -> SatelliteData:
    """Load satellite coefficients from JSON.

    Amendment 3: Includes per-sector confidence arrays.

    Raises:
        FileNotFoundError: If path does not exist.
        ValueError: If JSON is missing required fields.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    sector_codes = data.get("sector_codes", [])
    n = len(sector_codes)

    emp = data.get("employment", {})
    imp = data.get("import_ratios", {})
    va = data.get("va_ratios", {})

    jobs_coeff = np.array(emp.get("jobs_per_sar_million", []), dtype=np.float64)
    import_ratio = np.array(imp.get("values", []), dtype=np.float64)
    va_ratio = np.array(va.get("values", []), dtype=np.float64)

    if len(jobs_coeff) != n:
        msg = f"employment vector length ({len(jobs_coeff)}) != sector count ({n})"
        raise ValueError(msg)
    if len(import_ratio) != n:
        msg = f"import_ratio vector length ({len(import_ratio)}) != sector count ({n})"
        raise ValueError(msg)
    if len(va_ratio) != n:
        msg = f"va_ratio vector length ({len(va_ratio)}) != sector count ({n})"
        raise ValueError(msg)

    emp_conf = emp.get("confidence", ["unknown"] * n)
    imp_conf = imp.get("confidence", ["unknown"] * n)
    va_conf = va.get("confidence", ["unknown"] * n)

    metadata = {
        k: v for k, v in data.items()
        if k not in {"sector_codes", "employment", "import_ratios", "va_ratios"}
    }

    return SatelliteData(
        sector_codes=sector_codes,
        jobs_coeff=jobs_coeff,
        import_ratio=import_ratio,
        va_ratio=va_ratio,
        employment_confidence=list(emp_conf),
        import_confidence=list(imp_conf),
        va_confidence=list(va_conf),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_model(
    Z: np.ndarray,
    x: np.ndarray,
    sector_codes: list[str] | None = None,
) -> ValidationResult:
    """Comprehensive IO model validation with diagnostics.

    Checks:
    1. Z non-negativity
    2. x positivity (no zero-output sectors)
    3. Dimension consistency
    4. Spectral radius of A < 1 (productivity condition)
    5. Value-added positive for all sectors (column sums of A < 1)
    6. Leontief inverse B = (I-A)^{-1} is non-negative
    7. Output multipliers in reasonable range [1.0, 5.0]
    """
    Z = np.asarray(Z, dtype=np.float64)
    x = np.asarray(x, dtype=np.float64)
    n = len(x)

    if sector_codes is None:
        sector_codes = [f"S{i}" for i in range(n)]

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Z non-negativity
    all_z_nonneg = bool(np.all(Z >= 0))
    if not all_z_nonneg:
        neg_count = int(np.sum(Z < 0))
        errors.append(f"Z has {neg_count} negative entries")

    # 2. x positivity
    all_x_pos = bool(np.all(x > 0))
    if not all_x_pos:
        bad = [sector_codes[i] for i in range(n) if x[i] <= 0]
        errors.append(f"Zero or negative output in sectors: {bad}")

    # 3. Dimension consistency
    if Z.ndim != 2 or Z.shape[0] != Z.shape[1] or Z.shape[0] != n:
        errors.append(f"Dimension mismatch: Z shape {Z.shape}, x length {n}")

    # Compute A (only if x is valid)
    spectral_radius = 0.0
    all_va_positive = False
    b_nonneg = False
    multiplier_dict: dict[str, float] = {}
    va_dict: dict[str, float] = {}
    col_sums_dict: dict[str, float] = {}

    if all_x_pos and Z.shape == (n, n):
        A = Z / x[np.newaxis, :]

        # 4. Spectral radius
        eigenvalues = np.linalg.eigvals(A)
        spectral_radius = float(np.max(np.abs(eigenvalues)))
        if spectral_radius >= 1.0:
            errors.append(
                f"Spectral radius = {spectral_radius:.6f} (must be < 1)"
            )

        # 5. Value-added positive (column sums of A < 1)
        col_sums = A.sum(axis=0)
        col_sums_dict = {sector_codes[i]: float(col_sums[i]) for i in range(n)}
        va_arr = 1.0 - col_sums
        va_dict = {sector_codes[i]: float(va_arr[i]) for i in range(n)}
        all_va_positive = bool(np.all(va_arr > 0))
        if not all_va_positive:
            bad = [
                f"{sector_codes[i]} (VA={va_arr[i]:.4f})"
                for i in range(n) if va_arr[i] <= 0
            ]
            errors.append(f"Negative value-added: {bad}")

        # 6. Leontief inverse B
        if spectral_radius < 1.0:
            I_minus_A = np.eye(n) - A
            B = scipy_linalg.solve(I_minus_A, np.eye(n))
            b_nonneg = bool(np.all(B >= -1e-10))
            if not b_nonneg:
                neg_b = int(np.sum(B < -1e-10))
                errors.append(f"Leontief inverse has {neg_b} negative entries")

            # 7. Output multipliers
            multipliers = B.sum(axis=0)
            multiplier_dict = {
                sector_codes[i]: round(float(multipliers[i]), 4)
                for i in range(n)
            }
            for i in range(n):
                m = multipliers[i]
                if m < 1.0:
                    warnings.append(
                        f"Multiplier for {sector_codes[i]} = {m:.4f} (< 1.0)"
                    )
                elif m > 5.0:
                    warnings.append(
                        f"Multiplier for {sector_codes[i]} = {m:.4f} (> 5.0)"
                    )

    total_output = float(np.sum(x))
    # Amendment 7: VA is value added (≈ GDP), NOT total output
    va_values = np.array(list(va_dict.values())) if va_dict else np.zeros(0)
    x_arr = np.array([x[i] for i in range(n)]) if all_x_pos else np.zeros(0)
    total_va = float(np.sum(va_values * x_arr)) if len(va_values) == n else 0.0

    is_valid = len(errors) == 0

    return ValidationResult(
        is_valid=is_valid,
        spectral_radius=spectral_radius,
        all_z_nonnegative=all_z_nonneg,
        all_x_positive=all_x_pos,
        all_va_positive=all_va_positive,
        b_nonnegative=b_nonneg,
        output_multipliers=multiplier_dict,
        va_ratios=va_dict,
        column_sums_a=col_sums_dict,
        total_output=total_output,
        total_value_added=total_va,
        errors=errors,
        warnings=warnings,
    )
