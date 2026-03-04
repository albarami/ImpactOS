"""Tests for value-measures prerequisites on LoadedModel (Sprint 16)."""

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.engine.model_store import LoadedModel, ModelStore
from tests.integration.golden_scenarios.shared import (
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
    SMALL_DEFLATOR_SERIES,
    SMALL_FINAL_DEMAND_F,
    SMALL_GOS,
    SMALL_IMPORTS_VECTOR,
    SMALL_TAXES_LESS_SUBSIDIES,
)


def _register_with_value_artifacts(store: ModelStore) -> LoadedModel:
    """Register a 3-sector model with all value-measures artifacts."""
    mv = store.register(
        Z=GOLDEN_Z,
        x=GOLDEN_X,
        sector_codes=SECTOR_CODES_SMALL,
        base_year=2024,
        source="test-vm",
        artifact_payload={
            "gross_operating_surplus": SMALL_GOS.tolist(),
            "taxes_less_subsidies": SMALL_TAXES_LESS_SUBSIDIES.tolist(),
            "final_demand_F": SMALL_FINAL_DEMAND_F.tolist(),
            "imports_vector": SMALL_IMPORTS_VECTOR.tolist(),
            "deflator_series": SMALL_DEFLATOR_SERIES,
        },
    )
    return store.get(mv.model_version_id)


class TestLoadedModelValueMeasuresProperties:
    """LoadedModel exposes value-measures artifacts as numpy arrays."""

    def test_has_value_measures_prerequisites_true(self) -> None:
        store = ModelStore()
        loaded = _register_with_value_artifacts(store)
        assert loaded.has_value_measures_prerequisites is True

    def test_has_value_measures_prerequisites_false_without_artifacts(self) -> None:
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=2024, source="test",
        )
        loaded = store.get(mv.model_version_id)
        assert loaded.has_value_measures_prerequisites is False

    def test_gross_operating_surplus_array(self) -> None:
        store = ModelStore()
        loaded = _register_with_value_artifacts(store)
        arr = loaded.gross_operating_surplus_array
        assert arr is not None
        np.testing.assert_array_equal(arr, SMALL_GOS)

    def test_taxes_less_subsidies_array(self) -> None:
        store = ModelStore()
        loaded = _register_with_value_artifacts(store)
        arr = loaded.taxes_less_subsidies_array
        assert arr is not None
        np.testing.assert_array_equal(arr, SMALL_TAXES_LESS_SUBSIDIES)

    def test_final_demand_f_array(self) -> None:
        store = ModelStore()
        loaded = _register_with_value_artifacts(store)
        arr = loaded.final_demand_f_array
        assert arr is not None
        assert arr.shape == (3, 4)
        np.testing.assert_array_equal(arr, SMALL_FINAL_DEMAND_F)

    def test_imports_vector_array(self) -> None:
        store = ModelStore()
        loaded = _register_with_value_artifacts(store)
        arr = loaded.imports_vector_array
        assert arr is not None
        np.testing.assert_array_equal(arr, SMALL_IMPORTS_VECTOR)

    def test_deflator_for_year_present(self) -> None:
        store = ModelStore()
        loaded = _register_with_value_artifacts(store)
        assert loaded.deflator_for_year(2024) == 1.0
        assert loaded.deflator_for_year(2025) == 1.03

    def test_deflator_for_year_missing(self) -> None:
        store = ModelStore()
        loaded = _register_with_value_artifacts(store)
        assert loaded.deflator_for_year(2030) is None

    def test_none_when_no_artifacts(self) -> None:
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=2024, source="test",
        )
        loaded = store.get(mv.model_version_id)
        assert loaded.gross_operating_surplus_array is None
        assert loaded.taxes_less_subsidies_array is None
        assert loaded.final_demand_f_array is None
        assert loaded.imports_vector_array is None
        assert loaded.deflator_for_year(2024) is None


# ---------------------------------------------------------------------------
# Task 3: Validation tests
# ---------------------------------------------------------------------------

from src.engine.value_measures_validation import (
    ValueMeasuresValidationError,
    validate_value_measures_prerequisites,
)


class TestValueMeasuresValidationError:
    """Structured error with reason_code, environment, measure."""

    def test_error_fields(self) -> None:
        err = ValueMeasuresValidationError(
            "missing GOS",
            reason_code="VM_MISSING_GOS",
            environment="staging",
            measure="gdp_market_price",
        )
        assert err.reason_code == "VM_MISSING_GOS"
        assert err.environment == "staging"
        assert err.measure == "gdp_market_price"
        assert str(err) == "missing GOS"

    def test_no_secrets_in_message(self) -> None:
        err = ValueMeasuresValidationError(
            "GOS is missing for value measures in staging",
            reason_code="VM_MISSING_GOS",
            environment="staging",
            measure="gdp_basic_price",
        )
        msg = str(err).lower()
        assert "key" not in msg or "api" not in msg
        assert "sk-" not in msg
        assert "token" not in msg


