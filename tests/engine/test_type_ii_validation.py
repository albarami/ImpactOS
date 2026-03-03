"""Tests for Type II prerequisite validation with structured reason codes.

Covers ALL reason codes and error behavior:
- TYPE_II_MISSING_COMPENSATION
- TYPE_II_MISSING_HOUSEHOLD_SHARES
- TYPE_II_DIMENSION_MISMATCH
- TYPE_II_NEGATIVE_VALUES
- TYPE_II_INVALID_SHARE_SUM
- TYPE_II_NONFINITE_WAGE_COEFFICIENTS
"""

import numpy as np
import pytest

from src.engine.type_ii_validation import (
    TypeIIValidationError,
    TypeIIValidationResult,
    validate_type_ii_prerequisites,
)

# ---------------------------------------------------------------------------
# Valid inputs
# ---------------------------------------------------------------------------


class TestTypeIIValidation:
    """Type II prerequisite validation with reason codes."""

    def test_valid_inputs_pass(self) -> None:
        """Valid compensation and household shares return is_valid=True."""
        n = 3
        x = np.array([1000.0, 2000.0, 1500.0])
        comp = np.array([350.0, 900.0, 825.0])
        shares = np.array([0.30, 0.45, 0.20])

        result = validate_type_ii_prerequisites(
            n=n, x=x,
            compensation_of_employees=comp,
            household_consumption_shares=shares,
        )
        assert isinstance(result, TypeIIValidationResult)
        assert result.is_valid is True
        assert result.compensation.shape == (3,)
        assert result.household_shares.shape == (3,)
        assert result.wage_coefficients.shape == (3,)

    def test_missing_compensation_raises(self) -> None:
        """None compensation raises with TYPE_II_MISSING_COMPENSATION."""
        with pytest.raises(TypeIIValidationError, match="compensation_of_employees") as exc_info:
            validate_type_ii_prerequisites(
                n=3,
                x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=None,
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )
        assert exc_info.value.reason_code == "TYPE_II_MISSING_COMPENSATION"

    def test_missing_shares_raises(self) -> None:
        """None household shares raises with TYPE_II_MISSING_HOUSEHOLD_SHARES."""
        with pytest.raises(TypeIIValidationError, match="household_consumption_shares") as exc_info:
            validate_type_ii_prerequisites(
                n=3,
                x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=np.array([350.0, 900.0, 825.0]),
                household_consumption_shares=None,
            )
        assert exc_info.value.reason_code == "TYPE_II_MISSING_HOUSEHOLD_SHARES"

    def test_dimension_mismatch_raises(self) -> None:
        """Wrong-length compensation raises with TYPE_II_DIMENSION_MISMATCH."""
        with pytest.raises(TypeIIValidationError) as exc_info:
            validate_type_ii_prerequisites(
                n=3,
                x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=np.array([350.0, 900.0]),  # only 2 elements
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )
        assert exc_info.value.reason_code == "TYPE_II_DIMENSION_MISMATCH"

    def test_negative_values_raises(self) -> None:
        """Negative compensation raises with TYPE_II_NEGATIVE_VALUES."""
        with pytest.raises(TypeIIValidationError, match="negative") as exc_info:
            validate_type_ii_prerequisites(
                n=3,
                x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=np.array([-100.0, 900.0, 825.0]),
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )
        assert exc_info.value.reason_code == "TYPE_II_NEGATIVE_VALUES"

    def test_negative_shares_raises(self) -> None:
        """Negative household shares raises with TYPE_II_NEGATIVE_VALUES."""
        with pytest.raises(TypeIIValidationError, match="negative") as exc_info:
            validate_type_ii_prerequisites(
                n=3,
                x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=np.array([350.0, 900.0, 825.0]),
                household_consumption_shares=np.array([0.30, -0.10, 0.20]),
            )
        assert exc_info.value.reason_code == "TYPE_II_NEGATIVE_VALUES"

    def test_invalid_share_sum_too_high(self) -> None:
        """Shares summing > 1.0 raises with TYPE_II_INVALID_SHARE_SUM."""
        with pytest.raises(TypeIIValidationError, match="sum") as exc_info:
            validate_type_ii_prerequisites(
                n=3,
                x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=np.array([350.0, 900.0, 825.0]),
                household_consumption_shares=np.array([0.50, 0.40, 0.20]),  # sum=1.1
            )
        assert exc_info.value.reason_code == "TYPE_II_INVALID_SHARE_SUM"

    def test_invalid_share_sum_zero(self) -> None:
        """All-zero shares (sum=0) raises with TYPE_II_INVALID_SHARE_SUM."""
        with pytest.raises(TypeIIValidationError, match="sum") as exc_info:
            validate_type_ii_prerequisites(
                n=3,
                x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=np.array([350.0, 900.0, 825.0]),
                household_consumption_shares=np.array([0.0, 0.0, 0.0]),
            )
        assert exc_info.value.reason_code == "TYPE_II_INVALID_SHARE_SUM"

    def test_nonfinite_wage_coefficients(self) -> None:
        """Zero output sector causing inf wage coefficient raises."""
        with pytest.raises(TypeIIValidationError, match="non-finite") as exc_info:
            validate_type_ii_prerequisites(
                n=3,
                x=np.array([1000.0, 0.0, 1500.0]),  # zero output in sector 2
                compensation_of_employees=np.array([350.0, 900.0, 825.0]),
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )
        assert exc_info.value.reason_code == "TYPE_II_NONFINITE_WAGE_COEFFICIENTS"

    def test_error_has_reason_code_attribute(self) -> None:
        """TypeIIValidationError has a structured reason_code attribute."""
        try:
            validate_type_ii_prerequisites(
                n=3,
                x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=None,
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )
            pytest.fail("Expected TypeIIValidationError")
        except TypeIIValidationError as exc:
            assert hasattr(exc, "reason_code")
            assert isinstance(exc.reason_code, str)
            assert exc.reason_code.startswith("TYPE_II_")

    def test_no_secrets_in_error_message(self) -> None:
        """Error messages do not leak API keys or tokens."""
        sensitive_patterns = ["api_key", "token", "secret", "password", "bearer"]
        try:
            validate_type_ii_prerequisites(
                n=3,
                x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=None,
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )
        except TypeIIValidationError as exc:
            msg_lower = str(exc).lower()
            for pattern in sensitive_patterns:
                assert pattern not in msg_lower, (
                    f"Error message contains sensitive pattern: {pattern}"
                )
