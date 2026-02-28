# MVP-10: Feasibility & Constraint Layer

## Overview

The Feasibility & Constraint Layer produces dual outputs for every scenario: an **unconstrained** result (theoretical upper bound from Leontief IO model) and a **feasible** result (clipped to real-world constraints). The gap between them is the **deliverability gap** — the policy enabler opportunity.

## Architecture

```
ScenarioSpec
    │
    ▼
┌──────────────────┐
│  Leontief Solver  │  → unconstrained delta_x
└──────────────────┘
    │
    ▼
┌──────────────────┐
│FeasibilitySolver  │  → feasible delta_x + binding diagnostics
└──────────────────┘
    │
    ▼
┌──────────────────┐
│SatelliteAccounts  │  → delta_jobs, delta_imports, delta_VA (both)
└──────────────────┘
    │
    ▼
FeasibilityResult (dual output + enablers + diagnostics)
```

### Key Principle

The feasibility layer is **fully deterministic** — no LLM calls. It lives in `src/engine/constraints/` alongside the existing Leontief solver. This maintains the Agent-to-Math Boundary: AI components produce structured JSON (constraint suggestions), the engine applies them mathematically.

## Package Structure

```
src/engine/constraints/
├── __init__.py              # Package docstring
├── schema.py                # Constraint, ConstraintSet, enums
├── defaults.py              # Saudi-specific default constraints
├── solver.py                # FeasibilitySolver (iterative clipping v1)
├── constrained_runner.py    # ConstrainedRunner (orchestrates pipeline)
├── labor_constraints.py     # D-4 integration (build constraints from workforce data)
└── store.py                 # ConstraintSetStore (persistence interface)
```

## Constraint Types

| Type | Solver Phase | Behavior |
|------|-------------|----------|
| CAPACITY_CAP | Post-solve | Clips output at absolute max |
| RAMP | Post-solve | Clips at base * (1 + max_growth_rate) |
| LABOR | Post-solve | Converts jobs cap to output cap via satellite coefficients |
| IMPORT | Post-solve | Converts import cap to output cap via satellite coefficients |
| BUDGET | Pre-solve | Applied before Leontief (NOT in solver) |
| SAUDIZATION | Diagnostic | Reports compliance gap, does NOT clip output |

## Amendments Implemented

1. **ConstraintBoundScope** — ABSOLUTE_TOTAL (cap on base+delta) vs DELTA_ONLY (cap on delta)
2. **BUDGET excluded from solver** — pre-solve only, applied before Leontief
3. **ConstraintScope** — richer than bare sector_code (sector/group/all)
4. **Economy-wide proportional allocation** — scope_type="all" with proportional rule
5. **SAUDIZATION = diagnostic only** — compliance diagnostics, no clipping
6. **ConstraintUnit typed enum** — SAR, SAR_MILLIONS, JOBS, FRACTION, GROWTH_RATE
7. **Ramp = base-to-target growth** — max_total = base * (1 + rate), not YoY sequential
8. **DB-backed persistence** — ConstraintSetStore ABC + InMemoryConstraintSetStore
9. **ConstraintConfidenceSummary** — counts HARD/ESTIMATED/ASSUMED, binding breakdown
10. **Order-independent sector clipping** — min of implied caps across constraints
11. **Separate enabler lists** — output_enablers (from binding) vs compliance_enablers (from diagnostics)
12. **Rich ConstraintSet.validate()** — detects duplicates, missing allocation rules, unsupported rules

## Known Limitations (v1)

- **IO identity violation**: Clipping sectors independently violates Leontief accounting identities. A constrained optimization (LP/QP) approach would maintain consistency but is deferred to Phase 3.
- **Ramp constraints**: Use simple base-to-target growth, not true year-over-year sequential simulation.
- **Saudization diagnostics**: Projected values are placeholder (0.0) — enriched by D-4 labor integration in practice.

## Usage

### Basic: Apply constraints to a scenario

```python
from src.engine.constraints.constrained_runner import ConstrainedRunner
from src.engine.constraints.defaults import build_default_saudi_constraints
from src.engine.leontief import LeontiefSolver
from src.engine.satellites import SatelliteAccounts
from src.engine.constraints.solver import FeasibilitySolver

runner = ConstrainedRunner(
    leontief_solver=LeontiefSolver(),
    satellite_accounts=SatelliteAccounts(),
    feasibility_solver=FeasibilitySolver(),
)

constraint_set = build_default_saudi_constraints(loaded_model.sector_codes)

result = runner.run(
    loaded_model=loaded_model,
    delta_d=delta_d,
    satellite_coefficients=sat_coefficients,
    constraint_set=constraint_set,
)

# Dual outputs
print(result.unconstrained_delta_x)  # Theoretical upper bound
print(result.feasible_delta_x)       # Constrained result
print(result.total_output_gap)       # Deliverability gap
print(result.output_enablers)        # Policy actions to close the gap
```

### Build constraints from D-4 workforce data

```python
from src.engine.constraints.labor_constraints import build_labor_constraints_from_d4

labor_constraints = build_labor_constraints_from_d4(
    employment_coefficients=d4_data,
    nitaqat_targets=saudization_targets,
    max_employment_growth=1.0,  # 100% max growth
)
```

## Test Coverage

94 tests across 8 test files:

| File | Tests | Coverage |
|------|-------|----------|
| test_constraint_schema.py | 22 | Type enums, scope validation, constraint model |
| test_constraint_set.py | 11 | Lookups, validation (Amendment 12) |
| test_feasibility_solver.py | 16 | Clipping, ramp, labor, economy-wide, diagnostics |
| test_constrained_runner.py | 4 | Full pipeline integration |
| test_enabler_ranking.py | 4 | Output + compliance enablers |
| test_labor_constraints.py | 7 | D-4 integration, saudization |
| test_defaults.py | 14 | Saudi defaults, rates, validation |
| test_binding_diagnostics.py | 13 | Binding metadata, compliance, store |
| conftest.py | — | Shared fixtures |

Total: 2515 tests (2421 existing + 94 new), 0 failures.
