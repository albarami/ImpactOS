"""Golden-run regression tests — MVP-14.

PERMANENT regression test with hand-verified expected values for a 2-sector
IO model. NEVER remove this test. If it fails, something fundamental changed
in the Leontief engine.

Hand-verified math for Z=[[150,500],[200,100]], x=[1000,2000]:

    A = Z · diag(x)^{-1}
      = [[0.15, 0.25],
         [0.20, 0.05]]

    I - A = [[0.85, -0.25],
             [-0.20, 0.95]]

    det(I - A) = 0.85 × 0.95 - (-0.25)×(-0.20) = 0.8075 - 0.05 = 0.7575

    B = (I - A)^{-1} = (1/0.7575) × [[0.95, 0.25],
                                       [0.20, 0.85]]

    Shock: delta_d = [50.0, 0.0]

    delta_x_total = B @ delta_d:
      S1 = 0.95 × 50 / 0.7575 = 47.5 / 0.7575 = 62.706270627...
      S2 = 0.20 × 50 / 0.7575 = 10.0 / 0.7575 = 13.201320132...

    delta_x_direct = [50.0, 0.0]
    delta_x_indirect = [12.706270627..., 13.201320132...]
    sum(delta_x_total) = 75.907590759...

If the engine doesn't match, the ENGINE has a bug — do NOT adjust expected values.
"""

import numpy as np
import pytest

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import LoadedModel, ModelStore

# ---------------------------------------------------------------------------
# Hand-verified expected values
# ---------------------------------------------------------------------------

Z = np.array([[150.0, 500.0], [200.0, 100.0]])
X = np.array([1000.0, 2000.0])
SECTOR_CODES = ["S1", "S2"]

EXPECTED_A = np.array([
    [0.15, 0.25],
    [0.20, 0.05],
])

DET_I_MINUS_A = 0.7575

EXPECTED_B = np.array([
    [0.95 / DET_I_MINUS_A, 0.25 / DET_I_MINUS_A],
    [0.20 / DET_I_MINUS_A, 0.85 / DET_I_MINUS_A],
])

SHOCK = np.array([50.0, 0.0])

# delta_x_total = B @ shock
EXPECTED_DELTA_X_TOTAL = np.array([
    0.95 * 50.0 / DET_I_MINUS_A,   # 62.706270627...
    0.20 * 50.0 / DET_I_MINUS_A,   # 13.201320132...
])

EXPECTED_DELTA_X_DIRECT = np.array([50.0, 0.0])
EXPECTED_DELTA_X_INDIRECT = EXPECTED_DELTA_X_TOTAL - EXPECTED_DELTA_X_DIRECT
EXPECTED_TOTAL_OUTPUT = float(np.sum(EXPECTED_DELTA_X_TOTAL))  # 75.907590759...


@pytest.fixture
def loaded_model() -> LoadedModel:
    """Create a LoadedModel from the golden-run data."""
    store = ModelStore()
    mv = store.register(
        Z=Z,
        x=X,
        sector_codes=SECTOR_CODES,
        base_year=2023,
        source="golden-run",
    )
    return store.get(mv.model_version_id)


@pytest.fixture
def solver() -> LeontiefSolver:
    """Create a LeontiefSolver instance."""
    return LeontiefSolver()


class TestGoldenRun:
    """Permanent regression test against hand-verified expected values.

    NEVER remove this test. If it fails, investigate immediately.
    """

    def test_a_matrix_coefficients(self, loaded_model: LoadedModel) -> None:
        """A = Z · diag(x)^{-1} matches hand-verified expected values."""
        np.testing.assert_allclose(
            loaded_model.A,
            EXPECTED_A,
            atol=1e-10,
            err_msg="A matrix does not match hand-verified coefficients",
        )

    def test_leontief_inverse(self, loaded_model: LoadedModel) -> None:
        """B = (I - A)^{-1} matches hand-verified expected values."""
        np.testing.assert_allclose(
            loaded_model.B,
            EXPECTED_B,
            atol=1e-6,
            err_msg="Leontief inverse B does not match hand-verified values",
        )

    def test_type1_shock_propagation(
        self,
        loaded_model: LoadedModel,
        solver: LeontiefSolver,
    ) -> None:
        """delta_x per sector matches hand-verified values (atol=1e-4)."""
        result = solver.solve(loaded_model=loaded_model, delta_d=SHOCK)

        np.testing.assert_allclose(
            result.delta_x_total,
            EXPECTED_DELTA_X_TOTAL,
            atol=1e-4,
            err_msg="delta_x_total does not match hand-verified values",
        )

    def test_total_output_matches_sum(
        self,
        loaded_model: LoadedModel,
        solver: LeontiefSolver,
    ) -> None:
        """sum(delta_x_total) matches hand-verified sum."""
        result = solver.solve(loaded_model=loaded_model, delta_d=SHOCK)
        total = float(np.sum(result.delta_x_total))

        assert abs(total - EXPECTED_TOTAL_OUTPUT) < 1e-4, (
            f"Total output {total} != expected {EXPECTED_TOTAL_OUTPUT}"
        )

    def test_direct_indirect_decomposition(
        self,
        loaded_model: LoadedModel,
        solver: LeontiefSolver,
    ) -> None:
        """direct + indirect = total (exact algebraic identity)."""
        result = solver.solve(loaded_model=loaded_model, delta_d=SHOCK)

        # Verify decomposition identity
        np.testing.assert_allclose(
            result.delta_x_direct + result.delta_x_indirect,
            result.delta_x_total,
            atol=1e-10,
            err_msg="direct + indirect does not equal total",
        )

        # Verify direct = shock
        np.testing.assert_allclose(
            result.delta_x_direct,
            EXPECTED_DELTA_X_DIRECT,
            atol=1e-10,
            err_msg="direct effect does not equal shock vector",
        )

        # Verify indirect matches expected
        np.testing.assert_allclose(
            result.delta_x_indirect,
            EXPECTED_DELTA_X_INDIRECT,
            atol=1e-4,
            err_msg="indirect effect does not match hand-verified values",
        )
