"""Value-measures prerequisite validation with structured reason codes (Sprint 16).

Mirrors the Type II validation pattern from type_ii_validation.py (Sprint 15).
"""

from dataclasses import dataclass

import numpy as np

# Standard final demand column indices (SNA convention)
FD_COL_HOUSEHOLD = 0
FD_COL_GOVERNMENT = 1
FD_COL_INVESTMENT = 2
FD_COL_EXPORTS = 3
FD_MIN_COLUMNS = 4


class ValueMeasuresValidationError(Exception):
    """Raised when value-measures prerequisites are invalid.

    Carries structured fields for API error translation (mirrors Issue #17 pattern).
    """

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        environment: str = "",
        measure: str = "",
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.environment = environment
        self.measure = measure


@dataclass(frozen=True)
class ValueMeasuresValidationResult:
    is_valid: bool
    gos: np.ndarray
    taxes: np.ndarray
    final_demand_f: np.ndarray
    imports_vector: np.ndarray
    deflator: float
    tax_ratio: np.ndarray
    export_ratio: np.ndarray
    gov_spending_ratio: np.ndarray


def validate_value_measures_prerequisites(
    *,
    n: int,
    x: np.ndarray,
    gross_operating_surplus: np.ndarray | None,
    taxes_less_subsidies: np.ndarray | None,
    final_demand_f: np.ndarray | None,
    imports_vector: np.ndarray | None,
    deflator_series: dict[int, float] | None,
    base_year: int,
) -> ValueMeasuresValidationResult:
    """Validate all value-measures prerequisites.

    Raises ValueMeasuresValidationError with structured reason_code on failure.
    Returns validated arrays and pre-computed ratios on success.
    """
    # --- Presence checks ---
    if gross_operating_surplus is None:
        raise ValueMeasuresValidationError(
            "gross_operating_surplus is required for value measures.",
            reason_code="VM_MISSING_GOS",
        )
    if taxes_less_subsidies is None:
        raise ValueMeasuresValidationError(
            "taxes_less_subsidies is required for value measures.",
            reason_code="VM_MISSING_TAXES",
        )
    if final_demand_f is None:
        raise ValueMeasuresValidationError(
            "final_demand_F is required for value measures.",
            reason_code="VM_MISSING_FINAL_DEMAND",
        )
    if imports_vector is None:
        raise ValueMeasuresValidationError(
            "imports_vector is required for value measures.",
            reason_code="VM_MISSING_IMPORTS",
        )
    if deflator_series is None:
        raise ValueMeasuresValidationError(
            "deflator_series is required for value measures.",
            reason_code="VM_MISSING_DEFLATOR",
        )

    # --- Convert to numpy ---
    gos = np.asarray(gross_operating_surplus, dtype=np.float64)
    taxes = np.asarray(taxes_less_subsidies, dtype=np.float64)
    fd = np.asarray(final_demand_f, dtype=np.float64)
    imp = np.asarray(imports_vector, dtype=np.float64)
    x_arr = np.asarray(x, dtype=np.float64)

    # --- Dimension checks ---
    if gos.shape != (n,):
        raise ValueMeasuresValidationError(
            f"gross_operating_surplus has {gos.shape[0]} elements, expected {n}.",
            reason_code="VM_DIMENSION_MISMATCH",
        )
    if taxes.shape != (n,):
        raise ValueMeasuresValidationError(
            f"taxes_less_subsidies has {taxes.shape[0]} elements, expected {n}.",
            reason_code="VM_DIMENSION_MISMATCH",
        )
    if imp.shape != (n,):
        raise ValueMeasuresValidationError(
            f"imports_vector has {imp.shape[0]} elements, expected {n}.",
            reason_code="VM_DIMENSION_MISMATCH",
        )
    if fd.ndim != 2 or fd.shape[0] != n:
        raise ValueMeasuresValidationError(
            f"final_demand_F must be ({n}, k) matrix, got {fd.shape}.",
            reason_code="VM_INVALID_FINAL_DEMAND",
        )
    if fd.shape[1] < FD_MIN_COLUMNS:
        raise ValueMeasuresValidationError(
            f"final_demand_F must have >= {FD_MIN_COLUMNS} columns "
            f"(Household, Government, Investment, Exports), got {fd.shape[1]}.",
            reason_code="VM_INVALID_FINAL_DEMAND",
        )

    # --- Value checks ---
    if np.any(gos < 0):
        raise ValueMeasuresValidationError(
            "gross_operating_surplus contains negative values.",
            reason_code="VM_INVALID_GOS",
        )
    if not np.all(np.isfinite(gos)):
        raise ValueMeasuresValidationError(
            "gross_operating_surplus contains non-finite values.",
            reason_code="VM_INVALID_GOS",
        )
    if not np.all(np.isfinite(taxes)):
        raise ValueMeasuresValidationError(
            "taxes_less_subsidies contains non-finite values.",
            reason_code="VM_INVALID_TAXES",
        )
    if np.any(imp < 0):
        raise ValueMeasuresValidationError(
            "imports_vector contains negative values.",
            reason_code="VM_INVALID_IMPORTS",
        )
    if not np.all(np.isfinite(fd)):
        raise ValueMeasuresValidationError(
            "final_demand_F contains non-finite values.",
            reason_code="VM_INVALID_FINAL_DEMAND",
        )

    # --- Deflator checks ---
    if base_year not in deflator_series:
        raise ValueMeasuresValidationError(
            f"deflator_series missing entry for base_year={base_year}.",
            reason_code="VM_INVALID_DEFLATOR",
        )
    deflator_val = deflator_series[base_year]
    if deflator_val <= 0 or not np.isfinite(deflator_val):
        raise ValueMeasuresValidationError(
            f"deflator for base_year={base_year} is {deflator_val} (must be > 0).",
            reason_code="VM_INVALID_DEFLATOR",
        )

    # --- Pre-compute ratios ---
    tax_ratio = taxes / x_arr
    export_ratio = fd[:, FD_COL_EXPORTS] / x_arr
    gov_spending_ratio = fd[:, FD_COL_GOVERNMENT] / x_arr

    if not np.all(np.isfinite(tax_ratio)):
        raise ValueMeasuresValidationError(
            "Tax ratios (taxes / output) contain non-finite values.",
            reason_code="VM_INVALID_TAXES",
        )

    return ValueMeasuresValidationResult(
        is_valid=True,
        gos=gos,
        taxes=taxes,
        final_demand_f=fd,
        imports_vector=imp,
        deflator=deflator_val,
        tax_ratio=tax_ratio,
        export_ratio=export_ratio,
        gov_spending_ratio=gov_spending_ratio,
    )
