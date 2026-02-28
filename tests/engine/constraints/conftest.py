"""Shared fixtures for constraint/feasibility tests."""

from uuid import uuid4

import numpy as np
import pytest

from src.engine.constraints.schema import (
    Constraint,
    ConstraintBoundScope,
    ConstraintScope,
    ConstraintSet,
    ConstraintType,
    ConstraintUnit,
)
from src.engine.model_store import LoadedModel, ModelStore
from src.engine.satellites import SatelliteCoefficients
from src.models.common import ConstraintConfidence, new_uuid7


@pytest.fixture()
def workspace_id():
    return uuid4()


@pytest.fixture()
def model_version_id():
    return new_uuid7()


@pytest.fixture()
def two_sector_model() -> LoadedModel:
    """Simple 2-sector IO model for constraint testing.

    Sector 0 ("A"): agriculture, x=100
    Sector 1 ("F"): construction, x=200
    """
    store = ModelStore()
    Z = np.array([[10.0, 20.0], [5.0, 40.0]])
    x = np.array([100.0, 200.0])
    mv = store.register(
        Z=Z, x=x,
        sector_codes=["A", "F"],
        base_year=2024,
        source="test-2sector",
    )
    return store.get(mv.model_version_id)


@pytest.fixture()
def two_sector_coefficients() -> SatelliteCoefficients:
    """Satellite coefficients matching the 2-sector model."""
    return SatelliteCoefficients(
        jobs_coeff=np.array([0.5, 1.0]),    # 0.5 jobs/unit for A, 1.0 for F
        import_ratio=np.array([0.2, 0.3]),  # 20% imports for A, 30% for F
        va_ratio=np.array([0.6, 0.4]),      # 60% VA for A, 40% for F
        version_id=uuid4(),
    )


@pytest.fixture()
def capacity_cap_constraint_f() -> Constraint:
    """Capacity cap: sector F max absolute output = 250."""
    return Constraint(
        constraint_type=ConstraintType.CAPACITY_CAP,
        scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
        description="Construction capacity limit",
        upper_bound=250.0,
        bound_scope=ConstraintBoundScope.ABSOLUTE_TOTAL,
        unit=ConstraintUnit.SAR_MILLIONS,
        confidence=ConstraintConfidence.ESTIMATED,
    )


@pytest.fixture()
def ramp_constraint_f() -> Constraint:
    """Ramp: sector F max 15% growth from base."""
    return Constraint(
        constraint_type=ConstraintType.RAMP,
        scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
        description="Construction ramp limit",
        max_growth_rate=0.15,
        bound_scope=ConstraintBoundScope.ABSOLUTE_TOTAL,
        unit=ConstraintUnit.GROWTH_RATE,
        confidence=ConstraintConfidence.ASSUMED,
    )


@pytest.fixture()
def empty_constraint_set(workspace_id, model_version_id) -> ConstraintSet:
    """ConstraintSet with no constraints."""
    return ConstraintSet(
        workspace_id=workspace_id,
        model_version_id=model_version_id,
        name="empty",
        constraints=[],
    )