class TestValidateValueMeasuresPrerequisites:
    """Prerequisite validation for value measures."""

    def test_valid_prerequisites_pass(self) -> None:
        result = validate_value_measures_prerequisites(
            n=3,
            x=GOLDEN_X,
            gross_operating_surplus=SMALL_GOS,
            taxes_less_subsidies=SMALL_TAXES_LESS_SUBSIDIES,
            final_demand_f=SMALL_FINAL_DEMAND_F,
            imports_vector=SMALL_IMPORTS_VECTOR,
            deflator_series=SMALL_DEFLATOR_SERIES,
            base_year=2024,
        )
        assert result.is_valid

    def test_missing_gos_raises(self) -> None:
        with pytest.raises(ValueMeasuresValidationError) as exc_info:
            validate_value_measures_prerequisites(
                n=3, x=GOLDEN_X,
                gross_operating_surplus=None,
                taxes_less_subsidies=SMALL_TAXES_LESS_SUBSIDIES,
                final_demand_f=SMALL_FINAL_DEMAND_F,
                imports_vector=SMALL_IMPORTS_VECTOR,
                deflator_series=SMALL_DEFLATOR_SERIES,
                base_year=2024,
            )
        assert exc_info.value.reason_code == "VM_MISSING_GOS"

    def test_missing_taxes_raises(self) -> None:
        with pytest.raises(ValueMeasuresValidationError) as exc_info:
            validate_value_measures_prerequisites(
                n=3, x=GOLDEN_X,
                gross_operating_surplus=SMALL_GOS,
                taxes_less_subsidies=None,
                final_demand_f=SMALL_FINAL_DEMAND_F,
                imports_vector=SMALL_IMPORTS_VECTOR,
                deflator_series=SMALL_DEFLATOR_SERIES,
                base_year=2024,
            )
        assert exc_info.value.reason_code == "VM_MISSING_TAXES"

    def test_missing_final_demand_raises(self) -> None:
        with pytest.raises(ValueMeasuresValidationError) as exc_info:
            validate_value_measures_prerequisites(
                n=3, x=GOLDEN_X,
                gross_operating_surplus=SMALL_GOS,
                taxes_less_subsidies=SMALL_TAXES_LESS_SUBSIDIES,
                final_demand_f=None,
                imports_vector=SMALL_IMPORTS_VECTOR,
                deflator_series=SMALL_DEFLATOR_SERIES,
                base_year=2024,
            )
        assert exc_info.value.reason_code == "VM_MISSING_FINAL_DEMAND"

    def test_missing_imports_vector_raises(self) -> None:
        with pytest.raises(ValueMeasuresValidationError) as exc_info:
            validate_value_measures_prerequisites(
                n=3, x=GOLDEN_X,
                gross_operating_surplus=SMALL_GOS,
                taxes_less_subsidies=SMALL_TAXES_LESS_SUBSIDIES,
                final_demand_f=SMALL_FINAL_DEMAND_F,
                imports_vector=None,
                deflator_series=SMALL_DEFLATOR_SERIES,
                base_year=2024,
            )
        assert exc_info.value.reason_code == "VM_MISSING_IMPORTS"

    def test_wrong_dimension_gos_raises(self) -> None:
        with pytest.raises(ValueMeasuresValidationError) as exc_info:
            validate_value_measures_prerequisites(
                n=3, x=GOLDEN_X,
                gross_operating_surplus=np.array([1.0, 2.0]),  # wrong dim
                taxes_less_subsidies=SMALL_TAXES_LESS_SUBSIDIES,
                final_demand_f=SMALL_FINAL_DEMAND_F,
                imports_vector=SMALL_IMPORTS_VECTOR,
                deflator_series=SMALL_DEFLATOR_SERIES,
                base_year=2024,
            )
        assert exc_info.value.reason_code == "VM_DIMENSION_MISMATCH"

    def test_negative_gos_raises(self) -> None:
        with pytest.raises(ValueMeasuresValidationError) as exc_info:
            validate_value_measures_prerequisites(
                n=3, x=GOLDEN_X,
                gross_operating_surplus=np.array([-1.0, 2.0, 3.0]),
                taxes_less_subsidies=SMALL_TAXES_LESS_SUBSIDIES,
                final_demand_f=SMALL_FINAL_DEMAND_F,
                imports_vector=SMALL_IMPORTS_VECTOR,
                deflator_series=SMALL_DEFLATOR_SERIES,
                base_year=2024,
            )
        assert exc_info.value.reason_code == "VM_INVALID_GOS"

    def test_missing_deflator_raises(self) -> None:
        with pytest.raises(ValueMeasuresValidationError) as exc_info:
            validate_value_measures_prerequisites(
                n=3, x=GOLDEN_X,
                gross_operating_surplus=SMALL_GOS,
                taxes_less_subsidies=SMALL_TAXES_LESS_SUBSIDIES,
                final_demand_f=SMALL_FINAL_DEMAND_F,
                imports_vector=SMALL_IMPORTS_VECTOR,
                deflator_series=None,
                base_year=2024,
            )
        assert exc_info.value.reason_code == "VM_MISSING_DEFLATOR"

    def test_deflator_missing_base_year_raises(self) -> None:
        with pytest.raises(ValueMeasuresValidationError) as exc_info:
            validate_value_measures_prerequisites(
                n=3, x=GOLDEN_X,
                gross_operating_surplus=SMALL_GOS,
                taxes_less_subsidies=SMALL_TAXES_LESS_SUBSIDIES,
                final_demand_f=SMALL_FINAL_DEMAND_F,
                imports_vector=SMALL_IMPORTS_VECTOR,
                deflator_series={2025: 1.03},  # no 2024
                base_year=2024,
            )
        assert exc_info.value.reason_code == "VM_INVALID_DEFLATOR"

    def test_deflator_non_positive_raises(self) -> None:
        with pytest.raises(ValueMeasuresValidationError) as exc_info:
            validate_value_measures_prerequisites(
                n=3, x=GOLDEN_X,
                gross_operating_surplus=SMALL_GOS,
                taxes_less_subsidies=SMALL_TAXES_LESS_SUBSIDIES,
                final_demand_f=SMALL_FINAL_DEMAND_F,
                imports_vector=SMALL_IMPORTS_VECTOR,
                deflator_series={2024: 0.0},
                base_year=2024,
            )
        assert exc_info.value.reason_code == "VM_INVALID_DEFLATOR"

    def test_final_demand_too_few_columns_raises(self) -> None:
        with pytest.raises(ValueMeasuresValidationError) as exc_info:
            validate_value_measures_prerequisites(
                n=3, x=GOLDEN_X,
                gross_operating_surplus=SMALL_GOS,
                taxes_less_subsidies=SMALL_TAXES_LESS_SUBSIDIES,
                final_demand_f=np.array([[1, 2], [3, 4], [5, 6]]),  # only 2 cols
                imports_vector=SMALL_IMPORTS_VECTOR,
                deflator_series=SMALL_DEFLATOR_SERIES,
                base_year=2024,
            )
        assert exc_info.value.reason_code == "VM_INVALID_FINAL_DEMAND"


