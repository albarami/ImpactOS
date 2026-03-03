"""Type II prerequisite validation with structured reason codes."""

from dataclasses import dataclass

import numpy as np

_SHARE_SUM_TOLERANCE = 1e-6


class TypeIIValidationError(Exception):
    """Raised when Type II prerequisites are invalid."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class TypeIIValidationResult:
    is_valid: bool
    compensation: np.ndarray
    household_shares: np.ndarray
    wage_coefficients: np.ndarray


def validate_type_ii_prerequisites(
    *,
    n: int,
    x: np.ndarray,
    compensation_of_employees: np.ndarray | None,
    household_consumption_shares: np.ndarray | None,
) -> TypeIIValidationResult:
    """Validate Type II prerequisites. Raises TypeIIValidationError on failure."""
    if compensation_of_employees is None:
        raise TypeIIValidationError(
            "compensation_of_employees is required for Type II computation.",
            reason_code="TYPE_II_MISSING_COMPENSATION",
        )
    if household_consumption_shares is None:
        raise TypeIIValidationError(
            "household_consumption_shares is required for Type II computation.",
            reason_code="TYPE_II_MISSING_HOUSEHOLD_SHARES",
        )

    comp = np.asarray(compensation_of_employees, dtype=np.float64)
    shares = np.asarray(household_consumption_shares, dtype=np.float64)

    if comp.shape != (n,):
        raise TypeIIValidationError(
            f"compensation_of_employees has {comp.shape[0]} elements, expected {n}.",
            reason_code="TYPE_II_DIMENSION_MISMATCH",
        )
    if shares.shape != (n,):
        raise TypeIIValidationError(
            f"household_consumption_shares has {shares.shape[0]} elements, expected {n}.",
            reason_code="TYPE_II_DIMENSION_MISMATCH",
        )

    if np.any(comp < 0):
        raise TypeIIValidationError(
            "compensation_of_employees contains negative values.",
            reason_code="TYPE_II_NEGATIVE_VALUES",
        )
    if np.any(shares < 0):
        raise TypeIIValidationError(
            "household_consumption_shares contains negative values.",
            reason_code="TYPE_II_NEGATIVE_VALUES",
        )

    share_sum = float(np.sum(shares))
    if share_sum <= 0 or share_sum > 1.0 + _SHARE_SUM_TOLERANCE:
        raise TypeIIValidationError(
            f"household_consumption_shares sum is {share_sum:.6f} (must be in (0, 1]).",
            reason_code="TYPE_II_INVALID_SHARE_SUM",
        )

    w = comp / np.asarray(x, dtype=np.float64)
    if not np.all(np.isfinite(w)):
        raise TypeIIValidationError(
            "Wage coefficients (compensation / output) contain non-finite values. "
            "Check for zero-output sectors.",
            reason_code="TYPE_II_NONFINITE_WAGE_COEFFICIENTS",
        )

    return TypeIIValidationResult(
        is_valid=True,
        compensation=comp,
        household_shares=shares,
        wage_coefficients=w,
    )
