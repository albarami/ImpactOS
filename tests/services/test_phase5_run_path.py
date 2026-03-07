"""Phase 5 tests: Main Run Path Completeness.

P5-1: Sector breakdowns populated in ResultSet
P5-2: Workforce satellite on both run paths (consistent)
P5-3: Feasibility layer integrated in BatchRunner (optional)
P5-4: ResultPackager assembles DecisionPack input from ResultSets
"""

from uuid import UUID

import numpy as np
from uuid_extensions import uuid7

from src.engine.batch import BatchRequest, BatchRunner, ScenarioInput
from src.engine.feasibility import ConstraintSpec
from src.engine.model_store import LoadedModel, ModelStore
from src.engine.satellites import SatelliteCoefficients
from src.export.result_packager import ResultPackager
from src.models.common import new_uuid7
from src.models.model_version import ModelVersion
from src.models.run import ResultSet


# ===================================================================
# Shared test fixtures
# ===================================================================


def _make_3sector_model(store: ModelStore) -> tuple[LoadedModel, UUID]:
    """Create a minimal 3-sector model for testing."""
    n = 3
    mv = ModelVersion(
        model_version_id=new_uuid7(),
        base_year=2023,
        source="test",
        sector_count=n,
        checksum="sha256:" + "a" * 64,
    )
    Z = np.array([
        [0.0, 100.0, 50.0],
        [80.0, 0.0, 60.0],
        [40.0, 70.0, 0.0],
    ], dtype=np.float64)
    x = np.array([1000.0, 1000.0, 1000.0], dtype=np.float64)
    loaded = LoadedModel(
        model_version=mv,
        Z=Z,
        x=x,
        sector_codes=["SEC01", "SEC02", "SEC03"],
    )
    store.cache_prevalidated(loaded)
    return loaded, mv.model_version_id


def _make_coefficients(n: int = 3) -> SatelliteCoefficients:
    return SatelliteCoefficients(
        jobs_coeff=np.full(n, 10.0),
        import_ratio=np.full(n, 0.3),
        va_ratio=np.full(n, 0.5),
        version_id=new_uuid7(),
    )


def _make_version_refs() -> dict[str, UUID]:
    return {
        "taxonomy_version_id": new_uuid7(),
        "concordance_version_id": new_uuid7(),
        "mapping_library_version_id": new_uuid7(),
        "assumption_library_version_id": new_uuid7(),
        "prompt_pack_version_id": new_uuid7(),
    }


def _run_basic_scenario(store: ModelStore, model_version_id: UUID) -> list[ResultSet]:
    """Run a basic scenario and return result sets."""
    runner = BatchRunner(model_store=store, environment="dev")
    shock = np.array([1_000_000.0, 0.0, 0.0])
    scenario = ScenarioInput(
        scenario_spec_id=new_uuid7(),
        scenario_spec_version=1,
        name="Test",
        annual_shocks={2023: shock},
        base_year=2023,
    )
    request = BatchRequest(
        scenarios=[scenario],
        model_version_id=model_version_id,
        satellite_coefficients=_make_coefficients(),
        version_refs=_make_version_refs(),
    )
    result = runner.run(request)
    return result.run_results[0].result_sets


# ===================================================================
# P5-1: Sector breakdowns populated on total_output ResultSet
# ===================================================================


class TestSectorBreakdowns:
    """P5-1: total_output ResultSet has sector_breakdowns with components."""

    def test_total_output_has_sector_breakdowns(self) -> None:
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        # Find cumulative total_output (no series_kind)
        total_output = [
            rs for rs in result_sets
            if rs.metric_type == "total_output" and rs.series_kind is None
        ]
        assert len(total_output) == 1
        rs = total_output[0]
        assert rs.sector_breakdowns != {}

    def test_sector_breakdowns_has_direct_and_indirect(self) -> None:
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        rs = next(
            r for r in result_sets
            if r.metric_type == "total_output" and r.series_kind is None
        )
        assert "direct" in rs.sector_breakdowns
        assert "indirect" in rs.sector_breakdowns

    def test_sector_breakdowns_has_employment(self) -> None:
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        rs = next(
            r for r in result_sets
            if r.metric_type == "total_output" and r.series_kind is None
        )
        assert "employment" in rs.sector_breakdowns

    def test_sector_breakdowns_sectors_match_values(self) -> None:
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        rs = next(
            r for r in result_sets
            if r.metric_type == "total_output" and r.series_kind is None
        )
        # All breakdown keys should have the same sector codes as values
        for breakdown_type, breakdown_dict in rs.sector_breakdowns.items():
            assert set(breakdown_dict.keys()) == set(rs.values.keys()), (
                f"sector mismatch in {breakdown_type}"
            )

    def test_direct_plus_indirect_equals_total(self) -> None:
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        rs = next(
            r for r in result_sets
            if r.metric_type == "total_output" and r.series_kind is None
        )
        for sector in rs.values:
            direct = rs.sector_breakdowns["direct"][sector]
            indirect = rs.sector_breakdowns["indirect"][sector]
            total = rs.values[sector]
            assert abs(direct + indirect - total) < 1.0, (
                f"direct + indirect != total for {sector}: "
                f"{direct} + {indirect} != {total}"
            )


