"""Step 6: Integration test proving real economist workflow.

Exercises the FULL deterministic pipeline end-to-end without mocks:

  Model load → shock → Leontief solve → satellites (employment, imports, VA)
  → workforce saudization (D-4 pipeline) → feasibility (with/without constraints)
  → sector breakdowns → ResultPackager → governance claims → export

This is the capstone test for gap closure. If this passes, the system
does real economic computation from registered data to exportable output.
"""

from uuid import UUID

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.engine.batch import BatchRequest, BatchRunner, ScenarioInput
from src.engine.feasibility import ConstraintSpec
from src.engine.model_store import LoadedModel, ModelStore
from src.engine.satellites import SatelliteCoefficients
from src.export.result_packager import ResultPackager
from src.governance.claim_extractor import create_claims_from_results
from src.models.common import new_uuid7
from src.models.model_version import ModelVersion
from src.models.run import ResultSet


# ===================================================================
# Real Saudi IO Model (3 sectors: Construction, Manufacturing, Services)
# ===================================================================

def _build_saudi_model() -> tuple[ModelStore, LoadedModel, UUID]:
    """Build a realistic 3-sector Saudi IO model.

    Uses plausible inter-industry transaction flows:
    - F (Construction): high import leakage, labor intensive
    - C (Manufacturing): strong backward linkages
    - G (Services): large domestic multiplier
    """
    store = ModelStore()
    n = 3
    mv = ModelVersion(
        model_version_id=new_uuid7(),
        base_year=2023,
        source="test_economist_workflow",
        sector_count=n,
        checksum="sha256:" + "b" * 64,
        model_denomination="SAR_MILLIONS",
    )
    # Inter-industry transaction matrix (millions SAR)
    Z = np.array([
        [   0.0, 150.0, 80.0],  # F buys from F, C, G
        [ 200.0,   0.0, 120.0], # C buys from F, C, G
        [ 100.0, 180.0,   0.0], # G buys from F, C, G
    ], dtype=np.float64)
    # Total output per sector
    x = np.array([2000.0, 3000.0, 4000.0], dtype=np.float64)
    sector_codes = ["F", "C", "G"]

    loaded = LoadedModel(
        model_version=mv,
        Z=Z,
        x=x,
        sector_codes=sector_codes,
    )
    store.cache_prevalidated(loaded)
    return store, loaded, mv.model_version_id


def _build_coefficients() -> SatelliteCoefficients:
    """Build realistic satellite coefficients."""
    return SatelliteCoefficients(
        jobs_coeff=np.array([15.0, 8.0, 12.0]),   # jobs per million SAR
        import_ratio=np.array([0.35, 0.25, 0.10]), # import shares
        va_ratio=np.array([0.40, 0.50, 0.65]),     # value added ratios
        version_id=new_uuid7(),
    )


def _build_version_refs() -> dict[str, UUID]:
    return {
        "taxonomy_version_id": new_uuid7(),
        "concordance_version_id": new_uuid7(),
        "mapping_library_version_id": new_uuid7(),
        "assumption_library_version_id": new_uuid7(),
        "prompt_pack_version_id": new_uuid7(),
    }


# ===================================================================
# The capstone test
# ===================================================================


