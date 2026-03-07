"""Tests proving feasibility ResultSets are always emitted on main run path (P5-3).

TDD: These tests MUST fail before implementation, then pass after.
The core gap: feasible_output and constraint_gap only emitted when
constraints explicitly provided. They should ALWAYS be present.
"""

import pytest
import numpy as np

from src.engine.batch import BatchRunner, BatchRequest, ScenarioInput
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteCoefficients
from src.models.common import new_uuid7


def _register_3sector_model(store: ModelStore):
    """Register a real 3-sector model (A, F, I) in the store."""
    Z = np.array([
        [100.0, 50.0, 30.0],
        [80.0,  120.0, 60.0],
        [40.0,  70.0,  90.0],
    ])
    x = np.array([1e9, 2e9, 1.5e9])
    mv = store.register(
        Z=Z, x=x,
        sector_codes=["A", "F", "I"],
        base_year=2023,
        source="test_feasibility_on_main_path",
        model_denomination="SAR_MILLIONS",
    )
    return mv


def _make_coefficients() -> SatelliteCoefficients:
    return SatelliteCoefficients(
        jobs_coeff=np.array([0.001, 0.002, 0.003]),
        import_ratio=np.array([0.18, 0.15, 0.25]),
        va_ratio=np.array([0.50, 0.45, 0.55]),
        version_id=new_uuid7(),
    )


def _make_version_refs() -> dict:
    return {
        "taxonomy_version_id": new_uuid7(),
        "concordance_version_id": new_uuid7(),
        "mapping_library_version_id": new_uuid7(),
        "assumption_library_version_id": new_uuid7(),
        "prompt_pack_version_id": new_uuid7(),
    }


class TestFeasibilityAlwaysPresent:
    """P5-3: feasible_output and constraint_gap must always be emitted."""

    def test_feasible_output_emitted_without_constraints(self):
        """feasible_output must be present even when no constraints provided."""
        store = ModelStore()
        mv = _register_3sector_model(store)

        request = BatchRequest(
            scenarios=[
                ScenarioInput(
                    scenario_spec_id=new_uuid7(),
                    scenario_spec_version=1,
                    name="Test: No constraints",
                    annual_shocks={2023: np.array([0.0, 1_000_000_000.0, 0.0])},
                    base_year=2023,
                ),
            ],
            model_version_id=mv.model_version_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
            constraints=None,  # No constraints
        )

        runner = BatchRunner(model_store=store)
        result = runner.run(request)

        metric_types = {
            rs.metric_type for rs in result.run_results[0].result_sets
        }
        assert "feasible_output" in metric_types, \
            f"feasible_output missing without constraints. Got: {sorted(metric_types)}"
        assert "constraint_gap" in metric_types, \
            f"constraint_gap missing without constraints. Got: {sorted(metric_types)}"

    def test_unconstrained_feasible_equals_total_output(self):
        """When no constraints, feasible_output must equal total_output."""
        store = ModelStore()
        mv = _register_3sector_model(store)

        request = BatchRequest(
            scenarios=[
                ScenarioInput(
                    scenario_spec_id=new_uuid7(),
                    scenario_spec_version=1,
                    name="Test: Equality check",
                    annual_shocks={2023: np.array([500_000_000.0, 1_000_000_000.0, 300_000_000.0])},
                    base_year=2023,
                ),
            ],
            model_version_id=mv.model_version_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
            constraints=None,
        )

        runner = BatchRunner(model_store=store)
        result = runner.run(request)

        rsets: dict[str, dict] = {}
        for rs in result.run_results[0].result_sets:
            if rs.series_kind is None and rs.metric_type not in rsets:
                rsets[rs.metric_type] = rs.values

        # Feasible output should equal total output (no constraints = no gap)
        for code in ["A", "F", "I"]:
            assert rsets["feasible_output"][code] == pytest.approx(
                rsets["total_output"][code], rel=1e-6,
            ), f"feasible_output[{code}] != total_output[{code}]"

    def test_unconstrained_gap_is_zero(self):
        """When no constraints, constraint_gap must be zero for all sectors."""
        store = ModelStore()
        mv = _register_3sector_model(store)

        request = BatchRequest(
            scenarios=[
                ScenarioInput(
                    scenario_spec_id=new_uuid7(),
                    scenario_spec_version=1,
                    name="Test: Zero gap",
                    annual_shocks={2023: np.array([0.0, 1_000_000_000.0, 0.0])},
                    base_year=2023,
                ),
            ],
            model_version_id=mv.model_version_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
            constraints=None,
        )

        runner = BatchRunner(model_store=store)
        result = runner.run(request)

        rsets: dict[str, dict] = {}
        for rs in result.run_results[0].result_sets:
            if rs.metric_type not in rsets:
                rsets[rs.metric_type] = rs.values

        for code in ["A", "F", "I"]:
            assert rsets["constraint_gap"][code] == pytest.approx(0.0, abs=1e-6), \
                f"constraint_gap[{code}] should be zero without constraints"

    def test_constrained_feasible_differs_from_total(self):
        """When constraints are binding, feasible_output should differ from total_output."""
        from src.engine.feasibility import ConstraintSpec

        store = ModelStore()
        mv = _register_3sector_model(store)

        # Cap sector F at a very small value to ensure constraint binds
        constraints = [
            ConstraintSpec(
                constraint_id=new_uuid7(),
                constraint_type="CAPACITY_CAP",
                sector_index=1,  # F
                bound_value=100.0,  # Very tight cap
                confidence="HIGH",
            ),
        ]

        request = BatchRequest(
            scenarios=[
                ScenarioInput(
                    scenario_spec_id=new_uuid7(),
                    scenario_spec_version=1,
                    name="Test: Binding constraint",
                    annual_shocks={2023: np.array([0.0, 1_000_000_000.0, 0.0])},
                    base_year=2023,
                ),
            ],
            model_version_id=mv.model_version_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
            constraints=constraints,
        )

        runner = BatchRunner(model_store=store)
        result = runner.run(request)

        rsets: dict[str, dict] = {}
        for rs in result.run_results[0].result_sets:
            if rs.series_kind is None and rs.metric_type not in rsets:
                rsets[rs.metric_type] = rs.values

        # With binding constraint, feasible_output[F] should be capped
        assert rsets["feasible_output"]["F"] <= 100.0 + 1e-6, \
            f"feasible_output[F] should be capped at 100.0"
        assert rsets["constraint_gap"]["F"] > 0, \
            "constraint_gap[F] should be positive when constraint binds"