# ===================================================================
# P5-4: ResultPackager builds DecisionPack input from ResultSets
# ===================================================================


class TestResultPackager:
    """P5-4: ResultPackager converts ResultSet rows to DecisionPack format."""

    def test_builds_sector_impacts(self) -> None:
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        packager = ResultPackager()
        pack = packager.package(
            result_sets=result_sets,
            scenario_name="Test Scenario",
            base_year=2023,
        )
        assert "sector_impacts" in pack
        assert len(pack["sector_impacts"]) == 3  # 3 sectors

    def test_sector_impact_has_required_fields(self) -> None:
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        packager = ResultPackager()
        pack = packager.package(
            result_sets=result_sets,
            scenario_name="Test",
            base_year=2023,
        )
        for si in pack["sector_impacts"]:
            assert "sector_code" in si
            assert "direct_impact" in si
            assert "indirect_impact" in si
            assert "total_impact" in si
            assert "multiplier" in si
            assert "domestic_share" in si
            assert "import_leakage" in si

    def test_executive_summary_present(self) -> None:
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        packager = ResultPackager()
        pack = packager.package(
            result_sets=result_sets,
            scenario_name="Test",
            base_year=2023,
        )
        assert "executive_summary" in pack
        assert "headline_gdp" in pack["executive_summary"]
        assert "headline_jobs" in pack["executive_summary"]

    def test_employment_section_present(self) -> None:
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        packager = ResultPackager()
        pack = packager.package(
            result_sets=result_sets,
            scenario_name="Test",
            base_year=2023,
        )
        assert "employment" in pack
        # Employment should have sector-level data
        assert len(pack["employment"]) > 0

    def test_empty_result_sets_produces_empty_pack(self) -> None:
        packager = ResultPackager()
        pack = packager.package(
            result_sets=[],
            scenario_name="Empty",
            base_year=2023,
        )
        assert pack["sector_impacts"] == []
        assert pack["executive_summary"]["headline_gdp"] == 0.0
        assert pack["executive_summary"]["headline_jobs"] == 0

    def test_pack_data_suitable_for_export(self) -> None:
        """Pack output should be usable as pack_data for ExportRequest."""
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        packager = ResultPackager()
        pack = packager.package(
            result_sets=result_sets,
            scenario_name="Test",
            base_year=2023,
        )
        # Verify all required keys for export orchestrator
        required_keys = {
            "scenario_name", "base_year", "currency",
            "executive_summary", "sector_impacts",
            "input_vectors", "sensitivity",
            "assumptions", "evidence_ledger",
        }
        assert required_keys.issubset(set(pack.keys()))


# ===================================================================
# P5-2: Workforce satellite auto-loaded when not in request body
# ===================================================================


class TestWorkforceAutoLoad:
    """P5-2: API path supports optional satellite coefficients (auto-load)."""

    def test_run_request_accepts_optional_satellites(self) -> None:
        """RunRequest should work without satellite_coefficients."""
        from src.api.runs import RunRequest

        req = RunRequest(
            model_version_id="00000000-0000-0000-0000-000000000001",
            annual_shocks={"2023": [100.0, 200.0, 300.0]},
            base_year=2023,
            # No satellite_coefficients provided
        )
        assert req.satellite_coefficients is None

    def test_batch_run_request_accepts_optional_satellites(self) -> None:
        """BatchRunRequest should work without satellite_coefficients."""
        from src.api.runs import BatchRunRequest

        req = BatchRunRequest(
            model_version_id="00000000-0000-0000-0000-000000000001",
            scenarios=[],
            # No satellite_coefficients provided
        )
        assert req.satellite_coefficients is None

    def test_employment_result_always_produced(self) -> None:
        """Engine run produces employment ResultSet with curated coefficients.

        Verifies the run pipeline always emits employment (workforce) results
        regardless of how satellite coefficients are provided.
        """
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        employment_rs = [
            rs for rs in result_sets
            if rs.metric_type == "employment" and rs.series_kind is None
        ]
        assert len(employment_rs) == 1
        # Employment values should be non-zero (real workforce computation)
        emp = employment_rs[0]
        assert any(v != 0.0 for v in emp.values.values())


# ===================================================================
# P5-3: Feasibility solver integrated in BatchRunner (optional)
# ===================================================================