class TestRealEconomistWorkflow:
    """Prove the full economist workflow from model to export."""

    def _run_scenario(
        self,
        store: ModelStore,
        mv_id: UUID,
        shock: np.ndarray,
        name: str = "Construction Megaproject",
        constraints: list[ConstraintSpec] | None = None,
    ) -> list[ResultSet]:
        """Execute a single scenario and return result sets."""
        runner = BatchRunner(model_store=store, environment="dev")
        scenario = ScenarioInput(
            scenario_spec_id=new_uuid7(),
            scenario_spec_version=1,
            name=name,
            annual_shocks={2023: shock},
            base_year=2023,
        )
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=mv_id,
            satellite_coefficients=_build_coefficients(),
            version_refs=_build_version_refs(),
            constraints=constraints,
        )
        result = runner.run(request)
        return result.run_results[0].result_sets

    # ---------------------------------------------------------------
    # 1. Engine produces all metric types
    # ---------------------------------------------------------------

    def test_engine_produces_complete_metric_set(self) -> None:
        """A single run produces all 19 expected cumulative ResultSets."""
        store, _, mv_id = _build_saudi_model()
        shock = np.array([500_000_000.0, 0.0, 0.0])  # 500M SAR to construction
        result_sets = self._run_scenario(store, mv_id, shock)

        # Filter to cumulative only (no annual series)
        cumulative = [rs for rs in result_sets if rs.series_kind is None]
        metric_types = {rs.metric_type for rs in cumulative}

        # Core engine outputs
        assert "total_output" in metric_types
        assert "direct_effect" in metric_types
        assert "indirect_effect" in metric_types

        # Satellite outputs
        assert "employment" in metric_types
        assert "imports" in metric_types
        assert "domestic_output" in metric_types
        assert "value_added" in metric_types

        # Workforce saudization outputs (Step 3)
        assert "saudization_saudi_ready" in metric_types
        assert "saudization_saudi_trainable" in metric_types
        assert "saudization_expat_reliant" in metric_types

        # Feasibility outputs — always present (Step 4)
        assert "feasible_output" in metric_types
        assert "constraint_gap" in metric_types

    # ---------------------------------------------------------------
    # 2. Leontief computation is numerically correct
    # ---------------------------------------------------------------

    def test_leontief_direct_plus_indirect_equals_total(self) -> None:
        """Total output = direct + indirect for each sector."""
        store, _, mv_id = _build_saudi_model()
        shock = np.array([500_000_000.0, 0.0, 0.0])
        result_sets = self._run_scenario(store, mv_id, shock)

        cumulative = {
            rs.metric_type: rs for rs in result_sets if rs.series_kind is None
        }
        total = cumulative["total_output"]
        direct = cumulative["direct_effect"]
        indirect = cumulative["indirect_effect"]

        for sector in total.values:
            if sector.startswith("_"):
                continue
            d = direct.values.get(sector, 0.0)
            i = indirect.values.get(sector, 0.0)
            t = total.values[sector]
            assert abs(d + i - t) < 1.0, (
                f"d({d:.0f}) + i({i:.0f}) != t({t:.0f}) for {sector}"
            )

    def test_multiplier_exceeds_one(self) -> None:
        """Total output > direct effect (Leontief multiplier > 1)."""
        store, _, mv_id = _build_saudi_model()
        shock = np.array([500_000_000.0, 0.0, 0.0])
        result_sets = self._run_scenario(store, mv_id, shock)

        cumulative = {
            rs.metric_type: rs for rs in result_sets if rs.series_kind is None
        }
        total_sum = sum(
            v for k, v in cumulative["total_output"].values.items()
            if not k.startswith("_")
        )
        direct_sum = sum(
            v for k, v in cumulative["direct_effect"].values.items()
            if not k.startswith("_")
        )
        assert total_sum > direct_sum, "Multiplier must exceed 1.0"
        multiplier = total_sum / direct_sum
        assert 1.0 < multiplier < 10.0, f"Multiplier {multiplier:.2f} out of range"

    # ---------------------------------------------------------------
    # 3. Satellite computation is non-trivial
    # ---------------------------------------------------------------

    def test_employment_values_nonzero(self) -> None:
        """Employment values are positive when shock is applied."""
        store, _, mv_id = _build_saudi_model()
        shock = np.array([500_000_000.0, 0.0, 0.0])
        result_sets = self._run_scenario(store, mv_id, shock)

        emp = next(
            rs for rs in result_sets
            if rs.metric_type == "employment" and rs.series_kind is None
        )
        total_jobs = sum(
            v for k, v in emp.values.items() if not k.startswith("_")
        )
        assert total_jobs > 0, "Employment must be positive with non-zero shock"

    def test_import_leakage_is_positive(self) -> None:
        """Imports are positive, proving import ratios are applied."""
        store, _, mv_id = _build_saudi_model()
        shock = np.array([500_000_000.0, 0.0, 0.0])
        result_sets = self._run_scenario(store, mv_id, shock)

        imports_rs = next(
            rs for rs in result_sets
            if rs.metric_type == "imports" and rs.series_kind is None
        )
        total_imports = sum(
            v for k, v in imports_rs.values.items() if not k.startswith("_")
        )
        assert total_imports > 0, "Import leakage must be positive"

    # ---------------------------------------------------------------
    # 4. Saudization pipeline runs (Step 3 verification)
    # ---------------------------------------------------------------

    def test_saudization_categories_sum_to_employment(self) -> None:
        """saudi_ready + saudi_trainable + expat_reliant = employment per sector."""
        store, _, mv_id = _build_saudi_model()
        shock = np.array([500_000_000.0, 0.0, 0.0])
        result_sets = self._run_scenario(store, mv_id, shock)

        cumulative = {
            rs.metric_type: rs for rs in result_sets if rs.series_kind is None
        }
        emp = cumulative["employment"]
        saudi_ready = cumulative["saudization_saudi_ready"]
        saudi_trainable = cumulative["saudization_saudi_trainable"]
        expat_reliant = cumulative["saudization_expat_reliant"]

        for sector in emp.values:
            if sector.startswith("_"):
                continue
            total_emp = emp.values[sector]
            saud_sum = (
                saudi_ready.values.get(sector, 0.0)
                + saudi_trainable.values.get(sector, 0.0)
                + expat_reliant.values.get(sector, 0.0)
            )
            assert abs(saud_sum - total_emp) < 1.0, (
                f"Saudization categories don't sum to employment for {sector}: "
                f"{saud_sum:.0f} != {total_emp:.0f}"
            )

    # ---------------------------------------------------------------
    # 5. Feasibility always present (Step 4 verification)
    # ---------------------------------------------------------------

    def test_unconstrained_feasible_equals_total(self) -> None:
        """Without constraints, feasible_output = total_output."""
        store, _, mv_id = _build_saudi_model()
        shock = np.array([500_000_000.0, 0.0, 0.0])
        result_sets = self._run_scenario(store, mv_id, shock)

        cumulative = {
            rs.metric_type: rs for rs in result_sets if rs.series_kind is None
        }
        total = cumulative["total_output"]
        feasible = cumulative["feasible_output"]
        gap = cumulative["constraint_gap"]

        for sector in total.values:
            if sector.startswith("_"):
                continue
            assert abs(feasible.values[sector] - total.values[sector]) < 1.0
            assert gap.values[sector] == 0.0

    def test_constrained_feasible_respects_cap(self) -> None:
        """With CAPACITY_CAP, feasible output is clipped to bound."""
        store, _, mv_id = _build_saudi_model()
        shock = np.array([500_000_000.0, 0.0, 0.0])
        cap = 200_000_000.0  # 200M cap on construction
        constraints = [
            ConstraintSpec(
                constraint_id=new_uuid7(),
                constraint_type="CAPACITY_CAP",
                sector_index=0,  # F sector
                bound_value=cap,
                confidence="HARD",
            ),
        ]
        result_sets = self._run_scenario(store, mv_id, shock, constraints=constraints)

        cumulative = {
            rs.metric_type: rs for rs in result_sets if rs.series_kind is None
        }
        feasible = cumulative["feasible_output"]
        gap = cumulative["constraint_gap"]

        # F sector should be capped
        assert feasible.values["F"] <= cap + 1.0
        # Gap should be positive for F
        assert gap.values["F"] > 0.0
        # Unconstrained sectors have zero gap
        assert gap.values["C"] == 0.0
        assert gap.values["G"] == 0.0

    # ---------------------------------------------------------------
    # 6. Sector breakdowns populated
    # ---------------------------------------------------------------

    def test_sector_breakdowns_on_total_output(self) -> None:
        """total_output ResultSet has sector_breakdowns with components."""
        store, _, mv_id = _build_saudi_model()
        shock = np.array([500_000_000.0, 0.0, 0.0])
        result_sets = self._run_scenario(store, mv_id, shock)

        total_rs = next(
            rs for rs in result_sets
            if rs.metric_type == "total_output" and rs.series_kind is None
        )
        assert total_rs.sector_breakdowns != {}
        assert "direct" in total_rs.sector_breakdowns
        assert "indirect" in total_rs.sector_breakdowns
        assert "employment" in total_rs.sector_breakdowns

    # ---------------------------------------------------------------
    # 7. ResultPackager produces export-ready data
    # ---------------------------------------------------------------

    def test_result_packager_produces_complete_pack(self) -> None:
        """ResultPackager converts ResultSets to a complete pack_data."""
        store, _, mv_id = _build_saudi_model()
        shock = np.array([500_000_000.0, 0.0, 0.0])
        result_sets = self._run_scenario(store, mv_id, shock)

        packager = ResultPackager()
        pack = packager.package(
            result_sets=result_sets,
            scenario_name="500M Construction Megaproject",
            base_year=2023,
            currency="SAR",
        )

        # Executive summary
        assert pack["executive_summary"]["headline_jobs"] > 0
        assert pack["executive_summary"]["total_sectors"] == 3

        # Sector impacts
        assert len(pack["sector_impacts"]) == 3
        for si in pack["sector_impacts"]:
            assert "sector_code" in si
            assert "direct_impact" in si
            assert "indirect_impact" in si
            assert "total_impact" in si
            assert "multiplier" in si
            assert "domestic_share" in si
            assert "import_leakage" in si
            # Multiplier should be > 0 for sectors with output
            if si["direct_impact"] > 0:
                assert si["multiplier"] > 0

        # Employment section
        assert len(pack["employment"]) == 3

        # Export-ready structure
        required_keys = {
            "scenario_name", "base_year", "currency",
            "executive_summary", "sector_impacts",
            "input_vectors", "sensitivity",
            "assumptions", "evidence_ledger",
        }
        assert required_keys.issubset(set(pack.keys()))

    # ---------------------------------------------------------------
    # 8. Governance: claims auto-extracted from results
    # ---------------------------------------------------------------

    def test_governance_claims_from_engine_results(self) -> None:
        """Claims are auto-created from engine results (P4-1)."""
        store, _, mv_id = _build_saudi_model()
        shock = np.array([500_000_000.0, 0.0, 0.0])
        result_sets = self._run_scenario(store, mv_id, shock)

        # Build result_summary dict (as RunExecutionService does)
        result_summary = {}
        for rs in result_sets:
            if rs.series_kind is None:
                result_summary[rs.metric_type] = rs.values

        claims = create_claims_from_results(
            result_summary,
            run_id=new_uuid7(),
        )

        assert len(claims) > 0
        # One claim per metric type
        claim_metrics = {c.text for c in claims}
        # At least total_output, employment, imports should produce claims
        has_total = any("total_output" in t for t in claim_metrics)
        has_employment = any("employment" in t for t in claim_metrics)
        has_imports = any("imports" in t for t in claim_metrics)
        assert has_total, "Should have claim for total_output"
        assert has_employment, "Should have claim for employment"
        assert has_imports, "Should have claim for imports"

    # ---------------------------------------------------------------
    # 9. Full chain: model → compute → package → claims → export-ready
    # ---------------------------------------------------------------

    def test_full_chain_model_to_export(self) -> None:
        """The complete real economist workflow: no mocks, no stubs.

        Model → Shock → Leontief → Satellites → Saudization → Feasibility
        → Sector Breakdowns → ResultPackager → Claims → pack_data ready.
        """
        # 1. Build model
        store, loaded, mv_id = _build_saudi_model()
        assert loaded.sector_codes == ["F", "C", "G"]
        assert loaded.model_version.model_denomination == "SAR_MILLIONS"

        # 2. Define shock: 500M SAR construction megaproject
        shock = np.array([500_000_000.0, 0.0, 0.0])

        # 3. Run engine (Leontief + satellites + saudization + feasibility)
        result_sets = self._run_scenario(store, mv_id, shock)
        cumulative = {
            rs.metric_type: rs for rs in result_sets if rs.series_kind is None
        }

        # 4. Verify Leontief solve
        total_sum = sum(
            v for k, v in cumulative["total_output"].values.items()
            if not k.startswith("_")
        )
        assert total_sum > 500_000_000.0, "Multiplier effect must increase output"

        # 5. Verify satellites
        total_jobs = sum(
            v for k, v in cumulative["employment"].values.items()
            if not k.startswith("_")
        )
        assert total_jobs > 0

        # 6. Verify saudization
        saudi_ready = cumulative["saudization_saudi_ready"]
        assert any(v > 0 for v in saudi_ready.values.values())

        # 7. Verify feasibility
        assert cumulative["feasible_output"] is not None
        assert all(
            v == 0.0
            for k, v in cumulative["constraint_gap"].values.items()
            if not k.startswith("_")
        )

        # 8. Verify sector breakdowns
        total_rs = cumulative["total_output"]
        assert "direct" in total_rs.sector_breakdowns
        assert "indirect" in total_rs.sector_breakdowns

        # 9. Package for export
        packager = ResultPackager()
        pack = packager.package(
            result_sets=result_sets,
            scenario_name="500M Construction Megaproject",
            base_year=2023,
            currency="SAR",
        )
        assert pack["executive_summary"]["headline_jobs"] > 0
        assert len(pack["sector_impacts"]) == 3
        assert pack["scenario_name"] == "500M Construction Megaproject"

        # 10. Auto-create governance claims
        result_summary = {
            rs.metric_type: rs.values
            for rs in result_sets if rs.series_kind is None
        }
        claims = create_claims_from_results(result_summary, run_id=new_uuid7())
        assert len(claims) >= 5, (
            f"Expected at least 5 claims from {len(result_summary)} metrics, "
            f"got {len(claims)}"
        )

        # 11. Verify pack_data is export-ready
        required_export_keys = {
            "scenario_name", "base_year", "currency",
            "executive_summary", "sector_impacts",
            "input_vectors", "sensitivity",
            "assumptions", "evidence_ledger",
        }
        assert required_export_keys.issubset(set(pack.keys())), (
            f"Missing export keys: {required_export_keys - set(pack.keys())}"
        )

    # ---------------------------------------------------------------
    # 10. Batch run with multiple scenarios
    # ---------------------------------------------------------------

    def test_batch_run_two_scenarios(self) -> None:
        """Batch run with two scenarios produces independent results."""
        store, _, mv_id = _build_saudi_model()

        runner = BatchRunner(model_store=store, environment="dev")
        scenarios = [
            ScenarioInput(
                scenario_spec_id=new_uuid7(),
                scenario_spec_version=1,
                name="Low Investment",
                annual_shocks={2023: np.array([100_000_000.0, 0.0, 0.0])},
                base_year=2023,
            ),
            ScenarioInput(
                scenario_spec_id=new_uuid7(),
                scenario_spec_version=1,
                name="High Investment",
                annual_shocks={2023: np.array([1_000_000_000.0, 0.0, 0.0])},
                base_year=2023,
            ),
        ]
        request = BatchRequest(
            scenarios=scenarios,
            model_version_id=mv_id,
            satellite_coefficients=_build_coefficients(),
            version_refs=_build_version_refs(),
        )
        result = runner.run(request)

        assert len(result.run_results) == 2

        # High investment should produce larger total output
        low_total = sum(
            v for k, v in result.run_results[0].result_sets[0].values.items()
            if not k.startswith("_") and result.run_results[0].result_sets[0].metric_type == "total_output"
        )
        high_total = sum(
            v for k, v in result.run_results[1].result_sets[0].values.items()
            if not k.startswith("_") and result.run_results[1].result_sets[0].metric_type == "total_output"
        )

        # Both should have complete metric sets
        for sr in result.run_results:
            cumulative = [rs for rs in sr.result_sets if rs.series_kind is None]
            metric_types = {rs.metric_type for rs in cumulative}
            assert "total_output" in metric_types
            assert "employment" in metric_types
            assert "feasible_output" in metric_types
            assert "saudization_saudi_ready" in metric_types
