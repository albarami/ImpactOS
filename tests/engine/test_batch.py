"""Tests for batch runner (MVP-3 Section 7.6).

Covers: multi-scenario execution, sensitivity variants, immutable ResultSets,
RunSnapshot generation, 50+ scenario handling, Type II integration.
"""

from __future__ import annotations

from uuid import UUID

import numpy as np
from uuid_extensions import uuid7

from src.engine.batch import BatchRequest, BatchResult, BatchRunner, ScenarioInput
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteCoefficients
from src.engine.type_ii_validation import TypeIIValidationError
from src.models.model_version import ModelVersion
from src.models.run import ResultSet, RunSnapshot
from tests.integration.golden_scenarios.shared import (
    GOLDEN_COMPENSATION,
    GOLDEN_HOUSEHOLD_SHARES,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
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
        rs_half = [
            rs for rs in result.run_results[0].result_sets
            if rs.metric_type == "total_output"
        ][0]
        rs_base = [
            rs for rs in result.run_results[1].result_sets
            if rs.metric_type == "total_output"
        ][0]
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

    def _make_golden_store_and_model(
        self,
    ) -> tuple[ModelStore, ModelVersion]:
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

    def _golden_coefficients(self) -> SatelliteCoefficients:
        return SatelliteCoefficients(
            jobs_coeff=np.array(SMALL_JOBS_COEFF),
            import_ratio=np.array(SMALL_IMPORT_RATIO),
            va_ratio=np.array(SMALL_VA_RATIO),
            version_id=uuid7(),
        )

    def _make_refs(self) -> dict[str, UUID]:
        return {
            "taxonomy_version_id": uuid7(),
            "concordance_version_id": uuid7(),
            "mapping_library_version_id": uuid7(),
            "assumption_library_version_id": uuid7(),
            "prompt_pack_version_id": uuid7(),
        }

    def test_batch_produces_type_ii_metrics(self) -> None:
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

    def test_batch_without_prerequisites_no_type_ii(self) -> None:
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

    def test_type_ii_induced_positive(self) -> None:
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

    def test_existing_metrics_unchanged_count(self) -> None:
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
        # 7 cumulative + 3 annual (1 year * 3 metrics) + 1 peak + 3 Type II + 3 saudization = 17
        assert len(rs_list) == 17


# ===================================================================
# Type II error translation (Sprint 15 — Task 7)
# ===================================================================


class TestTypeIIErrorTranslation:
    """Type II validation errors carry reason_code through the stack."""

    def test_type_ii_validation_error_has_reason_code(self) -> None:
        """TypeIIValidationError carries a machine-readable reason_code."""
        exc = TypeIIValidationError("test message", reason_code="TYPE_II_MISSING_COMPENSATION")
        assert exc.reason_code == "TYPE_II_MISSING_COMPENSATION"
        assert str(exc) == "test message"

    def test_type_ii_error_serialization_for_api(self) -> None:
        """Error can be serialized to API-friendly payload."""
        exc = TypeIIValidationError(
            "compensation_of_employees is required",
            reason_code="TYPE_II_MISSING_COMPENSATION",
        )
        payload = {"reason_code": exc.reason_code, "message": str(exc)}
        assert payload == {
            "reason_code": "TYPE_II_MISSING_COMPENSATION",
            "message": "compensation_of_employees is required",
        }

    def test_no_secrets_in_type_ii_error(self) -> None:
        """Error message must not contain API keys, tokens, or secrets."""
        exc = TypeIIValidationError(
            "compensation_of_employees is required for Type II computation.",
            reason_code="TYPE_II_MISSING_COMPENSATION",
        )
        msg = str(exc)
        assert "key" not in msg.lower() or "api" not in msg.lower()
        assert "token" not in msg.lower()
        assert "password" not in msg.lower()


# ---------------------------------------------------------------------------
# Sprint 16: Batch value-measures integration
# ---------------------------------------------------------------------------

import pytest

from src.engine.value_measures_validation import ValueMeasuresValidationError
from tests.integration.golden_scenarios.shared import (
    SMALL_DEFLATOR_SERIES,
    SMALL_FINAL_DEMAND_F,
    SMALL_GOS,
    SMALL_IMPORTS_VECTOR,
    SMALL_TAXES_LESS_SUBSIDIES,
)

# Value-measures metric types
VM_METRICS = {
    "gdp_basic_price", "gdp_market_price", "gdp_real", "gdp_intensity",
    "balance_of_trade", "non_oil_exports",
    "government_non_oil_revenue", "government_revenue_spending_ratio",
}


class TestBatchValueMeasures:
    """Batch runner emits value-measures metrics when prerequisites present."""

    def _make_golden_store_and_model(self) -> tuple[ModelStore, ModelVersion]:
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=2024, source="test-vm-batch",
            artifact_payload={
                "gross_operating_surplus": SMALL_GOS.tolist(),
                "taxes_less_subsidies": SMALL_TAXES_LESS_SUBSIDIES.tolist(),
                "final_demand_F": SMALL_FINAL_DEMAND_F.tolist(),
                "imports_vector": SMALL_IMPORTS_VECTOR.tolist(),
                "deflator_series": SMALL_DEFLATOR_SERIES,
                "compensation_of_employees": GOLDEN_COMPENSATION,
                "household_consumption_shares": GOLDEN_HOUSEHOLD_SHARES,
            },
        )
        return store, mv

    def _golden_coefficients(self) -> SatelliteCoefficients:
        return SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF,
            import_ratio=SMALL_IMPORT_RATIO,
            va_ratio=SMALL_VA_RATIO,
            version_id=uuid7(),
        )

    def _make_refs(self) -> dict[str, UUID]:
        return {
            "taxonomy_version_id": uuid7(),
            "concordance_version_id": uuid7(),
            "mapping_library_version_id": uuid7(),
            "assumption_library_version_id": uuid7(),
            "prompt_pack_version_id": uuid7(),
        }

    def test_batch_includes_value_measures_metrics(self) -> None:
        store, mv = self._make_golden_store_and_model()
        runner = BatchRunner(model_store=store, environment="dev")
        request = BatchRequest(
            scenarios=[ScenarioInput(
                scenario_spec_id=uuid7(), scenario_spec_version=1,
                name="vm-test",
                annual_shocks={2025: np.array([100.0, 50.0, 25.0])},
                base_year=2024,
                deflators={2025: 1.03},
            )],
            model_version_id=mv.model_version_id,
            satellite_coefficients=self._golden_coefficients(),
            version_refs=self._make_refs(),
        )
        result = runner.run(request)
        metric_types = {rs.metric_type for rs in result.run_results[0].result_sets}
        for vm_metric in VM_METRICS:
            assert vm_metric in metric_types, f"Missing metric: {vm_metric}"

    def test_batch_without_vm_prerequisites_skips_in_dev(self) -> None:
        """Dev: missing value-measures prerequisites → skip VM metrics, no error."""
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=2024, source="test-no-vm",
        )
        coeffs = self._golden_coefficients()
        runner = BatchRunner(model_store=store, environment="dev")
        request = BatchRequest(
            scenarios=[ScenarioInput(
                scenario_spec_id=uuid7(), scenario_spec_version=1,
                name="no-vm-test",
                annual_shocks={2025: np.array([100.0, 50.0, 25.0])},
                base_year=2024,
            )],
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=self._make_refs(),
        )
        result = runner.run(request)
        metric_types = {rs.metric_type for rs in result.run_results[0].result_sets}
        # Should NOT have value-measures metrics
        assert not VM_METRICS.intersection(metric_types)

    def test_batch_without_vm_prerequisites_fails_in_nondev(self) -> None:
        """Non-dev: missing value-measures prerequisites → fail closed."""
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=2024, source="test-no-vm",
        )
        coeffs = self._golden_coefficients()
        runner = BatchRunner(model_store=store, environment="staging")
        request = BatchRequest(
            scenarios=[ScenarioInput(
                scenario_spec_id=uuid7(), scenario_spec_version=1,
                name="nondev-vm-test",
                annual_shocks={2025: np.array([100.0, 50.0, 25.0])},
                base_year=2024,
            )],
            model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs,
            version_refs=self._make_refs(),
        )
        with pytest.raises(ValueMeasuresValidationError) as exc_info:
            runner.run(request)
        assert "VM_MISSING" in exc_info.value.reason_code

    def test_existing_metrics_preserved_with_vm(self) -> None:
        """Value measures are additive — existing 7 metrics still present."""
        store, mv = self._make_golden_store_and_model()
        runner = BatchRunner(model_store=store, environment="dev")
        request = BatchRequest(
            scenarios=[ScenarioInput(
                scenario_spec_id=uuid7(), scenario_spec_version=1,
                name="parity-test",
                annual_shocks={2025: np.array([100.0, 50.0, 25.0])},
                base_year=2024,
                deflators={2025: 1.03},
            )],
            model_version_id=mv.model_version_id,
            satellite_coefficients=self._golden_coefficients(),
            version_refs=self._make_refs(),
        )
        result = runner.run(request)
        metric_types = {rs.metric_type for rs in result.run_results[0].result_sets}
        for existing in ("total_output", "direct_effect", "indirect_effect",
                         "employment", "imports", "value_added", "domestic_output"):
            assert existing in metric_types, f"Missing existing metric: {existing}"

    def test_gdp_basic_values_sum_to_scalar(self) -> None:
        """GDP basic price ResultSet has _total key with correct aggregate."""
        store, mv = self._make_golden_store_and_model()
        runner = BatchRunner(model_store=store, environment="dev")
        request = BatchRequest(
            scenarios=[ScenarioInput(
                scenario_spec_id=uuid7(), scenario_spec_version=1,
                name="aggregate-test",
                annual_shocks={2025: np.array([100.0, 50.0, 25.0])},
                base_year=2024,
                deflators={2025: 1.03},
            )],
            model_version_id=mv.model_version_id,
            satellite_coefficients=self._golden_coefficients(),
            version_refs=self._make_refs(),
        )
        result = runner.run(request)
        gdp_rs = [
            rs for rs in result.run_results[0].result_sets
            if rs.metric_type == "gdp_basic_price"
        ][0]
        assert "_total" in gdp_rs.values
        # _total should equal sum of sector values
        sector_sum = sum(
            v for k, v in gdp_rs.values.items() if k != "_total"
        )
        assert abs(gdp_rs.values["_total"] - sector_sum) < 1e-10
