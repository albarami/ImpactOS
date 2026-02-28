"""Tests for ConstrainedRunner — integration with Leontief + Satellite."""

from uuid import uuid4

import numpy as np
import pytest

from src.engine.constraints.constrained_runner import ConstrainedRunner
from src.engine.constraints.schema import (
    Constraint,
    ConstraintScope,
    ConstraintSet,
    ConstraintType,
    ConstraintUnit,
)
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteCoefficients
from src.models.common import ConstraintConfidence


class TestConstrainedRunnerIntegration:
    """Full pipeline: delta_d → Leontief → unconstrained → feasibility → feasible."""

    def _make_model_and_coefficients(self):
        store = ModelStore()
        Z = np.array([[10.0, 20.0], [5.0, 40.0]])
        x = np.array([100.0, 200.0])
        mv = store.register(
            Z=Z, x=x,
            sector_codes=["A", "F"],
            base_year=2024,
            source="test",
        )
        loaded = store.get(mv.model_version_id)
        coefficients = SatelliteCoefficients(
            jobs_coeff=np.array([0.5, 1.0]),
            import_ratio=np.array([0.2, 0.3]),
            va_ratio=np.array([0.6, 0.4]),
            version_id=uuid4(),
        )
        return loaded, coefficients

    def test_full_pipeline_no_constraints(self) -> None:
        loaded, coefficients = self._make_model_and_coefficients()
        runner = ConstrainedRunner()
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=loaded.model_version.model_version_id,
            name="empty",
            constraints=[],
        )
        delta_d = np.array([10.0, 0.0])

        result = runner.run(
            loaded_model=loaded,
            delta_d=delta_d,
            satellite_coefficients=coefficients,
            constraint_set=cs,
        )

        # Unconstrained == feasible when no constraints
        np.testing.assert_array_almost_equal(
            result.feasible_delta_x, result.unconstrained_delta_x,
        )

    def test_unconstrained_preserved(self) -> None:
        """Unconstrained result preserved, not overwritten."""
        loaded, coefficients = self._make_model_and_coefficients()
        runner = ConstrainedRunner()
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Tight cap",
            upper_bound=201.0,  # Very tight: base=200, max delta=1
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=loaded.model_version.model_version_id,
            name="tight",
            constraints=[cap],
        )
        delta_d = np.array([10.0, 20.0])

        result = runner.run(
            loaded_model=loaded,
            delta_d=delta_d,
            satellite_coefficients=coefficients,
            constraint_set=cs,
        )

        # Unconstrained should be the raw Leontief result
        assert float(np.sum(result.unconstrained_delta_x)) > 0
        # Feasible should be clipped
        assert result.feasible_delta_x[1] <= 1.0 + 1e-10
        # They should be different
        assert not np.allclose(
            result.feasible_delta_x, result.unconstrained_delta_x,
        )

    def test_both_satellite_results_computed(self) -> None:
        loaded, coefficients = self._make_model_and_coefficients()
        runner = ConstrainedRunner()
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="F cap",
            upper_bound=210.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=loaded.model_version.model_version_id,
            name="test",
            constraints=[cap],
        )
        delta_d = np.array([10.0, 20.0])

        result = runner.run(
            loaded_model=loaded,
            delta_d=delta_d,
            satellite_coefficients=coefficients,
            constraint_set=cs,
        )

        # Both satellite results should exist
        assert result.unconstrained_satellite is not None
        assert result.feasible_satellite is not None
        assert result.unconstrained_satellite.coefficients_version_id == coefficients.version_id
        assert result.feasible_satellite.coefficients_version_id == coefficients.version_id

    def test_total_output_gap_is_sum(self) -> None:
        loaded, coefficients = self._make_model_and_coefficients()
        runner = ConstrainedRunner()
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="F cap",
            upper_bound=205.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=loaded.model_version.model_version_id,
            name="test",
            constraints=[cap],
        )
        delta_d = np.array([10.0, 20.0])

        result = runner.run(
            loaded_model=loaded,
            delta_d=delta_d,
            satellite_coefficients=coefficients,
            constraint_set=cs,
        )

        # total_output_gap == sum of positive sector gaps
        gap_vec = result.unconstrained_delta_x - result.feasible_delta_x
        expected_gap = float(np.sum(np.maximum(gap_vec, 0)))
        assert result.total_output_gap == pytest.approx(expected_gap)
