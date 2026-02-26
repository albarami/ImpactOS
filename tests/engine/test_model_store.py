"""Tests for ModelVersion management (MVP-3 Section 7.1, 7.2, 7.6).

Covers: Z/x storage, A computation, Leontief inverse B=(I-A)^-1,
productivity validation (spectral radius, non-negativity), caching.
"""

import hashlib

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.engine.model_store import ModelStore


# ---------------------------------------------------------------------------
# Helpers: build well-known I-O data
# ---------------------------------------------------------------------------

def _simple_2x2() -> tuple[np.ndarray, np.ndarray]:
    """Simple 2-sector economy.

    Z = [[150, 500],    x = [1000, 2000]
         [200, 100]]
    A = [[0.15, 0.25],
         [0.20, 0.05]]
    Spectral radius of A ≈ 0.34 < 1 ✓
    """
    Z = np.array([[150.0, 500.0],
                   [200.0, 100.0]])
    x = np.array([1000.0, 2000.0])
    return Z, x


def _simple_3x3() -> tuple[np.ndarray, np.ndarray]:
    """3-sector economy for richer tests."""
    Z = np.array([
        [10.0, 20.0, 5.0],
        [15.0, 5.0,  10.0],
        [5.0,  10.0, 2.0],
    ])
    x = np.array([100.0, 80.0, 50.0])
    return Z, x


def _unstable_economy() -> tuple[np.ndarray, np.ndarray]:
    """Economy where spectral radius of A >= 1 (invalid).

    A = [[0.95, 0.5], [0.5, 0.95]], spectral radius = 1.45.
    """
    Z = np.array([[950.0, 500.0],
                   [500.0, 950.0]])
    x = np.array([1000.0, 1000.0])
    return Z, x


SECTOR_CODES_2 = ["S1", "S2"]
SECTOR_CODES_3 = ["S1", "S2", "S3"]


# ===================================================================
# Store and retrieve model
# ===================================================================


class TestModelStoreAndRetrieve:
    """Store Z, x and retrieve a loaded model."""

    def test_register_returns_model_version(self) -> None:
        store = ModelStore()
        Z, x = _simple_2x2()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_2,
            base_year=2023, source="GASTAT 2023",
        )
        assert mv.sector_count == 2
        assert mv.base_year == 2023

    def test_register_computes_checksum(self) -> None:
        store = ModelStore()
        Z, x = _simple_2x2()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_2,
            base_year=2023, source="GASTAT 2023",
        )
        assert mv.checksum.startswith("sha256:")

    def test_get_returns_stored_data(self) -> None:
        store = ModelStore()
        Z, x = _simple_2x2()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_2,
            base_year=2023, source="GASTAT 2023",
        )
        loaded = store.get(mv.model_version_id)
        np.testing.assert_array_almost_equal(loaded.Z, Z)
        np.testing.assert_array_almost_equal(loaded.x, x)
        assert loaded.sector_codes == SECTOR_CODES_2

    def test_get_nonexistent_raises(self) -> None:
        store = ModelStore()
        with pytest.raises(KeyError):
            store.get(uuid7())


# ===================================================================
# Technical coefficients matrix A
# ===================================================================


class TestTechnicalCoefficients:
    """A = Z * diag(x)^(-1)."""

    def test_A_computation_2x2(self) -> None:
        store = ModelStore()
        Z, x = _simple_2x2()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_2,
            base_year=2023, source="test",
        )
        loaded = store.get(mv.model_version_id)
        A = loaded.A
        expected_A = np.array([[0.15, 0.25],
                                [0.20, 0.05]])
        np.testing.assert_array_almost_equal(A, expected_A)

    def test_A_computation_3x3(self) -> None:
        store = ModelStore()
        Z, x = _simple_3x3()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_3,
            base_year=2023, source="test",
        )
        loaded = store.get(mv.model_version_id)
        # A[i,j] = Z[i,j] / x[j]
        expected_A = Z / x[np.newaxis, :]
        np.testing.assert_array_almost_equal(loaded.A, expected_A)

    def test_A_columns_sum_less_than_one(self) -> None:
        """For a productive economy, column sums of A < 1."""
        store = ModelStore()
        Z, x = _simple_2x2()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_2,
            base_year=2023, source="test",
        )
        loaded = store.get(mv.model_version_id)
        col_sums = loaded.A.sum(axis=0)
        assert all(s < 1.0 for s in col_sums)


