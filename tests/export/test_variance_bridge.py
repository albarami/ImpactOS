"""Tests for variance bridge (MVP-6).

Covers: compare two runs and decompose changes into drivers —
phasing, import share, mapping, constraint, model version changes.
Output as waterfall dataset.
"""

import pytest
from uuid_extensions import uuid7

from src.export.variance_bridge import (
    AdvancedVarianceBridge,
    BridgeDiagnostics,
    BridgeResult,
    DriverType,
    VarianceBridge,
    VarianceDriver,
    WaterfallDataset,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_A = uuid7()
RUN_B = uuid7()


def _make_run_data(
    total: float = 4_200_000_000.0,
    phasing: dict | None = None,
    import_shares: dict | None = None,
    mapping_count: int = 50,
    constraints_active: int = 0,
    model_version: str = "v1",
) -> dict:
    return {
        "run_id": str(uuid7()),
        "total_impact": total,
        "phasing": phasing or {"2026": 0.3, "2027": 0.4, "2028": 0.3},
        "import_shares": import_shares or {"C41": 0.35, "F": 0.30},
        "mapping_count": mapping_count,
        "constraints_active": constraints_active,
        "model_version": model_version,
    }


# ===================================================================
# Basic bridge
# ===================================================================


class TestBasicBridge:
    """Compare two runs and decompose."""

    def test_bridge_produces_waterfall(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(total=4_200_000_000.0)
        run_b = _make_run_data(total=4_500_000_000.0)
        result = bridge.compare(run_a=run_a, run_b=run_b)
        assert isinstance(result, WaterfallDataset)

    def test_bridge_total_variance(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(total=4_200_000_000.0)
        run_b = _make_run_data(total=4_500_000_000.0)
        result = bridge.compare(run_a=run_a, run_b=run_b)
        assert result.total_variance == pytest.approx(300_000_000.0)

    def test_bridge_start_and_end(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(total=4_200_000_000.0)
        run_b = _make_run_data(total=4_500_000_000.0)
        result = bridge.compare(run_a=run_a, run_b=run_b)
        assert result.start_value == 4_200_000_000.0
        assert result.end_value == 4_500_000_000.0

    def test_no_change(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(total=4_200_000_000.0)
        run_b = _make_run_data(total=4_200_000_000.0)
        result = bridge.compare(run_a=run_a, run_b=run_b)
        assert result.total_variance == pytest.approx(0.0)


# ===================================================================
# Driver decomposition
# ===================================================================


class TestDriverDecomposition:
    """Decompose into contributing factors."""

    def test_phasing_driver_detected(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(phasing={"2026": 0.3, "2027": 0.4, "2028": 0.3})
        run_b = _make_run_data(phasing={"2026": 0.5, "2027": 0.3, "2028": 0.2})
        result = bridge.compare(run_a=run_a, run_b=run_b)
        drivers = {d.driver_type for d in result.drivers}
        assert DriverType.PHASING in drivers

    def test_import_share_driver_detected(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(import_shares={"C41": 0.35})
        run_b = _make_run_data(import_shares={"C41": 0.25})
        result = bridge.compare(run_a=run_a, run_b=run_b)
        drivers = {d.driver_type for d in result.drivers}
        assert DriverType.IMPORT_SHARE in drivers

    def test_mapping_driver_detected(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(mapping_count=50)
        run_b = _make_run_data(mapping_count=55)
        result = bridge.compare(run_a=run_a, run_b=run_b)
        drivers = {d.driver_type for d in result.drivers}
        assert DriverType.MAPPING in drivers

    def test_constraint_driver_detected(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(constraints_active=0)
        run_b = _make_run_data(constraints_active=3)
        result = bridge.compare(run_a=run_a, run_b=run_b)
        drivers = {d.driver_type for d in result.drivers}
        assert DriverType.CONSTRAINT in drivers

    def test_model_version_driver_detected(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(model_version="v1")
        run_b = _make_run_data(model_version="v2")
        result = bridge.compare(run_a=run_a, run_b=run_b)
        drivers = {d.driver_type for d in result.drivers}
        assert DriverType.MODEL_VERSION in drivers

    def test_drivers_sum_to_total_variance(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(total=4_200_000_000.0)
        run_b = _make_run_data(total=4_500_000_000.0, phasing={"2026": 0.5, "2027": 0.3, "2028": 0.2})
        result = bridge.compare(run_a=run_a, run_b=run_b)
        driver_sum = sum(d.impact for d in result.drivers)
        assert driver_sum == pytest.approx(result.total_variance)

    def test_no_drivers_when_identical(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data()
        run_b = _make_run_data()
        result = bridge.compare(run_a=run_a, run_b=run_b)
        # Only residual driver with 0 impact
        non_zero = [d for d in result.drivers if abs(d.impact) > 1e-9]
        assert len(non_zero) == 0


# ===================================================================
# Waterfall dataset
# ===================================================================


class TestWaterfallDataset:
    """Waterfall dataset for reporting."""

    def test_to_dict(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(total=4_200_000_000.0)
        run_b = _make_run_data(total=4_500_000_000.0, model_version="v2")
        result = bridge.compare(run_a=run_a, run_b=run_b)
        d = result.to_dict()
        assert "start_value" in d
        assert "end_value" in d
        assert "total_variance" in d
        assert "drivers" in d
        assert isinstance(d["drivers"], list)

    def test_driver_dict_structure(self) -> None:
        bridge = VarianceBridge()
        run_a = _make_run_data(total=4_200_000_000.0)
        run_b = _make_run_data(total=4_500_000_000.0, model_version="v2")
        result = bridge.compare(run_a=run_a, run_b=run_b)
        d = result.to_dict()
        for driver in d["drivers"]:
            assert "driver_type" in driver
            assert "description" in driver
            assert "impact" in driver


# ---------------------------------------------------------------------------
# Sprint 23: Advanced artifact-linked variance bridge tests
# ---------------------------------------------------------------------------


class TestAdvancedBridgeAttribution:
    """S23-1: Deterministic attribution from artifact diffs."""

    def test_phasing_driver_from_time_horizon_diff(self):
        """Phasing driver detected when time_horizon differs."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(model_version_id="mv1"),
            run_b_snapshot=_snap(model_version_id="mv1"),
            result_a=_result(total=100.0),
            result_b=_result(total=120.0),
            spec_a=_spec(time_horizon={"start": 2025, "end": 2030}),
            spec_b=_spec(time_horizon={"start": 2025, "end": 2035}),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.PHASING in driver_types

    def test_import_share_driver_from_shock_diff(self):
        """Import share driver detected when ImportSubstitution shocks differ."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),
            result_a=_result(total=100.0),
            result_b=_result(total=110.0),
            spec_a=_spec(shock_items=[{"type": "ImportSubstitution", "sector": "A", "value": 0.1}]),
            spec_b=_spec(shock_items=[{"type": "ImportSubstitution", "sector": "A", "value": 0.2}]),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.IMPORT_SHARE in driver_types

    def test_mapping_driver_from_version_diff(self):
        """Mapping driver detected when mapping_library_version_id differs."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(mapping_library_version_id="map_v1"),
            run_b_snapshot=_snap(mapping_library_version_id="map_v2"),
            result_a=_result(total=100.0),
            result_b=_result(total=115.0),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.MAPPING in driver_types

    def test_constraint_driver_from_version_diff(self):
        """Constraint driver detected when constraint_set_version_id differs."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(constraint_set_version_id="cs1"),
            run_b_snapshot=_snap(constraint_set_version_id="cs2"),
            result_a=_result(total=100.0),
            result_b=_result(total=108.0),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.CONSTRAINT in driver_types

    def test_model_version_driver_from_version_diff(self):
        """Model version driver detected when model_version_id differs."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(model_version_id="mv1"),
            run_b_snapshot=_snap(model_version_id="mv2"),
            result_a=_result(total=100.0),
            result_b=_result(total=130.0),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.MODEL_VERSION in driver_types

    def test_feasibility_driver_from_constraint_shocks(self):
        """Feasibility driver detected when ConstraintOverride shocks differ."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),
            result_a=_result(total=100.0),
            result_b=_result(total=95.0),
            spec_a=_spec(shock_items=[]),
            spec_b=_spec(shock_items=[{"type": "ConstraintOverride", "sector": "X", "value": 0.5}]),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.FEASIBILITY in driver_types


class TestAdvancedBridgeIdentity:
    """S23-1: Strict identity invariant."""

    def test_drivers_sum_to_total_variance(self):
        """sum(driver.impact) == total_variance within tolerance."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(model_version_id="mv1", mapping_library_version_id="m1"),
            run_b_snapshot=_snap(model_version_id="mv2", mapping_library_version_id="m2"),
            result_a=_result(total=100.0),
            result_b=_result(total=150.0),
        )
        driver_sum = sum(d.impact for d in result.drivers)
        assert abs(driver_sum - result.total_variance) < 1e-9

    def test_zero_magnitudes_nonzero_variance_goes_to_residual(self):
        """All zero magnitudes + nonzero variance -> 100% RESIDUAL."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),  # identical snapshots
            result_a=_result(total=100.0),
            result_b=_result(total=120.0),  # but different results
        )
        assert len(result.drivers) == 1
        assert result.drivers[0].driver_type == DriverType.RESIDUAL
        assert abs(result.drivers[0].impact - 20.0) < 1e-9

    def test_zero_variance_no_drivers(self):
        """Zero total variance -> no drivers (or one RESIDUAL with 0)."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),
            result_a=_result(total=100.0),
            result_b=_result(total=100.0),
        )
        driver_sum = sum(d.impact for d in result.drivers)
        assert abs(driver_sum) < 1e-9

    def test_identity_tolerance_boundary(self):
        """Identity check uses 1e-9 tolerance."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(model_version_id="mv1"),
            run_b_snapshot=_snap(model_version_id="mv2"),
            result_a=_result(total=100.0),
            result_b=_result(total=100.0 + 1e-10),
        )
        assert result.diagnostics.identity_verified


class TestAdvancedBridgeDeterminism:
    """S23-1: Deterministic replay."""

    def test_same_inputs_produce_identical_checksum(self):
        """Same inputs -> identical output checksum."""
        kwargs = dict(
            run_a_snapshot=_snap(model_version_id="mv1"),
            run_b_snapshot=_snap(model_version_id="mv2"),
            result_a=_result(total=100.0),
            result_b=_result(total=130.0),
        )
        r1 = AdvancedVarianceBridge.compute_from_artifacts(**kwargs)
        r2 = AdvancedVarianceBridge.compute_from_artifacts(**kwargs)
        assert r1.diagnostics.checksum == r2.diagnostics.checksum

    def test_deterministic_driver_sort(self):
        """Drivers sorted by DriverType enum order, then abs(impact) desc."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(
                model_version_id="mv1",
                mapping_library_version_id="m1",
                constraint_set_version_id="cs1",
            ),
            run_b_snapshot=_snap(
                model_version_id="mv2",
                mapping_library_version_id="m2",
                constraint_set_version_id="cs2",
            ),
            result_a=_result(total=100.0),
            result_b=_result(total=160.0),
        )
        types = [d.driver_type for d in result.drivers]
        # Enum order: PHASING, IMPORT_SHARE, MAPPING, CONSTRAINT, MODEL_VERSION, FEASIBILITY, RESIDUAL
        type_indices = [list(DriverType).index(t) for t in types]
        assert type_indices == sorted(type_indices)


class TestAdvancedBridgeDiagnostics:
    """S23-1: Structured diagnostics payload."""

    def test_diagnostics_includes_checksum(self):
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),
            result_a=_result(total=100.0),
            result_b=_result(total=100.0),
        )
        assert result.diagnostics.checksum.startswith("sha256:")

    def test_diagnostics_identity_verified(self):
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),
            result_a=_result(total=100.0),
            result_b=_result(total=120.0),
        )
        assert result.diagnostics.identity_verified is True

    def test_diagnostics_per_driver_metadata(self):
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(model_version_id="mv1"),
            run_b_snapshot=_snap(model_version_id="mv2"),
            result_a=_result(total=100.0),
            result_b=_result(total=130.0),
        )
        mv_driver = next(d for d in result.drivers if d.driver_type == DriverType.MODEL_VERSION)
        assert mv_driver.raw_magnitude > 0
        assert mv_driver.weight > 0
        assert mv_driver.source_field is not None


# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------

def _snap(
    *,
    model_version_id: str = "mv_default",
    taxonomy_version_id: str = "tv_default",
    concordance_version_id: str = "cv_default",
    mapping_library_version_id: str = "ml_default",
    assumption_library_version_id: str = "al_default",
    prompt_pack_version_id: str = "pp_default",
    constraint_set_version_id: str | None = None,
) -> dict:
    """Build a minimal RunSnapshot-like dict for testing."""
    return {
        "model_version_id": model_version_id,
        "taxonomy_version_id": taxonomy_version_id,
        "concordance_version_id": concordance_version_id,
        "mapping_library_version_id": mapping_library_version_id,
        "assumption_library_version_id": assumption_library_version_id,
        "prompt_pack_version_id": prompt_pack_version_id,
        "constraint_set_version_id": constraint_set_version_id,
    }


def _result(*, total: float) -> dict:
    """Build a minimal ResultSet-like dict for testing."""
    return {"values": {"total": total}}


def _spec(
    *,
    time_horizon: dict | None = None,
    shock_items: list | None = None,
) -> dict:
    """Build a minimal ScenarioSpec-like dict for testing."""
    return {
        "time_horizon": time_horizon or {"start": 2025, "end": 2030},
        "shock_items": shock_items or [],
    }
