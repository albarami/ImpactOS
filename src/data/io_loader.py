"""IO model loader — loads curated JSON/Excel into ModelStore-compatible format.

Provides:
  load_from_json(path) -> IOModelData
  load_from_excel(path, config) -> IOModelData (stub for GASTAT)
  validate_model(Z, x, sector_codes) -> ValidationResult
  load_satellites_from_json(path) -> SatelliteData

D-1: Saudi Base IO Model Loading.
"""

from __future__ import annotations

import hashlib
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
    final_demand_F: np.ndarray | None = None
    imports_vector: np.ndarray | None = None
    compensation_of_employees: np.ndarray | None = None
    gross_operating_surplus: np.ndarray | None = None
    taxes_less_subsidies: np.ndarray | None = None
    household_consumption_shares: np.ndarray | None = None
    deflator_series: dict[int, float] | None = None


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


class ModelArtifactValidationError(ValueError):
    """Validation error for optional model artifacts with stable reason code."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code
        self.message = message


def _json_default(value: object) -> object:
    """Normalize numpy/scalar values for canonical JSON hashing."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer | np.floating):
        return value.item()
    return value


def compute_model_artifact_checksum(payload: dict[str, object]) -> str:
    """Compute deterministic SHA256 checksum over canonicalized model artifacts."""
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def validate_extended_model_artifacts(
    *,
    n: int,
    final_demand_F: list[list[float]] | None,
    imports_vector: list[float] | None,
    compensation_of_employees: list[float] | None,
    gross_operating_surplus: list[float] | None,
    taxes_less_subsidies: list[float] | None,
    household_consumption_shares: list[float] | None,
    deflator_series: dict[str, float] | dict[int, float] | None,
) -> dict[str, object]:
    """Validate/normalize optional Phase 2-E artifact fields against model dimension."""
    out: dict[str, object] = {}

    if final_demand_F is not None:
        arr = np.asarray(final_demand_F, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[0] != n or arr.shape[1] <= 0:
            raise ModelArtifactValidationError(
                "MODEL_FINAL_DEMAND_DIMENSION_MISMATCH",
                f"final_demand_F must have shape ({n}, k>0), got {arr.shape}.",
            )
        out["final_demand_F"] = arr

    def _validate_vector(
        raw: list[float] | None,
        *,
        key: str,
        reason_code: str,
    ) -> np.ndarray | None:
        if raw is None:
            return None
        vec = np.asarray(raw, dtype=np.float64)
        if vec.ndim != 1 or vec.shape[0] != n:
            raise ModelArtifactValidationError(
                reason_code,
                f"{key} must be a vector of length {n}, got shape {vec.shape}.",
            )
        return vec

    imports = _validate_vector(
        imports_vector,
        key="imports_vector",
        reason_code="MODEL_IMPORTS_VECTOR_DIMENSION_MISMATCH",
    )
    if imports is not None:
        out["imports_vector"] = imports

    wages = _validate_vector(
        compensation_of_employees,
        key="compensation_of_employees",
        reason_code="MODEL_COMPENSATION_VECTOR_DIMENSION_MISMATCH",
    )
    if wages is not None:
        out["compensation_of_employees"] = wages

    gos = _validate_vector(
        gross_operating_surplus,
        key="gross_operating_surplus",
        reason_code="MODEL_GOS_VECTOR_DIMENSION_MISMATCH",
    )
    if gos is not None:
        out["gross_operating_surplus"] = gos

    taxes = _validate_vector(
        taxes_less_subsidies,
        key="taxes_less_subsidies",
        reason_code="MODEL_TAX_VECTOR_DIMENSION_MISMATCH",
    )
    if taxes is not None:
        out["taxes_less_subsidies"] = taxes

    hh = _validate_vector(
        household_consumption_shares,
        key="household_consumption_shares",
        reason_code="MODEL_HOUSEHOLD_SHARES_DIMENSION_MISMATCH",
    )
    if hh is not None:
        total = float(np.sum(hh))
        if not np.isclose(total, 1.0, atol=1e-6):
            raise ModelArtifactValidationError(
                "MODEL_HOUSEHOLD_SHARES_INVALID_SUM",
                f"household_consumption_shares must sum to 1.0, got {total:.6f}.",
            )
        if np.any(hh < 0):
            raise ModelArtifactValidationError(
                "MODEL_HOUSEHOLD_SHARES_NEGATIVE",
                "household_consumption_shares must be non-negative.",
            )
        out["household_consumption_shares"] = hh

    if deflator_series is not None:
        normalized_deflators: dict[int, float] = {}
        for k, v in deflator_series.items():
            try:
                year = int(k)
            except (TypeError, ValueError) as exc:
                raise ModelArtifactValidationError(
                    "MODEL_DEFLATOR_INVALID",
                    f"deflator year key must be integer-like, got '{k}'.",
                ) from exc
            try:
                value = float(v)
            except (TypeError, ValueError) as exc:
                raise ModelArtifactValidationError(
                    "MODEL_DEFLATOR_INVALID",
                    f"deflator value for year {year} must be numeric.",
                ) from exc
            if value <= 0:
                raise ModelArtifactValidationError(
                    "MODEL_DEFLATOR_INVALID",
                    f"deflator value for year {year} must be > 0, got {value}.",
                )
            normalized_deflators[year] = value
        out["deflator_series"] = normalized_deflators

    return out


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

    validated_artifacts = validate_extended_model_artifacts(
        n=n,
        final_demand_F=data.get("final_demand_F"),
        imports_vector=data.get("imports_vector"),
        compensation_of_employees=data.get("compensation_of_employees"),
        gross_operating_surplus=data.get("gross_operating_surplus"),
        taxes_less_subsidies=data.get("taxes_less_subsidies"),
        household_consumption_shares=data.get("household_consumption_shares"),
        deflator_series=data.get("deflator_series"),
    )

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
        final_demand_F=validated_artifacts.get("final_demand_F"),
        imports_vector=validated_artifacts.get("imports_vector"),
        compensation_of_employees=validated_artifacts.get("compensation_of_employees"),
        gross_operating_surplus=validated_artifacts.get("gross_operating_surplus"),
        taxes_less_subsidies=validated_artifacts.get("taxes_less_subsidies"),
        household_consumption_shares=validated_artifacts.get("household_consumption_shares"),
        deflator_series=validated_artifacts.get("deflator_series"),
    )


def load_from_excel(
    path: str | Path,
    config: ExcelSheetConfig | None = None,  # noqa: ARG001
) -> IOModelData:
    """Load IO model from Excel workbook.

    Routes by extension:
      .xlsb, .xlsx -> SG model adapter
      Other -> raises SGImportError with SG_UNSUPPORTED_FORMAT

    config parameter reserved for future GASTAT integration.
    """
    from src.data.sg_model_adapter import SGImportError, extract_io_model

    p = Path(path)
    ext = p.suffix.lower()

    if ext not in (".xlsb", ".xlsx"):
        raise SGImportError(
            "SG_UNSUPPORTED_FORMAT",
            f"Unsupported file extension '{ext}'. Expected .xlsb or .xlsx.",
        )

    return extract_io_model(p)


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
