"""Tests proving workforce/saudization ResultSets are emitted on main run path (P5-2).

TDD: These tests MUST fail before implementation, then pass after.
The core gap: BatchRunner computes employment but does NOT emit
saudization_saudi_ready, saudization_saudi_trainable, or
saudization_expat_reliant ResultSets.
"""

import pytest
import numpy as np
from unittest.mock import patch

from src.engine.batch import BatchRunner, BatchRequest, ScenarioInput
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteCoefficients
from src.models.common import new_uuid7


def _register_3sector_model(store: ModelStore):
    """Register a real 3-sector model (A, F, I) in the store."""
    # Simple Z matrix (inter-industry flows)
    Z = np.array([
        [100.0, 50.0, 30.0],
        [80.0,  120.0, 60.0],
        [40.0,  70.0,  90.0],
    ])
    # Output vector
    x = np.array([1e9, 2e9, 1.5e9])

    mv = store.register(
        Z=Z,
        x=x,
        sector_codes=["A", "F", "I"],
        base_year=2023,
        source="test_workforce_on_main_path",
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


class TestWorkforceOnMainPath:
    """P5-2: Workforce/saudization ResultSets must be emitted on main run path."""

    def test_saudization_result_sets_emitted(self):
        """BatchRunner must emit saudization_* ResultSets when workforce data available."""
        store = ModelStore()
        mv = _register_3sector_model(store)

        request = BatchRequest(
            scenarios=[
                ScenarioInput(
                    scenario_spec_id=new_uuid7(),
                    scenario_spec_version=1,
                    name="Test: Construction shock",
                    annual_shocks={2023: np.array([0.0, 1_000_000_000.0, 0.0])},
                    base_year=2023,
                ),
            ],
            model_version_id=mv.model_version_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
        )

        runner = BatchRunner(model_store=store)
        result = runner.run(request)

        assert len(result.run_results) == 1
        metric_types = {
            rs.metric_type for rs in result.run_results[0].result_sets
        }

        # These must be present from workforce satellite
        assert "saudization_saudi_ready" in metric_types, \
            f"saudization_saudi_ready missing. Got: {sorted(metric_types)}"
        assert "saudization_saudi_trainable" in metric_types, \
            f"saudization_saudi_trainable missing. Got: {sorted(metric_types)}"
        assert "saudization_expat_reliant" in metric_types, \
            f"saudization_expat_reliant missing. Got: {sorted(metric_types)}"

    def test_saudization_values_sum_to_employment(self):
        """Saudi-ready + trainable + expat-reliant should equal total employment."""
        store = ModelStore()
        mv = _register_3sector_model(store)

        request = BatchRequest(
            scenarios=[
                ScenarioInput(
                    scenario_spec_id=new_uuid7(),
                    scenario_spec_version=1,
                    name="Test: Mixed shock",
                    annual_shocks={2023: np.array([500_000_000.0, 1_000_000_000.0, 300_000_000.0])},
                    base_year=2023,
                ),
            ],
            model_version_id=mv.model_version_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
        )

        runner = BatchRunner(model_store=store)
        result = runner.run(request)

        rsets: dict[str, dict] = {}
        for rs in result.run_results[0].result_sets:
            if rs.metric_type not in rsets:  # Take first of each metric_type
                rsets[rs.metric_type] = rs.values

        employment_total = sum(rsets["employment"].values())
        saudi_ready_total = sum(rsets["saudization_saudi_ready"].values())
        saudi_trainable_total = sum(rsets["saudization_saudi_trainable"].values())
        expat_reliant_total = sum(rsets["saudization_expat_reliant"].values())

        saud_sum = saudi_ready_total + saudi_trainable_total + expat_reliant_total
        assert saud_sum == pytest.approx(employment_total, rel=0.01), \
            f"Saudization sum {saud_sum} != employment {employment_total}"

    def test_basic_employment_still_emitted(self):
        """Wiring workforce must not break existing employment ResultSet."""
        store = ModelStore()
        mv = _register_3sector_model(store)

        request = BatchRequest(
            scenarios=[
                ScenarioInput(
                    scenario_spec_id=new_uuid7(),
                    scenario_spec_version=1,
                    name="Test: Basic check",
                    annual_shocks={2023: np.array([0.0, 1_000_000_000.0, 0.0])},
                    base_year=2023,
                ),
            ],
            model_version_id=mv.model_version_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
        )

        runner = BatchRunner(model_store=store)
        result = runner.run(request)

        metric_types = {
            rs.metric_type for rs in result.run_results[0].result_sets
        }
        # Basic satellite results must still be present
        assert "employment" in metric_types
        assert "imports" in metric_types
        assert "value_added" in metric_types
        assert "domestic_output" in metric_types

    def test_workforce_degradation_without_d4_data(self):
        """If D-4 data loading fails, basic employment still emitted (no crash)."""
        store = ModelStore()
        mv = _register_3sector_model(store)

        request = BatchRequest(
            scenarios=[
                ScenarioInput(
                    scenario_spec_id=new_uuid7(),
                    scenario_spec_version=1,
                    name="Test: Degraded",
                    annual_shocks={2023: np.array([0.0, 1_000_000_000.0, 0.0])},
                    base_year=2023,
                ),
            ],
            model_version_id=mv.model_version_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
        )

        runner = BatchRunner(model_store=store)

        # Simulate D-4 loading failure
        with patch(
            "src.engine.batch.load_workforce_data",
            side_effect=RuntimeError("No D-4 data"),
        ):
            result = runner.run(request)

        metric_types = {
            rs.metric_type for rs in result.run_results[0].result_sets
        }
        assert "employment" in metric_types  # Basic still works
        # Saudization NOT present because D-4 data failed
        assert "saudization_saudi_ready" not in metric_types

    def test_saudization_per_sector_keys_match_model(self):
        """Saudization ResultSets must use same sector codes as the model."""
        store = ModelStore()
        mv = _register_3sector_model(store)

        request = BatchRequest(
            scenarios=[
                ScenarioInput(
                    scenario_spec_id=new_uuid7(),
                    scenario_spec_version=1,
                    name="Test: Key check",
                    annual_shocks={2023: np.array([0.0, 1_000_000_000.0, 0.0])},
                    base_year=2023,
                ),
            ],
            model_version_id=mv.model_version_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
        )

        runner = BatchRunner(model_store=store)
        result = runner.run(request)

        rsets: dict[str, dict] = {}
        for rs in result.run_results[0].result_sets:
            if rs.metric_type not in rsets:
                rsets[rs.metric_type] = rs.values

        for metric in ["saudization_saudi_ready", "saudization_saudi_trainable", "saudization_expat_reliant"]:
            assert metric in rsets, f"{metric} not in result sets"
            assert set(rsets[metric].keys()) == {"A", "F", "I"}, \
                f"{metric} sector keys don't match model. Got: {set(rsets[metric].keys())}"