# ---------------------------------------------------------------------------
# Task 4: Value measures computation tests
# ---------------------------------------------------------------------------

from src.engine.leontief import LeontiefSolver
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.engine.value_measures import ValueMeasuresComputer
from tests.integration.golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_OIL_SECTOR_CODES,
    SMALL_VA_RATIO,
)


def _make_loaded_with_artifacts() -> tuple:
    """Create loaded model, solver, satellite result for value measures tests."""
    store = ModelStore()
    mv = store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR, source="test-vm",
        artifact_payload={
            "gross_operating_surplus": SMALL_GOS.tolist(),
            "taxes_less_subsidies": SMALL_TAXES_LESS_SUBSIDIES.tolist(),
            "final_demand_F": SMALL_FINAL_DEMAND_F.tolist(),
            "imports_vector": SMALL_IMPORTS_VECTOR.tolist(),
            "deflator_series": SMALL_DEFLATOR_SERIES,
        },
    )
    loaded = store.get(mv.model_version_id)

    solver = LeontiefSolver()
    delta_d = np.array([100.0, 50.0, 25.0])
    result = solver.solve(loaded_model=loaded, delta_d=delta_d)

    coeffs = SatelliteCoefficients(
        jobs_coeff=SMALL_JOBS_COEFF,
        import_ratio=SMALL_IMPORT_RATIO,
        va_ratio=SMALL_VA_RATIO,
        version_id=uuid7(),
    )
    sat = SatelliteAccounts()
    sat_result = sat.compute(delta_x=result.delta_x_total, coefficients=coeffs)
    return loaded, result, sat_result


