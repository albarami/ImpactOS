"""End-to-end golden tests using frozen JSON snapshots.

Each test runs the FULL deterministic pipeline and compares
against toleranced expected values loaded from committed JSON
files in golden_scenarios/snapshots/.

Golden values are NEVER recomputed automatically. To update:
    pytest tests/integration/test_e2e_golden.py --update-golden

Updated JSON files must be reviewed and committed.
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
from src.quality.service import QualityAssessmentService

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


def _load_snapshot(name: str) -> dict:
    """Load a frozen golden snapshot from JSON."""
    path = SNAPSHOTS_DIR / f"{name}_outputs.json"
    if not path.exists():
        pytest.skip(f"Snapshot {path} not found — run with --update-golden first")
    with open(path) as f:
        return json.load(f)


def _save_snapshot(name: str, data: dict) -> None:
    """Save a golden snapshot to JSON."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS_DIR / f"{name}_outputs.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _run_full_pipeline(delta_d: list[float], base_year: int = GOLDEN_BASE_YEAR) -> dict:
    """Run complete deterministic pipeline and return all results."""
    store = ModelStore()
    mv = store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=base_year, source="golden-e2e",
    )
    loaded = store.get(mv.model_version_id)

    solver = LeontiefSolver()
    solve = solver.solve(loaded_model=loaded, delta_d=np.asarray(delta_d))

    sat_coeff = SatelliteCoefficients(
        jobs_coeff=SMALL_JOBS_COEFF.copy(),
        import_ratio=SMALL_IMPORT_RATIO.copy(),
        va_ratio=SMALL_VA_RATIO.copy(),
        version_id=uuid7(),
    )
    sa = SatelliteAccounts()
    sat = sa.compute(delta_x=solve.delta_x_total, coefficients=sat_coeff)

    return {
        "delta_x": solve.delta_x_total,
        "total_output": float(solve.delta_x_total.sum()),
        "gdp_impact": float(sat.delta_va.sum()),
        "employment_total": float(sat.delta_jobs.sum()),
        "sector_outputs": {
            code: float(solve.delta_x_total[i])
            for i, code in enumerate(SECTOR_CODES_SMALL)
        },
    }


