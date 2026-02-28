"""Integration Path 1: Core Engine — Leontief -> Satellite -> Constraints.

Tests module boundaries between:
- ModelStore.register/get -> LoadedModel
- LeontiefSolver.solve(loaded_model, delta_d) -> SolveResult
- SatelliteAccounts.compute(delta_x, coefficients) -> SatelliteResult
- FeasibilitySolver.solve(unconstrained, constraints) -> FeasibilityResult

Uses the 3-sector toy IO model (ISIC F/C/G) from shared.py for basic path tests.
"""

import numpy as np
import pytest
from numpy.testing import assert_allclose
from uuid_extensions import uuid7

from src.engine.constraints.schema import (
    Constraint,
    ConstraintBoundScope,
    ConstraintScope,
    ConstraintSet,
    ConstraintType,
    ConstraintUnit,
)
from src.engine.constraints.solver import FeasibilitySolver
from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.models.common import ConstraintConfidence, new_uuid7

from tests.integration.golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    NUMERIC_RTOL,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
)


@pytest.fixture
def model_store():
    return ModelStore()


@pytest.fixture
def loaded_model(model_store):
    mv = model_store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR, source="test-engine-path",
    )
    return model_store.get(mv.model_version_id)


@pytest.fixture
def sat_coefficients():
    return SatelliteCoefficients(
        jobs_coeff=SMALL_JOBS_COEFF.copy(),
        import_ratio=SMALL_IMPORT_RATIO.copy(),
        va_ratio=SMALL_VA_RATIO.copy(),
        version_id=uuid7(),
    )


@pytest.mark.integration
class TestLeontiefToSatellite:
    """Leontief output feeds satellite accounts correctly."""

    def test_solve_produces_valid_delta_x(self, loaded_model):
        """delta_x = B . delta_d has correct shape and positive values."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        assert result.delta_x_total.shape == (3,)
        # Total = direct + indirect
        assert_allclose(
            result.delta_x_total,
            result.delta_x_direct + result.delta_x_indirect,
            rtol=NUMERIC_RTOL,
        )
        # Positive shock -> positive output
        assert np.all(result.delta_x_total > 0)

    def test_satellite_employment_from_delta_x(self, loaded_model, sat_coefficients):
        """Satellite employment = jobs_coeff * delta_x."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        solve_result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        sa = SatelliteAccounts()
        sat_result = sa.compute(
            delta_x=solve_result.delta_x_total,
            coefficients=sat_coefficients,
        )

        # Employment = jobs_coeff * delta_x (element-wise)
        expected_jobs = sat_coefficients.jobs_coeff * solve_result.delta_x_total
        assert_allclose(sat_result.delta_jobs, expected_jobs, rtol=NUMERIC_RTOL)

    def test_satellite_gdp_from_delta_x(self, loaded_model, sat_coefficients):
        """Satellite GDP = va_ratio * delta_x."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        solve_result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        sa = SatelliteAccounts()
        sat_result = sa.compute(
            delta_x=solve_result.delta_x_total,
            coefficients=sat_coefficients,
        )

        expected_va = sat_coefficients.va_ratio * solve_result.delta_x_total
        assert_allclose(sat_result.delta_va, expected_va, rtol=NUMERIC_RTOL)


@pytest.mark.integration
class TestUnconstrainedVsFeasible:
    """Constrained results vs unconstrained."""

    def test_feasibility_clips_not_creates(self, loaded_model, sat_coefficients):
        """Feasible delta_x <= unconstrained delta_x per sector."""
        solver = LeontiefSolver()
        delta_d = np.array([300.0, 150.0, 50.0])
        solve_result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        # Tight constraint on Construction (F): cap absolute total at 200
        # ConstraintScope requires scope_type="sector" with scope_values=["F"]
        # Constraint uses upper_bound (not bound_value)
        # ConstraintSet requires model_version_id and name
        constraints = ConstraintSet(
            constraint_set_id=new_uuid7(),
            constraints=[
                Constraint(
                    constraint_id=new_uuid7(),
                    constraint_type=ConstraintType.CAPACITY_CAP,
                    scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
                    upper_bound=200.0,
                    bound_scope=ConstraintBoundScope.DELTA_ONLY,
                    unit=ConstraintUnit.SAR_MILLIONS,
                    confidence=ConstraintConfidence.HARD,
                    description="Construction capacity cap",
                ),
            ],
            workspace_id=uuid7(),
            model_version_id=loaded_model.model_version.model_version_id,
            name="test-constraint-set",
        )

        fsolver = FeasibilitySolver()
        feas_result = fsolver.solve(
            unconstrained_delta_x=solve_result.delta_x_total,
            base_x=loaded_model.x,
            satellite_coefficients=sat_coefficients,
            constraint_set=constraints,
            sector_codes=SECTOR_CODES_SMALL,
        )

        # Feasible <= unconstrained for every sector
        assert np.all(
            feas_result.feasible_delta_x <= solve_result.delta_x_total + 1e-10
        )

    def test_binding_constraint_diagnostics(self, loaded_model, sat_coefficients):
        """Binding constraints report which constraint, gap, and description."""
        solver = LeontiefSolver()
        delta_d = np.array([300.0, 150.0, 50.0])
        solve_result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        constraints = ConstraintSet(
            constraint_set_id=new_uuid7(),
            constraints=[
                Constraint(
                    constraint_id=new_uuid7(),
                    constraint_type=ConstraintType.CAPACITY_CAP,
                    scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
                    upper_bound=200.0,
                    bound_scope=ConstraintBoundScope.DELTA_ONLY,
                    unit=ConstraintUnit.SAR_MILLIONS,
                    confidence=ConstraintConfidence.HARD,
                    description="Construction capacity cap",
                ),
            ],
            workspace_id=uuid7(),
            model_version_id=loaded_model.model_version.model_version_id,
            name="test-constraint-set",
        )

        fsolver = FeasibilitySolver()
        feas_result = fsolver.solve(
            unconstrained_delta_x=solve_result.delta_x_total,
            base_x=loaded_model.x,
            satellite_coefficients=sat_coefficients,
            constraint_set=constraints,
            sector_codes=SECTOR_CODES_SMALL,
        )

        # Should have at least one binding constraint
        assert len(feas_result.binding_constraints) >= 1
        bc = feas_result.binding_constraints[0]
        assert bc.gap > 0  # Gap is positive (clipped)
        assert bc.description != ""


@pytest.mark.integration
class TestDeterministicReproducibility:
    """Same inputs produce identical outputs."""

    def test_three_consecutive_runs_identical(self, loaded_model, sat_coefficients):
        """3 runs with same inputs -> bit-for-bit identical."""
        solver = LeontiefSolver()
        sa = SatelliteAccounts()
        delta_d = np.array([100.0, 50.0, 25.0])

        results = []
        for _ in range(3):
            solve_result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)
            sat_result = sa.compute(
                delta_x=solve_result.delta_x_total,
                coefficients=sat_coefficients,
            )
            results.append((solve_result.delta_x_total.copy(), sat_result.delta_jobs.copy()))

        for i in range(1, 3):
            assert_allclose(results[0][0], results[i][0], rtol=0)
            assert_allclose(results[0][1], results[i][1], rtol=0)