class TestFeasibilityIntegration:
    """P5-3: ClippingSolver runs within BatchRunner when constraints provided."""

    def test_no_constraints_feasibility_equals_unconstrained(self) -> None:
        """Without constraints, feasible_output equals total_output (P5-3 fix)."""
        store = ModelStore()
        _, mv_id = _make_3sector_model(store)
        result_sets = _run_basic_scenario(store, mv_id)

        feasible_rs = [
            rs for rs in result_sets
            if rs.metric_type == "feasible_output"
        ]
        assert len(feasible_rs) == 1  # Always present now

        gap_rs = [
            rs for rs in result_sets
            if rs.metric_type == "constraint_gap"
        ]
        assert len(gap_rs) == 1
        # Gap should be zero without constraints
        assert all(v == 0.0 for v in gap_rs[0].values.values())

    def test_capacity_cap_produces_feasible_output(self) -> None:
        """With CAPACITY_CAP, feasible_output ResultSet is emitted."""
        store = ModelStore()
        loaded, mv_id = _make_3sector_model(store)

        # Cap sector 0 at 500_000 (shock is 1M → should bind)
        constraints = [
            ConstraintSpec(
                constraint_id=new_uuid7(),
                constraint_type="CAPACITY_CAP",
                sector_index=0,
                bound_value=500_000.0,
                confidence="HARD",
            ),
        ]

        runner = BatchRunner(model_store=store, environment="dev")
        shock = np.array([1_000_000.0, 0.0, 0.0])
        scenario = ScenarioInput(
            scenario_spec_id=new_uuid7(),
            scenario_spec_version=1,
            name="Constrained",
            annual_shocks={2023: shock},
            base_year=2023,
        )
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=mv_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
            constraints=constraints,
        )
        result = runner.run(request)
        result_sets = result.run_results[0].result_sets

        feasible_rs = [
            rs for rs in result_sets
            if rs.metric_type == "feasible_output" and rs.series_kind is None
        ]
        assert len(feasible_rs) == 1

        # Feasible output for SEC01 should respect the 500_000 cap
        frs = feasible_rs[0]
        assert frs.values["SEC01"] <= 500_000.0 + 1.0  # small tolerance

    def test_constraint_gap_emitted(self) -> None:
        """Constraint gap ResultSet shows unconstrained - feasible."""
        store = ModelStore()
        loaded, mv_id = _make_3sector_model(store)

        constraints = [
            ConstraintSpec(
                constraint_id=new_uuid7(),
                constraint_type="CAPACITY_CAP",
                sector_index=0,
                bound_value=500_000.0,
                confidence="HARD",
            ),
        ]

        runner = BatchRunner(model_store=store, environment="dev")
        shock = np.array([1_000_000.0, 0.0, 0.0])
        scenario = ScenarioInput(
            scenario_spec_id=new_uuid7(),
            scenario_spec_version=1,
            name="Constrained",
            annual_shocks={2023: shock},
            base_year=2023,
        )
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=mv_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
            constraints=constraints,
        )
        result = runner.run(request)
        result_sets = result.run_results[0].result_sets

        gap_rs = [
            rs for rs in result_sets
            if rs.metric_type == "constraint_gap" and rs.series_kind is None
        ]
        assert len(gap_rs) == 1

        # Gap for SEC01 should be > 0 (constraint is binding)
        grs = gap_rs[0]
        assert grs.values["SEC01"] > 0.0

    def test_unconstrained_sectors_zero_gap(self) -> None:
        """Sectors without constraints have zero gap."""
        store = ModelStore()
        loaded, mv_id = _make_3sector_model(store)

        # Only constrain sector 0
        constraints = [
            ConstraintSpec(
                constraint_id=new_uuid7(),
                constraint_type="CAPACITY_CAP",
                sector_index=0,
                bound_value=500_000.0,
                confidence="HARD",
            ),
        ]

        runner = BatchRunner(model_store=store, environment="dev")
        shock = np.array([1_000_000.0, 0.0, 0.0])
        scenario = ScenarioInput(
            scenario_spec_id=new_uuid7(),
            scenario_spec_version=1,
            name="Constrained",
            annual_shocks={2023: shock},
            base_year=2023,
        )
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=mv_id,
            satellite_coefficients=_make_coefficients(),
            version_refs=_make_version_refs(),
            constraints=constraints,
        )
        result = runner.run(request)
        result_sets = result.run_results[0].result_sets

        gap_rs = next(
            rs for rs in result_sets
            if rs.metric_type == "constraint_gap" and rs.series_kind is None
        )

        # SEC02 and SEC03 have no sector-level constraints → 0 gap
        # (CAPACITY_CAP only applies to sector_index=0, not cross-sector)
        assert gap_rs.values["SEC02"] == 0.0
        assert gap_rs.values["SEC03"] == 0.0
