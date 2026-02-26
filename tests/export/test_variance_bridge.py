"""Tests for variance bridge (MVP-6).

Covers: compare two runs and decompose changes into drivers —
phasing, import share, mapping, constraint, model version changes.
Output as waterfall dataset.
"""

import pytest
from uuid_extensions import uuid7

from src.export.variance_bridge import VarianceBridge, WaterfallDataset, DriverType


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