class TestValueMeasuresComputation:
    """Deterministic value-measures computation."""

    def test_gdp_basic_price_equals_sum_va(self) -> None:
        loaded, result, sat_result = _make_loaded_with_artifacts()
        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total,
            sat_result=sat_result,
            loaded_model=loaded,
            base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        expected = float(np.sum(sat_result.delta_va))
        assert abs(vm_result.gdp_basic_price - expected) < 1e-10

    def test_gdp_market_price_exceeds_basic(self) -> None:
        """Market = basic + taxes effect. With positive taxes, market >= basic."""
        loaded, result, sat_result = _make_loaded_with_artifacts()
        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total,
            sat_result=sat_result,
            loaded_model=loaded,
            base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        assert vm_result.gdp_market_price > vm_result.gdp_basic_price

    def test_gdp_market_basic_identity(self) -> None:
        """GDP_market = GDP_basic + sum(tax_ratio * delta_x)."""
        loaded, result, sat_result = _make_loaded_with_artifacts()
        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total,
            sat_result=sat_result,
            loaded_model=loaded,
            base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        tax_ratio = SMALL_TAXES_LESS_SUBSIDIES / GOLDEN_X
        tax_effect = float(np.sum(tax_ratio * result.delta_x_total))
        expected_market = vm_result.gdp_basic_price + tax_effect
        assert abs(vm_result.gdp_market_price - expected_market) < 1e-10

    def test_gdp_real_equals_market_over_deflator(self) -> None:
        """Real GDP = market GDP / deflator(base_year)."""
        loaded, result, sat_result = _make_loaded_with_artifacts()
        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total,
            sat_result=sat_result,
            loaded_model=loaded,
            base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        # deflator(2024) = 1.0, so real == market
        assert abs(vm_result.gdp_real - vm_result.gdp_market_price) < 1e-10

    def test_gdp_intensity_ratio(self) -> None:
        """GDP intensity = GDP_market / sum(delta_x)."""
        loaded, result, sat_result = _make_loaded_with_artifacts()
        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total,
            sat_result=sat_result,
            loaded_model=loaded,
            base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        expected = vm_result.gdp_market_price / float(np.sum(result.delta_x_total))
        assert abs(vm_result.gdp_intensity - expected) < 1e-10

    def test_balance_of_trade_formula(self) -> None:
        """BoT = exports_effect - imports_effect."""
        loaded, result, sat_result = _make_loaded_with_artifacts()
        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total,
            sat_result=sat_result,
            loaded_model=loaded,
            base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        export_ratio = SMALL_FINAL_DEMAND_F[:, 3] / GOLDEN_X
        export_effect = float(np.sum(export_ratio * result.delta_x_total))
        import_effect = float(np.sum(sat_result.delta_imports))
        expected_bot = export_effect - import_effect
        assert abs(vm_result.balance_of_trade - expected_bot) < 1e-10

    def test_non_oil_exports_equals_total_when_no_oil(self) -> None:
        """With no oil sectors, non-oil exports == total exports effect."""
        loaded, result, sat_result = _make_loaded_with_artifacts()
        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total,
            sat_result=sat_result,
            loaded_model=loaded,
            base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=frozenset(),  # no oil sectors
        )
        export_ratio = SMALL_FINAL_DEMAND_F[:, 3] / GOLDEN_X
        total_exports = float(np.sum(export_ratio * result.delta_x_total))
        assert abs(vm_result.non_oil_exports - total_exports) < 1e-10

    def test_gov_revenue_spending_ratio_positive(self) -> None:
        loaded, result, sat_result = _make_loaded_with_artifacts()
        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total,
            sat_result=sat_result,
            loaded_model=loaded,
            base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        assert vm_result.government_revenue_spending_ratio > 0

    def test_deterministic_reproducibility(self) -> None:
        """Identical inputs yield identical outputs."""
        loaded, result, sat_result = _make_loaded_with_artifacts()
        vm = ValueMeasuresComputer()
        kwargs = dict(
            delta_x=result.delta_x_total,
            sat_result=sat_result,
            loaded_model=loaded,
            base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        r1 = vm.compute(**kwargs)
        r2 = vm.compute(**kwargs)
        assert r1.gdp_basic_price == r2.gdp_basic_price
        assert r1.gdp_market_price == r2.gdp_market_price
        assert r1.balance_of_trade == r2.balance_of_trade

    def test_zero_shock_produces_zero_measures(self) -> None:
        """Zero delta_x -> all value measures are zero."""
        loaded, _, _ = _make_loaded_with_artifacts()
        solver = LeontiefSolver()
        zero_result = solver.solve(loaded_model=loaded, delta_d=np.zeros(3))
        coeffs = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF, import_ratio=SMALL_IMPORT_RATIO,
            va_ratio=SMALL_VA_RATIO, version_id=uuid7(),
        )
        sat = SatelliteAccounts()
        sat_result = sat.compute(delta_x=zero_result.delta_x_total, coefficients=coeffs)
        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=zero_result.delta_x_total,
            sat_result=sat_result,
            loaded_model=loaded,
            base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        assert vm_result.gdp_basic_price == 0.0
        assert vm_result.balance_of_trade == 0.0
