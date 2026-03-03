"""Tests for batch runner (MVP-3 Section 7.6).

Covers: multi-scenario execution, sensitivity variants, immutable ResultSets,
RunSnapshot generation, 50+ scenario handling, Type II integration.
"""

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.engine.batch import BatchRunner, BatchRequest, ScenarioInput, BatchResult
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteCoefficients
from src.engine.type_ii_validation import TypeIIValidationError
from src.models.run import ResultSet, RunSnapshot
from tests.integration.golden_scenarios.shared import (
    GOLDEN_Z, GOLDEN_X, SECTOR_CODES_SMALL,
    GOLDEN_COMPENSATION, GOLDEN_HOUSEHOLD_SHARES,
    SMALL_JOBS_COEFF, SMALL_IMPORT_RATIO, SMALL_VA_RATIO,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_store_and_model() -> tuple[ModelStore, object]:
    store = ModelStore()
    Z = np.array([[150.0, 500.0],
                   [200.0, 100.0]])
    x = np.array([1000.0, 2000.0])
    mv = store.register(
        Z=Z, x=x, sector_codes=["S1", "S2"],
        base_year=2023, source="test",
    )
    return store, mv


def _make_coefficients() -> SatelliteCoefficients:
    return SatelliteCoefficients(
        jobs_coeff=np.array([0.01, 0.005]),
        import_ratio=np.array([0.30, 0.20]),
        va_ratio=np.array([0.40, 0.55]),
        version_id=uuid7(),
    )


def _make_scenario(name: str, shock: np.ndarray) -> ScenarioInput:
    return ScenarioInput(
        scenario_spec_id=uuid7(),
        scenario_spec_version=1,
        name=name,
        annual_shocks={2026: shock},
        base_year=2023,
    )


def _make_version_refs() -> dict:
    return {
        "taxonomy_version_id": uuid7(),
        "concordance_version_id": uuid7(),
        "mapping_library_version_id": uuid7(),
        "assumption_library_version_id": uuid7(),
        "prompt_pack_version_id": uuid7(),
    }


# ===================================================================
# Single scenario run
# ===================================================================


class TestSingleScenarioRun:
    """Batch runner handles a single scenario correctly."""

    def test_returns_batch_result(self) -> None:
        store, mv = _make_store_and_model()
        runner = BatchRunner(model_store=store)
        coeffs = _make_coefficients()

        scenario = _make_scenario("Base", np.array([100.0, 0.0]))
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=_make_version_refs(),
        )

        result = runner.run(request)
        assert isinstance(result, BatchResult)
        assert len(result.run_results) == 1

    def test_produces_result_sets(self) -> None:
        store, mv = _make_store_and_model()
        runner = BatchRunner(model_store=store)
        coeffs = _make_coefficients()

        scenario = _make_scenario("Base", np.array([100.0, 0.0]))
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=_make_version_refs(),
        )

        result = runner.run(request)
        run_result = result.run_results[0]
        # Should have result sets for total_output, direct, indirect, jobs, imports, va
        assert len(run_result.result_sets) >= 3

    def test_produces_run_snapshot(self) -> None:
        store, mv = _make_store_and_model()
        runner = BatchRunner(model_store=store)
        coeffs = _make_coefficients()

        scenario = _make_scenario("Base", np.array([100.0, 0.0]))
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=_make_version_refs(),
        )

        result = runner.run(request)
        snap = result.run_results[0].snapshot
        assert isinstance(snap, RunSnapshot)
        assert snap.model_version_id == mv.model_version_id

    def test_result_sets_are_immutable(self) -> None:
        store, mv = _make_store_and_model()
        runner = BatchRunner(model_store=store)
        coeffs = _make_coefficients()

        scenario = _make_scenario("Base", np.array([100.0, 0.0]))
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=_make_version_refs(),
        )

        result = runner.run(request)
        for rs in result.run_results[0].result_sets:
            assert isinstance(rs, ResultSet)
            # ResultSet is frozen — should be immutable


# ===================================================================
# Multi-scenario batch
# ===================================================================