# ===================================================================
# Leontief inverse B = (I - A)^(-1)
# ===================================================================


class TestLeontiefInverse:
    """B = (I - A)^(-1) computation and caching."""

    def test_B_computed(self) -> None:
        store = ModelStore()
        Z, x = _simple_2x2()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_2,
            base_year=2023, source="test",
        )
        loaded = store.get(mv.model_version_id)
        B = loaded.B
        assert B.shape == (2, 2)

    def test_B_identity_property(self) -> None:
        """B · (I - A) should equal I."""
        store = ModelStore()
        Z, x = _simple_2x2()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_2,
            base_year=2023, source="test",
        )
        loaded = store.get(mv.model_version_id)
        I_minus_A = np.eye(2) - loaded.A
        product = loaded.B @ I_minus_A
        np.testing.assert_array_almost_equal(product, np.eye(2), decimal=10)

    def test_B_diagonal_ge_one(self) -> None:
        """Diagonal entries of B should be >= 1."""
        store = ModelStore()
        Z, x = _simple_2x2()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_2,
            base_year=2023, source="test",
        )
        loaded = store.get(mv.model_version_id)
        for i in range(2):
            assert loaded.B[i, i] >= 1.0

    def test_B_non_negative(self) -> None:
        """All entries of B should be non-negative."""
        store = ModelStore()
        Z, x = _simple_2x2()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_2,
            base_year=2023, source="test",
        )
        loaded = store.get(mv.model_version_id)
        assert np.all(loaded.B >= 0)

    def test_B_cached(self) -> None:
        """B is cached — same object returned on repeated access."""
        store = ModelStore()
        Z, x = _simple_2x2()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_2,
            base_year=2023, source="test",
        )
        loaded = store.get(mv.model_version_id)
        B1 = loaded.B
        B2 = loaded.B
        assert B1 is B2

    def test_B_3x3(self) -> None:
        store = ModelStore()
        Z, x = _simple_3x3()
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_3,
            base_year=2023, source="test",
        )
        loaded = store.get(mv.model_version_id)
        I_minus_A = np.eye(3) - loaded.A
        product = loaded.B @ I_minus_A
        np.testing.assert_array_almost_equal(product, np.eye(3), decimal=10)


# ===================================================================
# Productivity validation
# ===================================================================


class TestProductivityValidation:
    """Spectral radius of A < 1 and non-negativity checks."""

    def test_valid_economy_passes(self) -> None:
        store = ModelStore()
        Z, x = _simple_2x2()
        # Should not raise
        mv = store.register(
            Z=Z, x=x, sector_codes=SECTOR_CODES_2,
            base_year=2023, source="test",
        )
        assert mv is not None

    def test_unstable_economy_raises(self) -> None:
        store = ModelStore()
        Z, x = _unstable_economy()
        with pytest.raises(ValueError, match="spectral radius"):
            store.register(
                Z=Z, x=x, sector_codes=["S1", "S2"],
                base_year=2023, source="test",
            )

    def test_negative_Z_entries_raises(self) -> None:
        store = ModelStore()
        Z = np.array([[-10.0, 20.0],
                       [15.0,  5.0]])
        x = np.array([100.0, 80.0])
        with pytest.raises(ValueError, match="non-negative"):
            store.register(
                Z=Z, x=x, sector_codes=["S1", "S2"],
                base_year=2023, source="test",
            )

    def test_zero_output_sector_raises(self) -> None:
        store = ModelStore()
        Z = np.array([[10.0, 20.0],
                       [15.0,  5.0]])
        x = np.array([100.0, 0.0])
        with pytest.raises(ValueError, match="zero.*output"):
            store.register(
                Z=Z, x=x, sector_codes=["S1", "S2"],
                base_year=2023, source="test",
            )

    def test_dimension_mismatch_raises(self) -> None:
        store = ModelStore()
        Z = np.array([[10.0, 20.0],
                       [15.0,  5.0]])
        x = np.array([100.0, 80.0, 50.0])  # wrong size
        with pytest.raises(ValueError, match="dimension"):
            store.register(
                Z=Z, x=x, sector_codes=["S1", "S2"],
                base_year=2023, source="test",
            )

    def test_sector_codes_mismatch_raises(self) -> None:
        store = ModelStore()
        Z, x = _simple_2x2()
        with pytest.raises(ValueError, match="sector_codes"):
            store.register(
                Z=Z, x=x, sector_codes=["S1", "S2", "S3"],
                base_year=2023, source="test",
            )
