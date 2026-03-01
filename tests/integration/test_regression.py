"""Regression suite — toleranced frozen snapshots (Amendment 7).

No hash-based comparison. Uses assert_allclose with documented
rtol/atol values. Golden values loaded from committed JSON snapshots
in golden_scenarios/snapshots/.

To update baselines after legitimate algorithm changes:
    pytest tests/integration/test_regression.py --update-golden
"""

import json
import numpy as np
import pytest
from datetime import datetime, timezone
from numpy.testing import assert_allclose
from pathlib import Path
from uuid_extensions import uuid7

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients

from tests.integration.golden_scenarios.shared import (
    EMPLOYMENT_ATOL,
    GDP_RTOL,
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    NUMERIC_RTOL,
    OUTPUT_RTOL,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
)

SNAPSHOTS_DIR = Path(__file__).parent / "golden_scenarios" / "snapshots"


def _load_snapshot(name: str) -> dict | None:
    """Load a frozen golden snapshot from JSON. Returns None if missing."""
    path = SNAPSHOTS_DIR / f"{name}_outputs.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _save_snapshot(name: str, data: dict) -> None:
    """Save a golden snapshot to JSON."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS_DIR / f"{name}_outputs.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _compute_pipeline(delta_d_list: list[float]) -> dict:
    """Run the deterministic pipeline and return all outputs."""
    store = ModelStore()
    mv = store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR, source="regression",
    )
    loaded = store.get(mv.model_version_id)

    solver = LeontiefSolver()
    delta_d = np.array(delta_d_list)
    solve = solver.solve(loaded_model=loaded, delta_d=delta_d)

    sat_coeff = SatelliteCoefficients(
        jobs_coeff=SMALL_JOBS_COEFF.copy(),
        import_ratio=SMALL_IMPORT_RATIO.copy(),
        va_ratio=SMALL_VA_RATIO.copy(),
        version_id=uuid7(),
    )
    sa = SatelliteAccounts()
    sat = sa.compute(delta_x=solve.delta_x_total, coefficients=sat_coeff)

    return {
        "total_output": float(solve.delta_x_total.sum()),
        "gdp_impact": float(sat.delta_va.sum()),
        "employment_total": float(sat.delta_jobs.sum()),
        "sector_outputs": {
            code: float(solve.delta_x_total[i])
            for i, code in enumerate(SECTOR_CODES_SMALL)
        },
    }


@pytest.mark.integration
@pytest.mark.regression
class TestRegressionSuite:
    """Golden regression baselines loaded from frozen JSON snapshots."""

    def test_industrial_zone_output_stable(self, update_golden):
        """Total output has not drifted from frozen baseline."""
        current = _compute_pipeline([300.0, 150.0, 50.0])

        if update_golden:
            snapshot = {
                "scenario": "industrial_zone",
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "model": "3-sector ISIC F/C/G",
                "tolerances": {"rtol": NUMERIC_RTOL, "employment_atol": EMPLOYMENT_ATOL, "gdp_rtol": GDP_RTOL},
                "delta_d": [300.0, 150.0, 50.0],
                "total_output_impact": current["total_output"],
                "gdp_impact": current["gdp_impact"],
                "employment_total": current["employment_total"],
                "sector_outputs": current["sector_outputs"],
                "quality_grade": None,
            }
            _save_snapshot("industrial_zone", snapshot)
            pytest.skip("Regression snapshot updated")

        golden = _load_snapshot("industrial_zone")
        if golden is None or golden.get("total_output_impact") is None:
            pytest.skip("No baseline — run with --update-golden first")

        assert_allclose(
            current["total_output"],
            golden["total_output_impact"],
            rtol=NUMERIC_RTOL,
            err_msg="Total output regression detected",
        )

    def test_industrial_zone_gdp_stable(self, update_golden):
        """GDP impact has not drifted from frozen baseline."""
        current = _compute_pipeline([300.0, 150.0, 50.0])

        golden = _load_snapshot("industrial_zone")
        if golden is None or golden.get("gdp_impact") is None:
            pytest.skip("No baseline — run with --update-golden first")

        assert_allclose(
            current["gdp_impact"],
            golden["gdp_impact"],
            rtol=GDP_RTOL,
            err_msg="GDP regression detected",
        )

    def test_industrial_zone_employment_stable(self, update_golden):
        """Employment has not drifted from frozen baseline."""
        current = _compute_pipeline([300.0, 150.0, 50.0])

        golden = _load_snapshot("industrial_zone")
        if golden is None or golden.get("employment_total") is None:
            pytest.skip("No baseline — run with --update-golden first")

        assert current["employment_total"] == pytest.approx(
            golden["employment_total"], abs=EMPLOYMENT_ATOL,
        )

    def test_contraction_output_stable(self, update_golden):
        """Contraction scenario output has not drifted from frozen baseline."""
        current = _compute_pipeline([-100.0, -50.0, -30.0])

        golden = _load_snapshot("contraction")
        if golden is None or golden.get("total_output_impact") is None:
            pytest.skip("No baseline — run with --update-golden first")

        assert_allclose(
            current["total_output"],
            golden["total_output_impact"],
            rtol=NUMERIC_RTOL,
            err_msg="Contraction output regression detected",
        )

    def test_per_sector_output_stable(self, update_golden):
        """Per-sector outputs match frozen baseline within tolerance."""
        current = _compute_pipeline([300.0, 150.0, 50.0])

        golden = _load_snapshot("industrial_zone")
        if golden is None or not golden.get("sector_outputs"):
            pytest.skip("No baseline — run with --update-golden first")

        for code in SECTOR_CODES_SMALL:
            assert_allclose(
                current["sector_outputs"][code],
                golden["sector_outputs"][code],
                rtol=NUMERIC_RTOL,
                err_msg=f"Sector {code} regression detected",
            )

    def test_numerical_tolerance_documented(self):
        """Tolerance constants are defined and positive."""
        assert NUMERIC_RTOL > 0
        assert EMPLOYMENT_ATOL > 0
        assert GDP_RTOL > 0
        assert OUTPUT_RTOL > 0
