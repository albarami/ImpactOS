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