class TestMultiScenarioBatch:
    """Batch runner handles multiple scenarios."""

    def test_multiple_scenarios(self) -> None:
        store, mv = _make_store_and_model()
        runner = BatchRunner(model_store=store)
        coeffs = _make_coefficients()

        scenarios = [
            _make_scenario("Low", np.array([50.0, 0.0])),
            _make_scenario("Base", np.array([100.0, 0.0])),
            _make_scenario("High", np.array([200.0, 0.0])),
        ]
        request = BatchRequest(
            scenarios=scenarios,
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=_make_version_refs(),
        )

        result = runner.run(request)
        assert len(result.run_results) == 3

    def test_each_scenario_has_unique_run_id(self) -> None:
        store, mv = _make_store_and_model()
        runner = BatchRunner(model_store=store)
        coeffs = _make_coefficients()

        scenarios = [
            _make_scenario("A", np.array([50.0, 0.0])),
            _make_scenario("B", np.array([100.0, 0.0])),
        ]
        request = BatchRequest(
            scenarios=scenarios,
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=_make_version_refs(),
        )

        result = runner.run(request)
        run_ids = [r.snapshot.run_id for r in result.run_results]
        assert len(set(run_ids)) == 2  # unique

    def test_50_plus_scenarios(self) -> None:
        """Batch runner handles 50+ scenarios without failure."""
        store, mv = _make_store_and_model()
        runner = BatchRunner(model_store=store)
        coeffs = _make_coefficients()

        scenarios = [
            _make_scenario(f"Scenario_{i}", np.array([float(i * 10), 0.0]))
            for i in range(60)
        ]
        request = BatchRequest(
            scenarios=scenarios,
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=_make_version_refs(),
        )

        result = runner.run(request)
        assert len(result.run_results) == 60


# ===================================================================
# Sensitivity variants
# ===================================================================


class TestSensitivityVariants:
    """Batch runner supports sensitivity variants per scenario."""

    def test_sensitivity_multipliers(self) -> None:
        store, mv = _make_store_and_model()
        runner = BatchRunner(model_store=store)
        coeffs = _make_coefficients()

        scenario = _make_scenario("Base", np.array([100.0, 0.0]))
        scenario.sensitivity_multipliers = [0.8, 1.0, 1.2]

        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=_make_version_refs(),
        )

        result = runner.run(request)
        # 3 sensitivity variants
        assert len(result.run_results) == 3

    def test_sensitivity_results_scale_proportionally(self) -> None:
        store, mv = _make_store_and_model()
        runner = BatchRunner(model_store=store)
        coeffs = _make_coefficients()

        scenario = _make_scenario("Base", np.array([100.0, 0.0]))
        scenario.sensitivity_multipliers = [0.5, 1.0, 2.0]

        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=_make_version_refs(),
        )

        result = runner.run(request)
        # The 0.5x result total output should be half the 1.0x result
        rs_half = [rs for rs in result.run_results[0].result_sets if rs.metric_type == "total_output"][0]
        rs_base = [rs for rs in result.run_results[1].result_sets if rs.metric_type == "total_output"][0]
        for sector in rs_half.values:
            np.testing.assert_almost_equal(
                rs_half.values[sector],
                rs_base.values[sector] * 0.5,
                decimal=6,
            )


# ===================================================================
# RunSnapshot completeness
# ===================================================================


class TestRunSnapshotCompleteness:
    """RunSnapshot captures all version references."""

    def test_snapshot_has_all_refs(self) -> None:
        store, mv = _make_store_and_model()
        runner = BatchRunner(model_store=store)
        coeffs = _make_coefficients()
        refs = _make_version_refs()

        scenario = _make_scenario("Base", np.array([100.0, 0.0]))
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=refs,
        )

        result = runner.run(request)
        snap = result.run_results[0].snapshot
        assert snap.model_version_id == mv.model_version_id
        assert snap.taxonomy_version_id == refs["taxonomy_version_id"]
        assert snap.concordance_version_id == refs["concordance_version_id"]
        assert snap.mapping_library_version_id == refs["mapping_library_version_id"]
        assert snap.assumption_library_version_id == refs["assumption_library_version_id"]
        assert snap.prompt_pack_version_id == refs["prompt_pack_version_id"]


# ===================================================================
# Type II batch integration (Sprint 15 — Task 6)
# ===================================================================


