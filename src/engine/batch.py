"""Batch runner — MVP-3 Section 7.6.

Executes multiple scenarios (50+) with optional sensitivity variants,
produces immutable ResultSet per run, generates RunSnapshot capturing
all version refs for reproducibility.

Pure deterministic — no LLM calls, no side effects.
"""

from dataclasses import dataclass
from uuid import UUID

import numpy as np

from src.engine.feasibility import ClippingSolver, ConstraintSpec
from src.engine.leontief import LeontiefSolver
from src.engine.model_store import LoadedModel, ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.engine.value_measures import ValueMeasuresComputer
from src.engine.value_measures_validation import ValueMeasuresValidationError
from src.models.common import new_uuid7
from src.models.run import ResultSet, RunSnapshot


@dataclass
class ScenarioInput:
    """Input definition for a single scenario."""

    scenario_spec_id: UUID
    scenario_spec_version: int
    name: str
    annual_shocks: dict[int, np.ndarray]
    base_year: int
    deflators: dict[int, float] | None = None
    sensitivity_multipliers: list[float] | None = None
    # Sprint 17: delta series fields
    baseline_run_id: UUID | None = None
    baseline_annual_data: dict[int, dict[str, dict[str, float]]] | None = None


@dataclass(frozen=True)
class SingleRunResult:
    """Result of a single scenario (or sensitivity variant) run.

    Amendment 7: optional quality_assessment_id links to the
    RunQualityAssessment produced by the quality automation pipeline.
    """

    snapshot: RunSnapshot
    result_sets: list[ResultSet]
    quality_assessment_id: UUID | None = None


@dataclass(frozen=True)
class BatchResult:
    """Result of an entire batch run."""

    run_results: list[SingleRunResult]


@dataclass
class BatchRequest:
    """Input for a batch run: scenarios + model + coefficients + version refs."""

    scenarios: list[ScenarioInput]
    model_version_id: UUID
    satellite_coefficients: SatelliteCoefficients
    version_refs: dict[str, UUID]
    constraints: list[ConstraintSpec] | None = None  # P5-3: optional feasibility constraints


