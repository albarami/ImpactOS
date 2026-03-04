"""Pytest fixture definitions for MVP-14 integration tests.

This file contains ONLY @pytest.fixture functions.
All constants and helpers live in shared.py.
"""

import pytest
from uuid_extensions import uuid7

from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteCoefficients

from .shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
)


@pytest.fixture
def model_store() -> ModelStore:
    """Fresh ModelStore instance."""
    return ModelStore()


@pytest.fixture
def small_model_version(model_store: ModelStore):
    """Register the 3-sector toy IO model (ISIC F/C/G)."""
    mv = model_store.register(
        Z=GOLDEN_Z,
        x=GOLDEN_X,
        sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR,
        source="golden-integration-test-small",
    )
    return mv


@pytest.fixture
def small_loaded_model(model_store: ModelStore, small_model_version):
    """Load the 3-sector toy model for computation."""
    return model_store.get(small_model_version.model_version_id)


@pytest.fixture
def small_satellite_coefficients() -> SatelliteCoefficients:
    """Satellite coefficients for the 3-sector toy model."""
    return SatelliteCoefficients(
        jobs_coeff=SMALL_JOBS_COEFF.copy(),
        import_ratio=SMALL_IMPORT_RATIO.copy(),
        va_ratio=SMALL_VA_RATIO.copy(),
        version_id=uuid7(),
    )