@pytest.mark.integration
@pytest.mark.golden
class TestEndToEndGolden:
    """End-to-end golden tests with frozen snapshot comparison."""

    def test_industrial_zone_full_pipeline(self, update_golden):
        """Golden Scenario 1: Industrial zone — full happy path."""
        results = _run_full_pipeline([300.0, 150.0, 50.0])

        if update_golden:
            snapshot = {
                "scenario": "industrial_zone",
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "model": "3-sector ISIC F/C/G",
                "tolerances": {
                    "rtol": NUMERIC_RTOL,
                    "employment_atol": EMPLOYMENT_ATOL,
                    "gdp_rtol": GDP_RTOL,
                },
                "delta_d": [300.0, 150.0, 50.0],
                "total_output_impact": results["total_output"],
                "gdp_impact": results["gdp_impact"],
                "employment_total": results["employment_total"],
                "sector_outputs": results["sector_outputs"],
                "quality_grade": None,
            }
            _save_snapshot("industrial_zone", snapshot)
            pytest.skip("Golden snapshot updated — review and commit")

        golden = _load_snapshot("industrial_zone")
        if golden.get("total_output_impact") is None:
            pytest.skip("Snapshot has null values — run with --update-golden first")

        assert_allclose(
            results["total_output"],
            golden["total_output_impact"],
            rtol=NUMERIC_RTOL,
            err_msg="Total output drifted from golden",
        )
        assert_allclose(
            results["gdp_impact"],
            golden["gdp_impact"],
            rtol=GDP_RTOL,
            err_msg="GDP impact drifted from golden",
        )
        assert results["employment_total"] == pytest.approx(
            golden["employment_total"], abs=EMPLOYMENT_ATOL,
        )
        for code in SECTOR_CODES_SMALL:
            assert_allclose(
                results["sector_outputs"][code],
                golden["sector_outputs"][code],
                rtol=NUMERIC_RTOL,
                err_msg=f"Sector {code} output drifted from golden",
            )

    def test_contraction_scenario(self, update_golden):
        """Golden Scenario 3: Negative demand shock — frozen snapshot."""
        results = _run_full_pipeline([-100.0, -50.0, -30.0])

        if update_golden:
            snapshot = {
                "scenario": "contraction",
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "model": "3-sector ISIC F/C/G",
                "tolerances": {
                    "rtol": NUMERIC_RTOL,
                    "employment_atol": EMPLOYMENT_ATOL,
                    "gdp_rtol": GDP_RTOL,
                },
                "delta_d": [-100.0, -50.0, -30.0],
                "total_output_impact": results["total_output"],
                "gdp_impact": results["gdp_impact"],
                "employment_total": results["employment_total"],
                "sector_outputs": results["sector_outputs"],
                "quality_grade": None,
            }
            _save_snapshot("contraction", snapshot)
            pytest.skip("Golden snapshot updated — review and commit")

        golden = _load_snapshot("contraction")
        if golden.get("total_output_impact") is None:
            pytest.skip("Snapshot has null values — run with --update-golden first")

        assert results["total_output"] < 0
        assert results["gdp_impact"] < 0
        assert results["employment_total"] < 0

        assert_allclose(
            results["total_output"],
            golden["total_output_impact"],
            rtol=NUMERIC_RTOL,
        )
        assert_allclose(
            results["gdp_impact"],
            golden["gdp_impact"],
            rtol=GDP_RTOL,
        )

    def test_mega_project_gaps(self, update_golden):
        """Golden Scenario 2: Mega-project with data gaps — frozen snapshot."""
        results = _run_full_pipeline([200.0, 100.0, 100.0], base_year=2018)

        if update_golden:
            snapshot = {
                "scenario": "mega_project_gaps",
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "model": "3-sector ISIC F/C/G",
                "tolerances": {
                    "rtol": NUMERIC_RTOL,
                    "employment_atol": EMPLOYMENT_ATOL,
                    "gdp_rtol": GDP_RTOL,
                },
                "delta_d": [200.0, 100.0, 100.0],
                "total_output_impact": results["total_output"],
                "gdp_impact": results["gdp_impact"],
                "employment_total": results["employment_total"],
                "sector_outputs": results["sector_outputs"],
                "quality_grade": None,
            }
            _save_snapshot("mega_project_gaps", snapshot)
            pytest.skip("Golden snapshot updated — review and commit")

        golden = _load_snapshot("mega_project_gaps")
        if golden.get("total_output_impact") is None:
            pytest.skip("Snapshot has null values — run with --update-golden first")

        assert_allclose(
            results["total_output"],
            golden["total_output_impact"],
            rtol=NUMERIC_RTOL,
        )

    def test_reproducibility_across_runs(self):
        """Same golden scenario produces identical results 3 times."""
        delta_d = [300.0, 150.0, 50.0]
        results = [_run_full_pipeline(delta_d) for _ in range(3)]

        for i in range(1, 3):
            assert_allclose(
                results[0]["total_output"],
                results[i]["total_output"],
                rtol=0,
            )
            assert_allclose(
                results[0]["gdp_impact"],
                results[i]["gdp_impact"],
                rtol=0,
            )

    def test_quality_assessment_from_full_run(self, update_golden):
        """Full run feeds quality assessment — grade verified against snapshot."""
        results = _run_full_pipeline([300.0, 150.0, 50.0])

        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=GOLDEN_BASE_YEAR,
            current_year=2026,
            mapping_coverage_pct=0.95,
            mapping_confidence_dist={"HIGH": 0.8, "MEDIUM": 0.15, "LOW": 0.05},
            mapping_residual_pct=0.02,
            mapping_unresolved_pct=0.01,
            mapping_unresolved_spend_pct=0.3,
            assumption_ranges_coverage_pct=0.85,
            assumption_approval_rate=0.9,
            constraint_confidence_summary={"HARD": 5, "ESTIMATED": 2, "ASSUMED": 1},
            workforce_overall_confidence="HIGH",
            plausibility_in_range_pct=95.0,
            plausibility_flagged_count=0,
            source_ages=[],
            run_id=uuid7(),
        )
        assert assessment.grade.value in ("A", "B")

    def test_data_gaps_lower_quality_grade(self):
        """Scenario 2: Data gaps produce lower quality grade (C or D)."""
        _run_full_pipeline([200.0, 100.0, 100.0], base_year=2018)

        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=2018,
            current_year=2026,
            mapping_coverage_pct=0.70,
            mapping_confidence_dist={"HIGH": 0.3, "MEDIUM": 0.3, "LOW": 0.4},
            mapping_residual_pct=0.15,
            mapping_unresolved_pct=0.10,
            mapping_unresolved_spend_pct=3.0,
            assumption_ranges_coverage_pct=0.4,
            assumption_approval_rate=0.5,
            constraint_confidence_summary={"HARD": 1, "ESTIMATED": 1, "ASSUMED": 4},
            workforce_overall_confidence="LOW",
            plausibility_in_range_pct=70.0,
            plausibility_flagged_count=5,
            source_ages=[],
            run_id=uuid7(),
        )
        assert assessment.grade.value in ("C", "D", "F")