class BatchRunner:
    """Executes batch scenarios through the deterministic engine pipeline."""

    def __init__(self, model_store: ModelStore, environment: str = "dev") -> None:
        self._store = model_store
        self._solver = LeontiefSolver()
        self._satellites = SatelliteAccounts()
        self._environment = environment

    def run(self, request: BatchRequest) -> BatchResult:
        """Execute all scenarios in the batch request.

        For each scenario, if sensitivity_multipliers are provided,
        runs one variant per multiplier. Otherwise runs once.

        Returns:
            BatchResult with one SingleRunResult per scenario (or variant).
        """
        loaded = self._store.get(request.model_version_id)
        results: list[SingleRunResult] = []

        for scenario in request.scenarios:
            multipliers = scenario.sensitivity_multipliers or [1.0]
            for multiplier in multipliers:
                run_result = self._execute_single(
                    loaded=loaded,
                    scenario=scenario,
                    multiplier=multiplier,
                    coefficients=request.satellite_coefficients,
                    version_refs=request.version_refs,
                    constraints=request.constraints,
                )
                results.append(run_result)

        return BatchResult(run_results=results)

    def _execute_single(
        self,
        *,
        loaded: LoadedModel,
        scenario: ScenarioInput,
        multiplier: float,
        coefficients: SatelliteCoefficients,
        version_refs: dict[str, UUID],
        constraints: list[ConstraintSpec] | None = None,
    ) -> SingleRunResult:
        """Execute a single scenario at a given sensitivity multiplier."""
        run_id = new_uuid7()
        sector_codes = loaded.sector_codes

        # Scale shocks by multiplier
        scaled_shocks: dict[int, np.ndarray] = {
            year: shock * multiplier
            for year, shock in scenario.annual_shocks.items()
        }

        # Solve phased Leontief
        phased = self._solver.solve_phased(
            loaded_model=loaded,
            annual_shocks=scaled_shocks,
            base_year=scenario.base_year,
            deflators=scenario.deflators,
        )

        # Compute satellite impacts on cumulative output
        sat_result = self._satellites.compute(
            delta_x=phased.cumulative_delta_x,
            coefficients=coefficients,
        )

        # Build result sets
        result_sets: list[ResultSet] = []

        # Direct effect (sum of annual directs)
        cumulative_direct = np.zeros(loaded.n)
        cumulative_indirect = np.zeros(loaded.n)
        for year_result in phased.annual_results.values():
            cumulative_direct += year_result.delta_x_direct
            cumulative_indirect += year_result.delta_x_indirect

        # P5-1: Build sector_breakdowns for total_output (direct, indirect,
        # employment, imports, value_added per sector)
        sector_breakdowns: dict[str, dict[str, float]] = {
            "direct": self._vec_to_dict(cumulative_direct, sector_codes),
            "indirect": self._vec_to_dict(cumulative_indirect, sector_codes),
            "employment": self._vec_to_dict(sat_result.delta_jobs, sector_codes),
            "imports": self._vec_to_dict(sat_result.delta_imports, sector_codes),
            "value_added": self._vec_to_dict(sat_result.delta_va, sector_codes),
            "domestic_output": self._vec_to_dict(sat_result.delta_domestic_output, sector_codes),
        }

        # Total output (with sector breakdowns)
        result_sets.append(ResultSet(
            run_id=run_id,
            metric_type="total_output",
            values=self._vec_to_dict(phased.cumulative_delta_x, sector_codes),
            sector_breakdowns=sector_breakdowns,
        ))

        result_sets.append(ResultSet(
            run_id=run_id,
            metric_type="direct_effect",
            values=self._vec_to_dict(cumulative_direct, sector_codes),
        ))

        result_sets.append(ResultSet(
            run_id=run_id,
            metric_type="indirect_effect",
            values=self._vec_to_dict(cumulative_indirect, sector_codes),
        ))

        # Sprint 17: Emit annual series rows
        for year in sorted(phased.annual_results):
            year_result = phased.annual_results[year]
            result_sets.append(ResultSet(
                run_id=run_id,
                metric_type="total_output",
                values=self._vec_to_dict(year_result.delta_x_total, sector_codes),
                year=year,
                series_kind="annual",
            ))
            result_sets.append(ResultSet(
                run_id=run_id,
                metric_type="direct_effect",
                values=self._vec_to_dict(year_result.delta_x_direct, sector_codes),
                year=year,
                series_kind="annual",
            ))
            result_sets.append(ResultSet(
                run_id=run_id,
                metric_type="indirect_effect",
                values=self._vec_to_dict(year_result.delta_x_indirect, sector_codes),
                year=year,
                series_kind="annual",
            ))

        # Sprint 17: Peak-year row
        result_sets.append(ResultSet(
            run_id=run_id,
            metric_type="total_output",
            values=self._vec_to_dict(phased.peak_delta_x, sector_codes),
            year=phased.peak_year,
            series_kind="peak",
        ))

        # Sprint 17: Delta series (when baseline provided)
        if scenario.baseline_run_id is not None and scenario.baseline_annual_data is not None:
            from src.engine.runseries_delta import compute_delta_series
            # Extract scenario annual data from just-emitted annual rows
            scenario_annual_data: dict[int, dict[str, dict[str, float]]] = {}
            for rs in result_sets:
                if rs.series_kind == "annual" and rs.year is not None:
                    scenario_annual_data.setdefault(rs.year, {})[rs.metric_type] = dict(rs.values)

            delta_data = compute_delta_series(scenario_annual_data, scenario.baseline_annual_data)
            for year, metrics in sorted(delta_data.items()):
                for metric_type, values in sorted(metrics.items()):
                    result_sets.append(ResultSet(
                        run_id=run_id,
                        metric_type=metric_type,
                        values=values,
                        year=year,
                        series_kind="delta",
                        baseline_run_id=scenario.baseline_run_id,
                    ))

        # Satellite results
        result_sets.append(ResultSet(
            run_id=run_id,
            metric_type="employment",
            values=self._vec_to_dict(sat_result.delta_jobs, sector_codes),
        ))

        result_sets.append(ResultSet(
            run_id=run_id,
            metric_type="imports",
            values=self._vec_to_dict(sat_result.delta_imports, sector_codes),
        ))

        result_sets.append(ResultSet(
            run_id=run_id,
            metric_type="value_added",
            values=self._vec_to_dict(sat_result.delta_va, sector_codes),
        ))

        result_sets.append(ResultSet(
            run_id=run_id,
            metric_type="domestic_output",
            values=self._vec_to_dict(sat_result.delta_domestic_output, sector_codes),
        ))

        # Value measures (fail-closed in non-dev: always attempt validation)
        _attempt_vm = (
            loaded.has_value_measures_prerequisites
            or self._environment in ("staging", "prod")
        )
        if _attempt_vm:
            try:
                vm_computer = ValueMeasuresComputer()
                vm_result = vm_computer.compute(
                    delta_x=phased.cumulative_delta_x,
                    sat_result=sat_result,
                    loaded_model=loaded,
                    base_year=scenario.base_year,
                )

                # GDP at basic price (per-sector + aggregate)
                gdp_basic_vals = self._vec_to_dict(
                    vm_result.gdp_basic_by_sector, sector_codes,
                )
                gdp_basic_vals["_total"] = vm_result.gdp_basic_price
                result_sets.append(ResultSet(
                    run_id=run_id,
                    metric_type="gdp_basic_price",
                    values=gdp_basic_vals,
                ))

                # GDP at market price
                gdp_market_by_sector = (
                    vm_result.gdp_basic_by_sector
                    + vm_result.tax_effect_by_sector
                )
                gdp_market_vals = self._vec_to_dict(
                    gdp_market_by_sector, sector_codes,
                )
                gdp_market_vals["_total"] = vm_result.gdp_market_price
                result_sets.append(ResultSet(
                    run_id=run_id,
                    metric_type="gdp_market_price",
                    values=gdp_market_vals,
                ))

                # GDP real (scalar only)
                result_sets.append(ResultSet(
                    run_id=run_id,
                    metric_type="gdp_real",
                    values={"_total": vm_result.gdp_real},
                ))

                # GDP intensity (scalar only)
                result_sets.append(ResultSet(
                    run_id=run_id,
                    metric_type="gdp_intensity",
                    values={"_total": vm_result.gdp_intensity},
                ))

                # Balance of trade (per-sector + aggregate)
                bot_by_sector = (
                    vm_result.export_effect_by_sector
                    - sat_result.delta_imports
                )
                bot_vals = self._vec_to_dict(bot_by_sector, sector_codes)
                bot_vals["_total"] = vm_result.balance_of_trade
                result_sets.append(ResultSet(
                    run_id=run_id,
                    metric_type="balance_of_trade",
                    values=bot_vals,
                ))

                # Non-oil exports (scalar)
                result_sets.append(ResultSet(
                    run_id=run_id,
                    metric_type="non_oil_exports",
                    values={"_total": vm_result.non_oil_exports},
                ))

                # Government non-oil revenue (scalar)
                result_sets.append(ResultSet(
                    run_id=run_id,
                    metric_type="government_non_oil_revenue",
                    values={"_total": vm_result.government_non_oil_revenue},
                ))

                # Government revenue/spending ratio (scalar)
                result_sets.append(ResultSet(
                    run_id=run_id,
                    metric_type="government_revenue_spending_ratio",
                    values={"_total": vm_result.government_revenue_spending_ratio},
                ))

            except ValueMeasuresValidationError:
                if self._environment in ("staging", "prod"):
                    raise  # fail-closed in non-dev
                import logging
                logging.getLogger(__name__).warning(
                    "Value measures validation failed in dev — "
                    "continuing without value measures"
                )

        # Type II induced effects (when model has prerequisites)
        if loaded.has_type_ii_prerequisites:
            from src.engine.type_ii_validation import (
                TypeIIValidationError,
                validate_type_ii_prerequisites,
            )
            try:
                validate_type_ii_prerequisites(
                    n=loaded.n,
                    x=loaded.x,
                    compensation_of_employees=loaded.compensation_of_employees_array,
                    household_consumption_shares=loaded.household_consumption_shares_array,
                )
                # Compute Type II phased solve
                phased_type_ii = self._solver.solve_phased(
                    loaded_model=loaded,
                    annual_shocks=scaled_shocks,
                    base_year=scenario.base_year,
                    deflators=scenario.deflators,
                    compensation_of_employees=loaded.compensation_of_employees_array,
                    household_consumption_shares=loaded.household_consumption_shares_array,
                )
                # Type II total output
                type_ii_vals = self._vec_to_dict(
                    phased_type_ii.cumulative_delta_x_type_ii, sector_codes,
                )
                result_sets.append(ResultSet(
                    run_id=run_id,
                    metric_type="type_ii_total_output",
                    values=type_ii_vals,
                ))
                # Induced effect
                induced_vals = self._vec_to_dict(
                    phased_type_ii.cumulative_delta_x_induced, sector_codes,
                )
                result_sets.append(ResultSet(
                    run_id=run_id,
                    metric_type="induced_effect",
                    values=induced_vals,
                ))
                # Type II employment satellite
                type_ii_jobs = coefficients.jobs_coeff * phased_type_ii.cumulative_delta_x_type_ii
                result_sets.append(ResultSet(
                    run_id=run_id,
                    metric_type="type_ii_employment",
                    values=self._vec_to_dict(type_ii_jobs, sector_codes),
                ))
            except TypeIIValidationError:
                if self._environment in ("staging", "prod"):
                    raise  # fail-closed in non-dev
                import logging
                logging.getLogger(__name__).warning(
                    "Type II validation failed in dev -- continuing with Type I only"
                )

        # P5-3: Optional feasibility solve after unconstrained computation
        if constraints:
            feasibility_solver = ClippingSolver()
            feas_result = feasibility_solver.solve(
                unconstrained_delta_x=phased.cumulative_delta_x,
                constraints=constraints,
                satellite_coefficients=coefficients,
                sector_codes=sector_codes,
            )

            # Emit feasible_output ResultSet
            result_sets.append(ResultSet(
                run_id=run_id,
                metric_type="feasible_output",
                values=self._vec_to_dict(
                    feas_result.feasible_delta_x, sector_codes,
                ),
            ))

            # Emit constraint_gap ResultSet (unconstrained - feasible, >= 0)
            result_sets.append(ResultSet(
                run_id=run_id,
                metric_type="constraint_gap",
                values=self._vec_to_dict(
                    feas_result.gap_per_sector, sector_codes,
                ),
            ))

        # Build RunSnapshot
        snapshot = RunSnapshot(
            run_id=run_id,
            model_version_id=loaded.model_version.model_version_id,
            taxonomy_version_id=version_refs["taxonomy_version_id"],
            concordance_version_id=version_refs["concordance_version_id"],
            mapping_library_version_id=version_refs["mapping_library_version_id"],
            assumption_library_version_id=version_refs["assumption_library_version_id"],
            prompt_pack_version_id=version_refs["prompt_pack_version_id"],
        )

        return SingleRunResult(snapshot=snapshot, result_sets=result_sets)

    @staticmethod
    def _vec_to_dict(vec: np.ndarray, sector_codes: list[str]) -> dict[str, float]:
        """Convert a numpy vector to a sector-code-keyed dict."""
        return {code: float(vec[i]) for i, code in enumerate(sector_codes)}