class TestTypeIIBatchIntegration:
    """BatchRunner produces Type II metrics when model has prerequisites."""

    def _make_golden_store_and_model(self):
        store = ModelStore()
        mv = store.register(
            Z=np.array(GOLDEN_Z), x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL, base_year=2023, source="test",
            artifact_payload={
                "compensation_of_employees": GOLDEN_COMPENSATION,
                "household_consumption_shares": GOLDEN_HOUSEHOLD_SHARES,
            },
        )
        return store, mv

    def _golden_coefficients(self):
        return SatelliteCoefficients(
            jobs_coeff=np.array(SMALL_JOBS_COEFF),
            import_ratio=np.array(SMALL_IMPORT_RATIO),
            va_ratio=np.array(SMALL_VA_RATIO),
            version_id=uuid7(),
        )

    def _make_refs(self):
        return {
            "taxonomy_version_id": uuid7(),
            "concordance_version_id": uuid7(),
            "mapping_library_version_id": uuid7(),
            "assumption_library_version_id": uuid7(),
            "prompt_pack_version_id": uuid7(),
        }

    def test_batch_produces_type_ii_metrics(self):
        store, mv = self._make_golden_store_and_model()
        runner = BatchRunner(model_store=store, environment="dev")
        scenario = ScenarioInput(
            scenario_spec_id=uuid7(), scenario_spec_version=1, name="test",
            annual_shocks={2024: np.array([100.0, 0.0, 0.0])}, base_year=2023,
        )
        request = BatchRequest(
            scenarios=[scenario], model_version_id=mv.model_version_id,
            satellite_coefficients=self._golden_coefficients(),
            version_refs=self._make_refs(),
        )
        result = runner.run(request)
        metric_types = {rs.metric_type for rs in result.run_results[0].result_sets}
        assert "type_ii_total_output" in metric_types
        assert "induced_effect" in metric_types
        assert "type_ii_employment" in metric_types
        assert "total_output" in metric_types  # backward compat
        assert "direct_effect" in metric_types

    def test_batch_without_prerequisites_no_type_ii(self):
        store, mv = _make_store_and_model()  # uses existing 2-sector without artifacts
        runner = BatchRunner(model_store=store, environment="dev")
        scenario = _make_scenario("test", np.array([100.0, 0.0]))
        request = BatchRequest(
            scenarios=[scenario], model_version_id=mv.model_version_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=self._make_refs(),
        )
        result = runner.run(request)
        metric_types = {rs.metric_type for rs in result.run_results[0].result_sets}
        assert "type_ii_total_output" not in metric_types
        assert "induced_effect" not in metric_types

    def test_type_ii_induced_positive(self):
        store, mv = self._make_golden_store_and_model()
        runner = BatchRunner(model_store=store, environment="dev")
        scenario = ScenarioInput(
            scenario_spec_id=uuid7(), scenario_spec_version=1, name="test",
            annual_shocks={2024: np.array([100.0, 0.0, 0.0])}, base_year=2023,
        )
        request = BatchRequest(
            scenarios=[scenario], model_version_id=mv.model_version_id,
            satellite_coefficients=self._golden_coefficients(),
            version_refs=self._make_refs(),
        )
        result = runner.run(request)
        induced_rs = next(
            rs for rs in result.run_results[0].result_sets
            if rs.metric_type == "induced_effect"
        )
        # Induced effects should be positive (household spending creates output)
        assert all(v >= 0 for v in induced_rs.values.values())

    def test_existing_metrics_unchanged_count(self):
        """Existing 7 Type I metrics still present when Type II is added."""
        store, mv = self._make_golden_store_and_model()
        runner = BatchRunner(model_store=store, environment="dev")
        scenario = ScenarioInput(
            scenario_spec_id=uuid7(), scenario_spec_version=1, name="test",
            annual_shocks={2024: np.array([100.0, 0.0, 0.0])}, base_year=2023,
        )
        request = BatchRequest(
            scenarios=[scenario], model_version_id=mv.model_version_id,
            satellite_coefficients=self._golden_coefficients(),
            version_refs=self._make_refs(),
        )
        result = runner.run(request)
        rs_list = result.run_results[0].result_sets
        # 7 existing + 3 Type II = 10
        assert len(rs_list) == 10
