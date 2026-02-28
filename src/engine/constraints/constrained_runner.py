"""Constrained runner — wraps existing engine pipeline with feasibility.

Pipeline:
1. LeontiefSolver.solve() → unconstrained delta_x
2. SatelliteAccounts.compute() → unconstrained satellite impacts
3. FeasibilitySolver.solve() → feasible delta_x + diagnostics
4. SatelliteAccounts.compute() → feasible satellite impacts
5. Package both into FeasibilityResult

This is DETERMINISTIC — no LLM calls.
"""

import numpy as np

from src.engine.constraints.schema import ConstraintSet
from src.engine.constraints.solver import FeasibilityResult, FeasibilitySolver
from src.engine.leontief import LeontiefSolver
from src.engine.model_store import LoadedModel
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients


class ConstrainedRunner:
    """Wraps the existing engine pipeline with feasibility analysis.

    Computes unconstrained IO results via LeontiefSolver, then applies
    constraints via FeasibilitySolver. Both results are preserved.
    """

    def __init__(
        self,
        leontief_solver: LeontiefSolver | None = None,
        satellite_accounts: SatelliteAccounts | None = None,
        feasibility_solver: FeasibilitySolver | None = None,
    ) -> None:
        self._leontief = leontief_solver or LeontiefSolver()
        self._satellites = satellite_accounts or SatelliteAccounts()
        self._feasibility = feasibility_solver or FeasibilitySolver()

    def run(
        self,
        *,
        loaded_model: LoadedModel,
        delta_d: np.ndarray,
        satellite_coefficients: SatelliteCoefficients,
        constraint_set: ConstraintSet,
        scenario_year: int | None = None,
    ) -> FeasibilityResult:
        """Execute full pipeline: Leontief → unconstrained → constrained.

        Args:
            loaded_model: Model with cached B matrix and base output x.
            delta_d: Final demand shock vector.
            satellite_coefficients: For satellite impact computation.
            constraint_set: Constraints to apply.
            scenario_year: Optional year for time-windowed constraints.

        Returns:
            FeasibilityResult with unconstrained and feasible outputs.
        """
        # Step 1: Solve unconstrained Leontief
        solve_result = self._leontief.solve(
            loaded_model=loaded_model,
            delta_d=delta_d,
        )

        # Step 2: Apply constraints
        feasibility_result = self._feasibility.solve(
            unconstrained_delta_x=solve_result.delta_x_total,
            base_x=loaded_model.x,
            satellite_coefficients=satellite_coefficients,
            constraint_set=constraint_set,
            sector_codes=loaded_model.sector_codes,
            scenario_year=scenario_year,
        )

        return feasibility_result
