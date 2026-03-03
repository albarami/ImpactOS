"""Batch runner — MVP-3 Section 7.6.

Executes multiple scenarios (50+) with optional sensitivity variants,
produces immutable ResultSet per run, generates RunSnapshot capturing
all version refs for reproducibility.

Pure deterministic — no LLM calls, no side effects.
"""

from dataclasses import dataclass
from uuid import UUID

import numpy as np

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import LoadedModel, ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
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

        # Total output
        result_sets.append(ResultSet(
            run_id=run_id,
            metric_type="total_output",
            values=self._vec_to_dict(phased.cumulative_delta_x, sector_codes),
        ))

        # Direct effect (sum of annual directs)
        cumulative_direct = np.zeros(loaded.n)
        cumulative_indirect = np.zeros(loaded.n)
        for year_result in phased.annual_results.values():
            cumulative_direct += year_result.delta_x_direct
            cumulative_indirect += year_result.delta_x_indirect

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
