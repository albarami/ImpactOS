"""Tests for RAS matrix balancing (MVP-3 Section 7.7).

Covers: RAS iteration convergence, row/column total matching,
ModelVersion output labeled as "balanced-nowcast".
"""

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.engine.model_store import ModelStore
from src.engine.ras import RASBalancer, RASResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _simple_Z_and_targets() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Base Z with new target row/column totals.

    Z0 = [[150, 500],    row sums = [650, 300]
           [200, 100]]    col sums = [350, 600]

    Target: r = [700, 350], c = [400, 650]
    """
    Z0 = np.array([[150.0, 500.0],
                    [200.0, 100.0]])
    r = np.array([700.0, 350.0])
    c = np.array([400.0, 650.0])
    return Z0, r, c


def _3x3_Z_and_targets() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    Z0 = np.array([
        [10.0, 20.0, 5.0],
        [15.0, 5.0,  10.0],
        [5.0,  10.0, 2.0],
    ])
    # New targets (slightly different from original sums)
    r = np.array([40.0, 35.0, 20.0])
    c = np.array([35.0, 38.0, 22.0])
    return Z0, r, c


# ===================================================================
# Basic RAS convergence
# ===================================================================


class TestRASConvergence:
    """RAS iterates until row/column totals match targets."""

    def test_returns_ras_result(self) -> None:
        Z0, r, c = _simple_Z_and_targets()
        balancer = RASBalancer()
        result = balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)
        assert isinstance(result, RASResult)

    def test_row_totals_match(self) -> None:
        Z0, r, c = _simple_Z_and_targets()
        balancer = RASBalancer()
        result = balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)

        actual_row_sums = result.Z_balanced.sum(axis=1)
        np.testing.assert_array_almost_equal(actual_row_sums, r, decimal=6)

    def test_col_totals_match(self) -> None:
        Z0, r, c = _simple_Z_and_targets()
        balancer = RASBalancer()
        result = balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)

        actual_col_sums = result.Z_balanced.sum(axis=0)
        np.testing.assert_array_almost_equal(actual_col_sums, c, decimal=6)

    def test_non_negative_output(self) -> None:
        Z0, r, c = _simple_Z_and_targets()
        balancer = RASBalancer()
        result = balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)
        assert np.all(result.Z_balanced >= 0)

    def test_preserves_zero_structure(self) -> None:
        """If Z0[i,j] = 0, then Z*[i,j] = 0 (RAS preserves zeros)."""
        Z0 = np.array([[100.0, 0.0],
                        [50.0,  200.0]])
        r = np.array([120.0, 300.0])
        c = np.array([180.0, 240.0])
        balancer = RASBalancer()
        result = balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)
        assert result.Z_balanced[0, 1] == 0.0

    def test_3x3_convergence(self) -> None:
        Z0, r, c = _3x3_Z_and_targets()
        balancer = RASBalancer()
        result = balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)

        np.testing.assert_array_almost_equal(
            result.Z_balanced.sum(axis=1), r, decimal=6,
        )
        np.testing.assert_array_almost_equal(
            result.Z_balanced.sum(axis=0), c, decimal=6,
        )

    def test_converged_flag(self) -> None:
        Z0, r, c = _simple_Z_and_targets()
        balancer = RASBalancer()
        result = balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)
        assert result.converged is True

    def test_iteration_count(self) -> None:
        Z0, r, c = _simple_Z_and_targets()
        balancer = RASBalancer()
        result = balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)
        assert result.iterations > 0
        assert result.iterations < 1000


# ===================================================================
# RAS → ModelVersion
# ===================================================================


class TestRASToModelVersion:
    """RAS output creates a new ModelVersion labeled balanced-nowcast."""

    def test_creates_model_version(self) -> None:
        Z0, r, c = _simple_Z_and_targets()
        x_new = r + c  # simple new output = intermediate inputs + intermediate outputs
        store = ModelStore()
        balancer = RASBalancer()

        result = balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)
        mv = balancer.to_model_version(
            ras_result=result,
            x_new=x_new,
            sector_codes=["S1", "S2"],
            base_year=2024,
            store=store,
        )
        assert mv.source == "balanced-nowcast"
        assert mv.base_year == 2024
        assert mv.sector_count == 2

    def test_registered_model_is_valid(self) -> None:
        Z0, r, c = _simple_Z_and_targets()
        x_new = r + c
        store = ModelStore()
        balancer = RASBalancer()

        result = balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)
        mv = balancer.to_model_version(
            ras_result=result,
            x_new=x_new,
            sector_codes=["S1", "S2"],
            base_year=2024,
            store=store,
        )
        loaded = store.get(mv.model_version_id)
        # Should have valid B matrix
        assert loaded.B.shape == (2, 2)


# ===================================================================
# Validation
# ===================================================================


class TestRASValidation:
    """RAS validates inputs."""

    def test_dimension_mismatch_raises(self) -> None:
        Z0 = np.array([[10.0, 20.0], [15.0, 5.0]])
        r = np.array([30.0, 20.0, 10.0])  # wrong size
        c = np.array([25.0, 25.0])
        balancer = RASBalancer()
        with pytest.raises(ValueError, match="dimension"):
            balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)

    def test_negative_targets_raises(self) -> None:
        Z0 = np.array([[10.0, 20.0], [15.0, 5.0]])
        r = np.array([-30.0, 20.0])
        c = np.array([25.0, 25.0])
        balancer = RASBalancer()
        with pytest.raises(ValueError, match="non-negative"):
            balancer.balance(Z0=Z0, target_row_totals=r, target_col_totals=c)

    def test_custom_tolerance(self) -> None:
        Z0, r, c = _simple_Z_and_targets()
        balancer = RASBalancer()
        result = balancer.balance(
            Z0=Z0, target_row_totals=r, target_col_totals=c, tolerance=1e-12,
        )
        assert result.converged is True
