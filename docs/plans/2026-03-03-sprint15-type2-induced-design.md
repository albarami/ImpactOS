# Sprint 15: Type II Induced Effects Parity — Design

**Date:** 2026-03-03
**Branch:** `phase2e-sprint15-type2-induced-effects`
**Baseline:** 4014 tests, alembic 011, main at f7c57a4

## Goal

Add deterministic Type II induced effects using household-closed Leontief logic. Compute and expose Type I, Type II, and Induced (Type II - Type I) side-by-side. Fail closed in non-dev when Type II prerequisites are invalid/missing.

## Architecture Decision

**N-vector difference approach:** Solver computes Type II internally with (n+1) closed system but returns only n-dimensional sector vectors. Household pseudo-sector stays internal. `induced = type_ii_total - type_i_total`.

## S15-1: Deterministic Type II Math

### LeontiefSolver.solve_type_ii()

1. Accept `compensation_of_employees: np.ndarray` (n), `household_consumption_shares: np.ndarray` (n), plus existing `A`, `x`, `delta_d`.
2. Derive wage coefficient vector: `w = compensation_of_employees / x`.
3. Construct augmented `(n+1) x (n+1)` matrix `A*`:
   - Top-left: existing `A` (n x n)
   - Bottom row: `w` (household income from each sector)
   - Right column: `household_consumption_shares`
   - Bottom-right: `0`
4. Compute `B* = (I - A*)^{-1}`.
5. Augment `delta_d` to (n+1) with 0 for household row.
6. Compute `delta_x_star = B* @ delta_d_augmented`.
7. Trim: `type_ii_total = delta_x_star[:n]`.
8. Return: `type_i_total` (from existing solve), `type_ii_total`, `induced = type_ii_total - type_i_total`.

### Extended SolveResult

Add optional fields (backward-compatible, default None):
- `delta_x_type_ii_total: np.ndarray | None`
- `delta_x_induced: np.ndarray | None`

### Extended PhasedResult

Add optional fields:
- `cumulative_delta_x_type_ii: np.ndarray | None`
- `cumulative_delta_x_induced: np.ndarray | None`

### solve_phased() Update

Accept optional compensation/consumption vectors. When provided, call `solve_type_ii()` per year; aggregate Type II results alongside Type I.

## S15-2: Prerequisite Validation + Fail-Closed

### validate_type_ii_prerequisites()

New function with explicit reason codes. Validates:
- Missing vectors: `TYPE_II_MISSING_COMPENSATION`, `TYPE_II_MISSING_HOUSEHOLD_SHARES`
- Length mismatch: `TYPE_II_DIMENSION_MISMATCH`
- Negative values: `TYPE_II_NEGATIVE_VALUES`
- Invalid share sum (sum <= 0 or sum > 1 + tol): `TYPE_II_INVALID_SHARE_SUM`
- Non-finite wage coefficients (inf/nan from division by zero): `TYPE_II_NONFINITE_WAGE_COEFFICIENTS`

Returns structured validation result with reason_code per failure.

### Environment Wiring (Fix #2)

`BatchRunner` currently has no env context. Wire `environment: str` from API settings into `BatchRunner.__init__()` or `execute()`. Enforce fail-closed in `_execute_single()`:
- Non-dev + invalid prerequisites -> structured failure with reason_code
- Dev + invalid -> skip Type II, emit Type I-only with explicit metadata

### API Boundary Translation (Fix #5)

In `create_run` and `create_batch_run` (`runs.py`), translate domain validation failures to structured error payloads with `reason_code`. Avoid generic 500s — catch Type II validation errors and return structured 422/503 with `{reason_code, message, environment}`.

## S15-3: Engine/API Additive Exposure

### Model Rehydration (Fix #1)

`_ensure_model_loaded()` at `runs.py:243` currently rebuilds `ModelVersion` without extended artifacts. Include `compensation_of_employees` and `household_consumption_shares` from DB rehydrate path so `LoadedModel` has access to Type II prerequisites.

### LoadedModel Additions

- `compensation_of_employees_array` property -> `np.ndarray` from `model_version.compensation_of_employees`
- `household_consumption_shares_array` property -> `np.ndarray` from `model_version.household_consumption_shares`
- `has_type_ii_prerequisites` property -> bool (both vectors present and non-None)

### batch.py Additions

After existing 7 metric types, emit 3 new `ResultSet`s when Type II computed:
- `"type_ii_total_output"` — Type II total (direct + indirect + induced)
- `"induced_effect"` — induced component only
- `"type_ii_employment"` — satellite employment on Type II total

Keep existing `"total_output"` as Type I for backward compatibility.

### Confidence Label (Fix #6)

`sector_breakdowns` is typed as numeric nested dict — string "ESTIMATED" there is type-incompatible. Instead: confidence is derived from `metric_type` prefix convention. Any metric starting with `type_ii_` or equal to `induced_effect` carries implicit ESTIMATED confidence. Document this convention in evidence. If a proper `confidence` field is desired, add it as an optional string on `ResultSet` schema (additive, non-breaking).

### Side-by-Side Clarity (Fix #7)

Final metric types emitted per run:
- `total_output` — Type I total (existing, unchanged)
- `direct_effect` — direct (existing, unchanged)
- `indirect_effect` — indirect (existing, unchanged)
- `type_ii_total_output` — Type II total (new)
- `induced_effect` — induced = Type II - Type I (new)
- `type_ii_employment` — employment from Type II total (new)
- `employment` — Type I employment (existing, unchanged)
- `imports`, `value_added`, `domestic_output` — existing, unchanged

## S15-4: Evidence + Docs

- Evidence section in `docs/evidence/release-readiness-checklist.md`
- Golden reference: pre-computed `B*` for 3-sector toy model in `tests/integration/golden_scenarios/shared.py`
- Parity test: `induced = type_ii_total - type_i_total` within tolerance

## What Does NOT Change

- No migration (metric_type is free-form string, values is JSONB)
- No breaking API changes (additive metrics only)
- No auth changes (Sprint 11+ semantics preserved)
- No new endpoints
- Existing Type I outputs identical
- `SolveResult` backward-compatible (new fields optional/None)

## Validation Matrix

| Input | Check | Non-Dev Fail Mode | Dev Behavior | Reason Code |
|---|---|---|---|---|
| compensation_of_employees is None | Missing | Structured error | Type I fallback + metadata | TYPE_II_MISSING_COMPENSATION |
| household_consumption_shares is None | Missing | Structured error | Type I fallback + metadata | TYPE_II_MISSING_HOUSEHOLD_SHARES |
| Vector length != n | Dimension | Structured error | Type I fallback + metadata | TYPE_II_DIMENSION_MISMATCH |
| Negative values in vectors | Non-negativity | Structured error | Type I fallback + metadata | TYPE_II_NEGATIVE_VALUES |
| Share sum <= 0 or > 1 + tol | Sum constraint | Structured error | Type I fallback + metadata | TYPE_II_INVALID_SHARE_SUM |
| w = comp / x produces inf/nan | Finite check | Structured error | Type I fallback + metadata | TYPE_II_NONFINITE_WAGE_COEFFICIENTS |
