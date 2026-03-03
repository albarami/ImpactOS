# Sprint 15: Type II Induced Effects Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add deterministic Type II induced effects (household-closed Leontief) with fail-closed validation in non-dev, exposing Type I/Type II/induced side-by-side additively.

**Architecture:** Extend `LeontiefSolver` with `solve_type_ii()` that constructs (n+1) augmented matrix internally but returns n-vectors only. `BatchRunner` gets environment awareness for fail-closed. API translates domain errors to structured payloads. No migration needed.

**Tech Stack:** Python 3.11, NumPy/SciPy, FastAPI, Pydantic v2, pytest

---

### Task 1: Extend SolveResult and PhasedResult with Type II fields

**Files:**
- Modify: `src/engine/leontief.py:16-33`
- Test: `tests/engine/test_leontief.py`

**Step 1: Write failing test**

Append to `tests/engine/test_leontief.py`:

```python
class TestTypeIIResultStructure:
    """SolveResult and PhasedResult have optional Type II fields."""

    def test_solve_result_has_type_ii_fields(self) -> None:
        arr = np.zeros(3)
        result = SolveResult(
            delta_x_total=arr, delta_x_direct=arr, delta_x_indirect=arr,
        )
        assert result.delta_x_type_ii_total is None
        assert result.delta_x_induced is None

    def test_solve_result_accepts_type_ii_values(self) -> None:
        arr = np.zeros(3)
        result = SolveResult(
            delta_x_total=arr, delta_x_direct=arr, delta_x_indirect=arr,
            delta_x_type_ii_total=arr, delta_x_induced=arr,
        )
        assert result.delta_x_type_ii_total is not None
        assert result.delta_x_induced is not None
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/engine/test_leontief.py::TestTypeIIResultStructure -v`
Expected: FAIL — `SolveResult` has no `delta_x_type_ii_total` field.

**Step 3: Implement — extend dataclasses**

In `src/engine/leontief.py`, update `SolveResult`:
```python
@dataclass(frozen=True)
class SolveResult:
    """Result of a single Leontief solve: total, direct, indirect effects.
    Optional Type II fields populated when household closure is computed."""
    delta_x_total: np.ndarray
    delta_x_direct: np.ndarray
    delta_x_indirect: np.ndarray
    delta_x_type_ii_total: np.ndarray | None = None
    delta_x_induced: np.ndarray | None = None
```

Update `PhasedResult`:
```python
@dataclass(frozen=True)
class PhasedResult:
    """Result of a multi-year phased solve."""
    annual_results: dict[int, SolveResult]
    cumulative_delta_x: np.ndarray
    peak_year: int
    peak_delta_x: np.ndarray
    cumulative_delta_x_type_ii: np.ndarray | None = None
    cumulative_delta_x_induced: np.ndarray | None = None
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/engine/test_leontief.py -q`
Expected: All existing + 2 new tests pass.

**Step 5: Commit**

```bash
git add src/engine/leontief.py tests/engine/test_leontief.py
git commit -m "[sprint15] extend SolveResult/PhasedResult with optional Type II fields"
```

---

### Task 2: Implement solve_type_ii() on LeontiefSolver

**Files:**
- Modify: `src/engine/leontief.py:35-137`
- Test: `tests/engine/test_leontief.py`
- Reference: `tests/integration/golden_scenarios/shared.py` (GOLDEN_Z, GOLDEN_X, SECTOR_CODES_SMALL)

**Step 1: Add golden Type II constants to shared.py**

In `tests/integration/golden_scenarios/shared.py`, add after `EXPECTED_B_SMALL`:

```python
# Type II golden values for household-closed model
# Compensation of employees: wage payments per sector (3-sector toy model)
GOLDEN_COMPENSATION = [350.0, 900.0, 825.0]  # SAR millions

# Household consumption shares: how households spend income across sectors
# Must sum to <= 1.0 (remainder is savings)
GOLDEN_HOUSEHOLD_SHARES = [0.30, 0.45, 0.20]  # sum = 0.95

# Pre-computed Type II Leontief inverse B* = (I - A*)^{-1}
# Computed from augmented (4x4) matrix with household row/col
_w_golden = np.array(GOLDEN_COMPENSATION) / np.array(GOLDEN_X)  # wage coefficients
_h_golden = np.array(GOLDEN_HOUSEHOLD_SHARES)
_A_star = np.zeros((4, 4))
_A_star[:3, :3] = _A_SMALL
_A_star[3, :3] = _w_golden   # household income row
_A_star[:3, 3] = _h_golden   # household consumption column
EXPECTED_B_STAR_SMALL = np.linalg.inv(np.eye(4) - _A_star)
```

**Step 2: Write failing tests for solve_type_ii()**

Append to `tests/engine/test_leontief.py`:

```python
from tests.integration.golden_scenarios.shared import (
    GOLDEN_Z, GOLDEN_X, SECTOR_CODES_SMALL,
    GOLDEN_COMPENSATION, GOLDEN_HOUSEHOLD_SHARES,
    EXPECTED_B_STAR_SMALL,
)

class TestTypeIISolve:
    """Type II household-closed Leontief solve."""

    def _register_golden(self, store: ModelStore):
        mv = store.register(
            Z=np.array(GOLDEN_Z), x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL,
            base_year=2023, source="test-golden",
        )
        return store.get(mv.model_version_id)

    def test_type_ii_total_larger_than_type_i(self) -> None:
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 0.0, 0.0])
        result = solver.solve_type_ii(
            loaded_model=loaded, delta_d=delta_d,
            compensation_of_employees=np.array(GOLDEN_COMPENSATION),
            household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
        )
        assert np.sum(result.delta_x_type_ii_total) > np.sum(result.delta_x_total)

    def test_induced_equals_difference(self) -> None:
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 0.0, 0.0])
        result = solver.solve_type_ii(
            loaded_model=loaded, delta_d=delta_d,
            compensation_of_employees=np.array(GOLDEN_COMPENSATION),
            household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
        )
        np.testing.assert_allclose(
            result.delta_x_induced,
            result.delta_x_type_ii_total - result.delta_x_total,
            atol=1e-10,
        )

    def test_type_ii_matches_golden_reference(self) -> None:
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 0.0, 0.0])
        result = solver.solve_type_ii(
            loaded_model=loaded, delta_d=delta_d,
            compensation_of_employees=np.array(GOLDEN_COMPENSATION),
            household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
        )
        # Expected from B* @ [100, 0, 0, 0], trimmed to 3 sectors
        expected_type_ii = EXPECTED_B_STAR_SMALL[:3, :3] @ delta_d + EXPECTED_B_STAR_SMALL[:3, 3] * (EXPECTED_B_STAR_SMALL[3, :3] @ delta_d)
        # More precisely: full B* @ augmented_d, trimmed
        augmented_d = np.array([100.0, 0.0, 0.0, 0.0])
        expected_full = EXPECTED_B_STAR_SMALL @ augmented_d
        np.testing.assert_allclose(result.delta_x_type_ii_total, expected_full[:3], atol=1e-8)

    def test_type_ii_dimension_mismatch_raises(self) -> None:
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 0.0, 0.0])
        with pytest.raises(ValueError, match="dimension"):
            solver.solve_type_ii(
                loaded_model=loaded, delta_d=delta_d,
                compensation_of_employees=np.array([1.0, 2.0]),  # wrong length
                household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
            )

    def test_type_ii_deterministic_reproducibility(self) -> None:
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        results = [
            solver.solve_type_ii(
                loaded_model=loaded, delta_d=delta_d,
                compensation_of_employees=np.array(GOLDEN_COMPENSATION),
                household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
            )
            for _ in range(5)
        ]
        for r in results[1:]:
            np.testing.assert_array_equal(r.delta_x_type_ii_total, results[0].delta_x_type_ii_total)

    def test_existing_type_i_solve_unchanged(self) -> None:
        """Backward compat: solve() returns None for Type II fields."""
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 0.0, 0.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)
        assert result.delta_x_type_ii_total is None
        assert result.delta_x_induced is None
```

**Step 2b: Run to verify failures**

Run: `python -m pytest tests/engine/test_leontief.py::TestTypeIISolve -v`
Expected: FAIL — `solve_type_ii` not defined.

**Step 3: Implement solve_type_ii()**

Add to `LeontiefSolver` class in `src/engine/leontief.py`:

```python
def solve_type_ii(
    self,
    *,
    loaded_model: LoadedModel,
    delta_d: np.ndarray,
    compensation_of_employees: np.ndarray,
    household_consumption_shares: np.ndarray,
) -> SolveResult:
    """Compute Type II output effects with household closure.

    Constructs augmented (n+1)x(n+1) matrix A* with household
    row (wage coefficients) and column (consumption shares).
    Returns n-vectors only — household pseudo-sector stays internal.

    Args:
        loaded_model: Model with cached B matrix.
        delta_d: Final demand shock vector (n).
        compensation_of_employees: Wage payments per sector (n).
        household_consumption_shares: Household spending distribution (n), sum <= 1.

    Returns:
        SolveResult with Type I + Type II + induced fields populated.
    """
    delta_d = np.asarray(delta_d, dtype=np.float64)
    comp = np.asarray(compensation_of_employees, dtype=np.float64)
    hh_shares = np.asarray(household_consumption_shares, dtype=np.float64)
    n = loaded_model.n

    if delta_d.shape != (n,):
        msg = f"dimension mismatch: delta_d has {delta_d.shape[0]} elements, model has {n} sectors."
        raise ValueError(msg)
    if comp.shape != (n,):
        msg = f"dimension mismatch: compensation_of_employees has {comp.shape[0]} elements, model has {n} sectors."
        raise ValueError(msg)
    if hh_shares.shape != (n,):
        msg = f"dimension mismatch: household_consumption_shares has {hh_shares.shape[0]} elements, model has {n} sectors."
        raise ValueError(msg)

    # Type I solve (reuse existing method)
    type_i = self.solve(loaded_model=loaded_model, delta_d=delta_d)

    # Wage coefficient vector: w_i = compensation_i / x_i
    x = loaded_model.x
    w = comp / x

    # Construct augmented (n+1)x(n+1) matrix A*
    A = loaded_model.A
    A_star = np.zeros((n + 1, n + 1))
    A_star[:n, :n] = A
    A_star[n, :n] = w           # household income row
    A_star[:n, n] = hh_shares   # household consumption column
    # A_star[n, n] = 0 (households don't consume own output)

    # B* = (I - A*)^{-1}
    I_star = np.eye(n + 1)
    B_star = scipy_linalg.solve(I_star - A_star, I_star)

    # Augmented demand vector: [delta_d, 0]
    delta_d_aug = np.zeros(n + 1)
    delta_d_aug[:n] = delta_d

    # Type II total: trim to n sectors
    delta_x_star = B_star @ delta_d_aug
    type_ii_total = delta_x_star[:n]

    # Induced = Type II - Type I
    induced = type_ii_total - type_i.delta_x_total

    return SolveResult(
        delta_x_total=type_i.delta_x_total,
        delta_x_direct=type_i.delta_x_direct,
        delta_x_indirect=type_i.delta_x_indirect,
        delta_x_type_ii_total=type_ii_total,
        delta_x_induced=induced,
    )
```

Add `from scipy import linalg as scipy_linalg` import at top of leontief.py (it's already imported in model_store.py but not leontief.py).

**Step 4: Run to verify passes**

Run: `python -m pytest tests/engine/test_leontief.py -q`
Expected: All tests pass.

**Step 5: Commit**

```bash
git add src/engine/leontief.py tests/engine/test_leontief.py tests/integration/golden_scenarios/shared.py
git commit -m "[sprint15] implement deterministic type-ii household closure in leontief solver"
```

---

### Task 3: Extend solve_phased() for Type II

**Files:**
- Modify: `src/engine/leontief.py:83-137` (solve_phased method)
- Test: `tests/engine/test_leontief.py`

**Step 1: Write failing test**

```python
class TestTypeIIPhasedSolve:
    """Multi-year phased solve with Type II."""

    def test_phased_type_ii_accumulates(self) -> None:
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        shocks = {
            2024: np.array([100.0, 0.0, 0.0]),
            2025: np.array([50.0, 0.0, 0.0]),
        }
        result = solver.solve_phased(
            loaded_model=loaded, annual_shocks=shocks, base_year=2023,
            compensation_of_employees=np.array(GOLDEN_COMPENSATION),
            household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
        )
        assert result.cumulative_delta_x_type_ii is not None
        assert result.cumulative_delta_x_induced is not None
        np.testing.assert_allclose(
            result.cumulative_delta_x_induced,
            result.cumulative_delta_x_type_ii - result.cumulative_delta_x,
            atol=1e-10,
        )

    def test_phased_without_type_ii_returns_none(self) -> None:
        store = ModelStore()
        mv, loaded = _register_2x2(store)
        solver = LeontiefSolver()
        shocks = {2024: np.array([100.0, 0.0])}
        result = solver.solve_phased(
            loaded_model=loaded, annual_shocks=shocks, base_year=2023,
        )
        assert result.cumulative_delta_x_type_ii is None
        assert result.cumulative_delta_x_induced is None

    # Helper (same as Task 2)
    def _register_golden(self, store):
        mv = store.register(
            Z=np.array(GOLDEN_Z), x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL, base_year=2023, source="test-golden",
        )
        return store.get(mv.model_version_id)
```

**Step 2: Run and verify failure**

**Step 3: Implement — extend solve_phased()**

Update `solve_phased()` signature to accept optional Type II vectors:

```python
def solve_phased(
    self,
    *,
    loaded_model: LoadedModel,
    annual_shocks: dict[int, np.ndarray],
    base_year: int,
    deflators: dict[int, float] | None = None,
    compensation_of_employees: np.ndarray | None = None,
    household_consumption_shares: np.ndarray | None = None,
) -> PhasedResult:
```

In the per-year loop, when both vectors are provided, call `solve_type_ii()` instead of `solve()`. Accumulate Type II and induced cumulatives. Set them on PhasedResult.

**Step 4: Run and verify passes**

Run: `python -m pytest tests/engine/test_leontief.py -q`

**Step 5: Commit**

```bash
git add src/engine/leontief.py tests/engine/test_leontief.py
git commit -m "[sprint15] extend solve_phased with optional type-ii accumulation"
```

---

### Task 4: Type II prerequisite validation with reason codes

**Files:**
- Create: `src/engine/type_ii_validation.py`
- Test: `tests/engine/test_type_ii_validation.py`

**Step 1: Write failing tests**

Create `tests/engine/test_type_ii_validation.py`:

```python
"""Tests for Type II prerequisite validation."""
import numpy as np
import pytest

from src.engine.type_ii_validation import (
    TypeIIValidationError,
    validate_type_ii_prerequisites,
)


class TestTypeIIValidation:
    def test_valid_inputs_pass(self) -> None:
        result = validate_type_ii_prerequisites(
            n=3,
            x=np.array([1000.0, 2000.0, 1500.0]),
            compensation_of_employees=np.array([350.0, 900.0, 825.0]),
            household_consumption_shares=np.array([0.30, 0.45, 0.20]),
        )
        assert result.is_valid

    def test_missing_compensation_raises(self) -> None:
        with pytest.raises(TypeIIValidationError, match="TYPE_II_MISSING_COMPENSATION"):
            validate_type_ii_prerequisites(
                n=3, x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=None,
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )

    def test_missing_shares_raises(self) -> None:
        with pytest.raises(TypeIIValidationError, match="TYPE_II_MISSING_HOUSEHOLD_SHARES"):
            validate_type_ii_prerequisites(
                n=3, x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=np.array([350.0, 900.0, 825.0]),
                household_consumption_shares=None,
            )

    def test_dimension_mismatch_raises(self) -> None:
        with pytest.raises(TypeIIValidationError, match="TYPE_II_DIMENSION_MISMATCH"):
            validate_type_ii_prerequisites(
                n=3, x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=np.array([350.0, 900.0]),  # wrong length
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )

    def test_negative_values_raises(self) -> None:
        with pytest.raises(TypeIIValidationError, match="TYPE_II_NEGATIVE_VALUES"):
            validate_type_ii_prerequisites(
                n=3, x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=np.array([350.0, -10.0, 825.0]),
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )

    def test_invalid_share_sum_too_high(self) -> None:
        with pytest.raises(TypeIIValidationError, match="TYPE_II_INVALID_SHARE_SUM"):
            validate_type_ii_prerequisites(
                n=3, x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=np.array([350.0, 900.0, 825.0]),
                household_consumption_shares=np.array([0.50, 0.45, 0.20]),  # sum > 1
            )

    def test_invalid_share_sum_zero(self) -> None:
        with pytest.raises(TypeIIValidationError, match="TYPE_II_INVALID_SHARE_SUM"):
            validate_type_ii_prerequisites(
                n=3, x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=np.array([350.0, 900.0, 825.0]),
                household_consumption_shares=np.array([0.0, 0.0, 0.0]),  # sum = 0
            )

    def test_nonfinite_wage_coefficients(self) -> None:
        with pytest.raises(TypeIIValidationError, match="TYPE_II_NONFINITE_WAGE_COEFFICIENTS"):
            validate_type_ii_prerequisites(
                n=3, x=np.array([1000.0, 0.0, 1500.0]),  # zero output -> inf wage
                compensation_of_employees=np.array([350.0, 900.0, 825.0]),
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )

    def test_error_has_reason_code_attribute(self) -> None:
        with pytest.raises(TypeIIValidationError) as exc_info:
            validate_type_ii_prerequisites(
                n=3, x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=None,
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )
        assert exc_info.value.reason_code == "TYPE_II_MISSING_COMPENSATION"

    def test_no_secrets_in_error_message(self) -> None:
        with pytest.raises(TypeIIValidationError) as exc_info:
            validate_type_ii_prerequisites(
                n=3, x=np.array([1000.0, 2000.0, 1500.0]),
                compensation_of_employees=None,
                household_consumption_shares=np.array([0.30, 0.45, 0.20]),
            )
        msg = str(exc_info.value)
        assert "key" not in msg.lower() or "api" not in msg.lower()
        assert "token" not in msg.lower()
```

**Step 2: Run and verify failure**

**Step 3: Implement validation module**

Create `src/engine/type_ii_validation.py`:

```python
"""Type II prerequisite validation with structured reason codes."""

from dataclasses import dataclass

import numpy as np

_SHARE_SUM_TOLERANCE = 1e-6


class TypeIIValidationError(Exception):
    """Raised when Type II prerequisites are invalid."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class TypeIIValidationResult:
    is_valid: bool
    compensation: np.ndarray
    household_shares: np.ndarray
    wage_coefficients: np.ndarray


def validate_type_ii_prerequisites(
    *,
    n: int,
    x: np.ndarray,
    compensation_of_employees: np.ndarray | None,
    household_consumption_shares: np.ndarray | None,
) -> TypeIIValidationResult:
    """Validate Type II prerequisites. Raises TypeIIValidationError on failure."""
    if compensation_of_employees is None:
        raise TypeIIValidationError(
            "compensation_of_employees is required for Type II computation.",
            reason_code="TYPE_II_MISSING_COMPENSATION",
        )
    if household_consumption_shares is None:
        raise TypeIIValidationError(
            "household_consumption_shares is required for Type II computation.",
            reason_code="TYPE_II_MISSING_HOUSEHOLD_SHARES",
        )

    comp = np.asarray(compensation_of_employees, dtype=np.float64)
    shares = np.asarray(household_consumption_shares, dtype=np.float64)

    if comp.shape != (n,):
        raise TypeIIValidationError(
            f"compensation_of_employees has {comp.shape[0]} elements, expected {n}.",
            reason_code="TYPE_II_DIMENSION_MISMATCH",
        )
    if shares.shape != (n,):
        raise TypeIIValidationError(
            f"household_consumption_shares has {shares.shape[0]} elements, expected {n}.",
            reason_code="TYPE_II_DIMENSION_MISMATCH",
        )

    if np.any(comp < 0):
        raise TypeIIValidationError(
            "compensation_of_employees contains negative values.",
            reason_code="TYPE_II_NEGATIVE_VALUES",
        )
    if np.any(shares < 0):
        raise TypeIIValidationError(
            "household_consumption_shares contains negative values.",
            reason_code="TYPE_II_NEGATIVE_VALUES",
        )

    share_sum = float(np.sum(shares))
    if share_sum <= 0 or share_sum > 1.0 + _SHARE_SUM_TOLERANCE:
        raise TypeIIValidationError(
            f"household_consumption_shares sum is {share_sum:.6f} (must be in (0, 1]).",
            reason_code="TYPE_II_INVALID_SHARE_SUM",
        )

    w = comp / np.asarray(x, dtype=np.float64)
    if not np.all(np.isfinite(w)):
        raise TypeIIValidationError(
            "Wage coefficients (compensation / output) contain non-finite values. "
            "Check for zero-output sectors.",
            reason_code="TYPE_II_NONFINITE_WAGE_COEFFICIENTS",
        )

    return TypeIIValidationResult(
        is_valid=True,
        compensation=comp,
        household_shares=shares,
        wage_coefficients=w,
    )
```

**Step 4: Run and verify passes**

Run: `python -m pytest tests/engine/test_type_ii_validation.py -q`

**Step 5: Commit**

```bash
git add src/engine/type_ii_validation.py tests/engine/test_type_ii_validation.py
git commit -m "[sprint15] add fail-closed type-ii prerequisite validation and reason codes"
```

---

### Task 5: Add LoadedModel Type II properties and fix rehydration

**Files:**
- Modify: `src/engine/model_store.py:59-126` (LoadedModel class)
- Modify: `src/api/runs.py:242-249` (_ensure_model_loaded rehydration)
- Test: `tests/engine/test_leontief.py` (or inline with model_store tests)

**Step 1: Write failing tests**

```python
class TestLoadedModelTypeIIProperties:
    def test_has_type_ii_prerequisites_true(self) -> None:
        store = ModelStore()
        mv = store.register(
            Z=np.array(GOLDEN_Z), x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL, base_year=2023, source="test",
            artifact_payload={
                "compensation_of_employees": GOLDEN_COMPENSATION,
                "household_consumption_shares": GOLDEN_HOUSEHOLD_SHARES,
            },
        )
        loaded = store.get(mv.model_version_id)
        assert loaded.has_type_ii_prerequisites is True
        assert loaded.compensation_of_employees_array is not None
        assert loaded.household_consumption_shares_array is not None

    def test_has_type_ii_prerequisites_false(self) -> None:
        store = ModelStore()
        mv = store.register(
            Z=np.array(GOLDEN_Z), x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL, base_year=2023, source="test",
        )
        loaded = store.get(mv.model_version_id)
        assert loaded.has_type_ii_prerequisites is False
        assert loaded.compensation_of_employees_array is None
```

**Step 2: Run and verify failure**

**Step 3: Implement LoadedModel properties**

Add to `LoadedModel` class in `model_store.py`:

```python
@property
def has_type_ii_prerequisites(self) -> bool:
    mv = self._model_version
    return (
        mv.compensation_of_employees is not None
        and mv.household_consumption_shares is not None
    )

@property
def compensation_of_employees_array(self) -> np.ndarray | None:
    data = self._model_version.compensation_of_employees
    if data is None:
        return None
    return np.asarray(data, dtype=np.float64)

@property
def household_consumption_shares_array(self) -> np.ndarray | None:
    data = self._model_version.household_consumption_shares
    if data is None:
        return None
    return np.asarray(data, dtype=np.float64)
```

**Step 3b: Fix _ensure_model_loaded rehydration (Fix #1)**

In `src/api/runs.py`, line 243, the `ModelVersion` reconstruction currently omits extended artifacts. Fix:

```python
# Before (line 243-249):
mv = ModelVersion(
    model_version_id=mv_row.model_version_id,
    base_year=mv_row.base_year,
    source=mv_row.source,
    sector_count=mv_row.sector_count,
    checksum=mv_row.checksum,
)

# After:
artifact_kwargs: dict[str, object] = {}
for key in ("compensation_of_employees", "gross_operating_surplus",
            "taxes_less_subsidies", "household_consumption_shares",
            "imports_vector", "deflator_series"):
    json_key = f"{key}_json"
    val = getattr(md_row, json_key, None)
    if val is not None:
        artifact_kwargs[key] = val
fd_val = getattr(md_row, "final_demand_f_json", None)
if fd_val is not None:
    artifact_kwargs["final_demand_F"] = fd_val

mv = ModelVersion(
    model_version_id=mv_row.model_version_id,
    base_year=mv_row.base_year,
    source=mv_row.source,
    sector_count=mv_row.sector_count,
    checksum=mv_row.checksum,
    **artifact_kwargs,
)
```

**Step 4: Run and verify**

Run: `python -m pytest tests/engine/test_leontief.py tests/engine/test_api_runs.py -q`

**Step 5: Commit**

```bash
git add src/engine/model_store.py src/api/runs.py tests/engine/test_leontief.py
git commit -m "[sprint15] add LoadedModel type-ii properties and fix rehydration gap"
```

---

### Task 6: Wire environment into BatchRunner + fail-closed behavior

**Files:**
- Modify: `src/engine/batch.py:65-197`
- Modify: `src/api/runs.py:527,598` (pass environment to BatchRunner)
- Test: `tests/engine/test_batch.py`

**Step 1: Write failing tests**

Append to `tests/engine/test_batch.py`:

```python
from src.engine.type_ii_validation import TypeIIValidationError

class TestTypeIIBatchIntegration:
    """Batch runner produces Type II metrics when prerequisites available."""

    def test_batch_produces_type_ii_metrics(self) -> None:
        store = ModelStore()
        mv = store.register(
            Z=np.array(GOLDEN_Z), x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL, base_year=2023, source="test",
            artifact_payload={
                "compensation_of_employees": GOLDEN_COMPENSATION,
                "household_consumption_shares": GOLDEN_HOUSEHOLD_SHARES,
            },
        )
        runner = BatchRunner(model_store=store, environment="dev")
        scenario = ScenarioInput(
            scenario_spec_id=uuid7(), scenario_spec_version=1,
            name="test", annual_shocks={2024: np.array([100.0, 0.0, 0.0])},
            base_year=2023,
        )
        coeffs = SatelliteCoefficients(
            jobs_coeff=np.array(SMALL_JOBS_COEFF),
            import_ratio=np.array(SMALL_IMPORT_RATIO),
            va_ratio=np.array(SMALL_VA_RATIO),
            version_id=uuid7(),
        )
        request = BatchRequest(
            scenarios=[scenario], model_version_id=mv.model_version_id,
            satellite_coefficients=coeffs, version_refs=_make_refs(),
        )
        result = runner.run(request)
        metric_types = {rs.metric_type for rs in result.run_results[0].result_sets}
        assert "type_ii_total_output" in metric_types
        assert "induced_effect" in metric_types
        assert "type_ii_employment" in metric_types
        # Existing metrics still present
        assert "total_output" in metric_types
        assert "direct_effect" in metric_types

    def test_batch_without_type_ii_prerequisites_dev_fallback(self) -> None:
        """Dev: no Type II prerequisites -> Type I only, no error."""
        store, mv = _make_store_and_model()
        runner = BatchRunner(model_store=store, environment="dev")
        # ... standard run without type II fields
        # Expect only 7 original metric types, no Type II

    def test_batch_nondev_missing_prerequisites_raises(self) -> None:
        """Non-dev: model registered with Type II fields but validation fails -> error."""
        # This tests the fail-closed path when environment is staging/prod
        pass  # Placeholder — specific test depends on exact fail-closed trigger


def _make_refs() -> dict[str, UUID]:
    from uuid_extensions import uuid7
    return {
        "taxonomy_version_id": uuid7(),
        "concordance_version_id": uuid7(),
        "mapping_library_version_id": uuid7(),
        "assumption_library_version_id": uuid7(),
        "prompt_pack_version_id": uuid7(),
    }
```

**Step 2: Run and verify failure**

**Step 3: Implement**

Add `environment` param to `BatchRunner.__init__()`:

```python
class BatchRunner:
    def __init__(self, model_store: ModelStore, environment: str = "dev") -> None:
        self._store = model_store
        self._solver = LeontiefSolver()
        self._satellites = SatelliteAccounts()
        self._environment = environment
```

In `_execute_single()`, after existing Type I solve, add Type II logic:

```python
# After satellite computation on Type I results (line ~131)...

# Type II induced effects (when prerequisites available)
type_ii_computed = False
if loaded.has_type_ii_prerequisites:
    from src.engine.type_ii_validation import (
        TypeIIValidationError, validate_type_ii_prerequisites,
    )
    try:
        validate_type_ii_prerequisites(
            n=loaded.n, x=loaded.x,
            compensation_of_employees=loaded.compensation_of_employees_array,
            household_consumption_shares=loaded.household_consumption_shares_array,
        )
        phased_type_ii = self._solver.solve_phased(
            loaded_model=loaded, annual_shocks=scaled_shocks,
            base_year=scenario.base_year, deflators=scenario.deflators,
            compensation_of_employees=loaded.compensation_of_employees_array,
            household_consumption_shares=loaded.household_consumption_shares_array,
        )
        # Emit Type II metrics
        result_sets.append(ResultSet(
            run_id=run_id, metric_type="type_ii_total_output",
            values=self._vec_to_dict(phased_type_ii.cumulative_delta_x_type_ii, sector_codes),
        ))
        result_sets.append(ResultSet(
            run_id=run_id, metric_type="induced_effect",
            values=self._vec_to_dict(phased_type_ii.cumulative_delta_x_induced, sector_codes),
        ))
        # Type II employment satellite
        type_ii_jobs = coefficients.jobs_coeff * phased_type_ii.cumulative_delta_x_type_ii
        result_sets.append(ResultSet(
            run_id=run_id, metric_type="type_ii_employment",
            values=self._vec_to_dict(type_ii_jobs, sector_codes),
        ))
        type_ii_computed = True
    except TypeIIValidationError:
        if self._environment in ("staging", "prod"):
            raise  # fail-closed in non-dev
        # dev: log warning, continue with Type I only
        import logging
        logging.getLogger(__name__).warning("Type II validation failed in dev — continuing with Type I only")
```

Wire environment into BatchRunner from API: in `src/api/runs.py`, where `BatchRunner` is constructed (lines 527 and 598):

```python
from src.api.settings import get_settings
# ...
settings = get_settings()
runner = BatchRunner(model_store=_model_store, environment=settings.ENVIRONMENT.value)
```

**Step 4: Run and verify**

Run: `python -m pytest tests/engine/test_batch.py tests/engine/test_leontief.py -q`

**Step 5: Commit**

```bash
git add src/engine/batch.py src/api/runs.py tests/engine/test_batch.py
git commit -m "[sprint15] wire environment into batch runner with type-ii fail-closed"
```

---

### Task 7: API boundary error translation for Type II failures

**Files:**
- Modify: `src/api/runs.py:501-542,559-620` (create_run, create_batch_run)
- Test: `tests/engine/test_api_runs.py`

**Step 1: Write failing tests**

Append to `tests/engine/test_api_runs.py`:

```python
class TestTypeIIAPIExposure:
    """Type II metrics appear in API responses when model has prerequisites."""

    @pytest.mark.anyio
    async def test_run_with_type_ii_model_returns_induced_metrics(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        payload = _register_model_payload()
        payload["compensation_of_employees"] = [350.0, 900.0]
        payload["household_consumption_shares"] = [0.45, 0.50]
        resp = await client.post("/v1/engine/models", json=payload)
        assert resp.status_code == 201
        mvid = resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        run_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": mvid,
                "annual_shocks": {"2024": [100.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _satellite_payload(),
            },
        )
        assert run_resp.status_code == 200
        metric_types = {rs["metric_type"] for rs in run_resp.json()["result_sets"]}
        assert "type_ii_total_output" in metric_types
        assert "induced_effect" in metric_types
        assert "total_output" in metric_types  # backward compat
```

**Step 2: Run and verify failure**

**Step 3: Implement API error translation**

In `create_run` and `create_batch_run`, wrap the `runner.run()` call:

```python
from src.engine.type_ii_validation import TypeIIValidationError
from fastapi.responses import JSONResponse

try:
    result = runner.run(request)
except TypeIIValidationError as exc:
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "reason_code": exc.reason_code,
                "message": str(exc),
            }
        },
    )
```

Update return type annotations to `RunResponse | JSONResponse` and `BatchResponse | JSONResponse`.

**Step 4: Run and verify**

Run: `python -m pytest tests/engine/test_api_runs.py -q`

**Step 5: Commit**

```bash
git add src/api/runs.py tests/engine/test_api_runs.py
git commit -m "[sprint15] wire additive type-i/type-ii/induced outputs through engine api"
```

---

### Task 8: Evidence docs, parity tests, and OpenAPI refresh

**Files:**
- Modify: `docs/evidence/release-readiness-checklist.md`
- Create: `tests/evidence/test_sprint15_evidence.py`
- Create: `tests/integration/test_mathematical_accuracy.py` (append Type II tests)
- Modify: `openapi.json` (regenerate)

**Step 1: Write evidence doc section**

Append to `docs/evidence/release-readiness-checklist.md`:

```markdown
## Sprint 15: Type II Induced Effects Parity (MVP-15)

### Agent Path: Deterministic Engine (Type II Household Closure)

| Metric | Meaning | Confidence | Source |
|---|---|---|---|
| `total_output` | Type I total (direct + indirect) | MEASURED | `leontief.py:solve()` |
| `direct_effect` | Direct effect | MEASURED | `leontief.py:solve()` |
| `indirect_effect` | Indirect effect | MEASURED | `leontief.py:solve()` |
| `type_ii_total_output` | Type II total (direct + indirect + induced) | ESTIMATED | `leontief.py:solve_type_ii()` |
| `induced_effect` | Induced = Type II - Type I | ESTIMATED | `leontief.py:solve_type_ii()` |
| `type_ii_employment` | Employment from Type II total | ESTIMATED | `batch.py` |

### Prerequisite Validation

| Input | Check | Reason Code |
|---|---|---|
| compensation_of_employees is None | Missing | TYPE_II_MISSING_COMPENSATION |
| household_consumption_shares is None | Missing | TYPE_II_MISSING_HOUSEHOLD_SHARES |
| Vector length != n | Dimension | TYPE_II_DIMENSION_MISMATCH |
| Negative values | Non-negativity | TYPE_II_NEGATIVE_VALUES |
| Share sum <= 0 or > 1+tol | Sum constraint | TYPE_II_INVALID_SHARE_SUM |
| comp / x produces inf/nan | Finite check | TYPE_II_NONFINITE_WAGE_COEFFICIENTS |

### Preflight Checks

- [ ] All Type II tests pass
- [ ] Parity check: induced = type_ii_total - type_i_total (within 1e-10)
- [ ] Golden reference B* matches hand computation
- [ ] Non-dev fail-closed enforced for invalid prerequisites
- [ ] Existing Type I outputs unchanged

### Go / No-Go

- No silent Type II success when prerequisites are invalid in non-dev
- Type II metrics are additive (existing consumers unaffected)
- Deterministic: repeated runs produce identical results
```

**Step 2: Write evidence tests and parity tests**

Create `tests/evidence/test_sprint15_evidence.py` and append Type II mathematical accuracy tests to `tests/integration/test_mathematical_accuracy.py`.

**Step 3: Regenerate openapi.json**

```bash
python -c "import json; from pathlib import Path; from src.api.main import app; Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
python -c "import json; json.load(open('openapi.json','r',encoding='utf-8')); print('openapi.json valid')"
```

**Step 4: Run full verification**

```bash
python -m pytest tests/engine/test_leontief.py tests/engine/test_batch.py tests/engine/test_api_runs.py tests/engine/test_type_ii_validation.py -q
python -m pytest tests/integration/test_mathematical_accuracy.py tests/integration/test_path_engine.py -q
python -m pytest tests -q
python -m alembic current
python -m alembic check
python -m ruff check src tests
```

**Step 5: Commit**

```bash
git add docs/evidence/release-readiness-checklist.md tests/evidence/test_sprint15_evidence.py tests/integration/test_mathematical_accuracy.py openapi.json
git commit -m "[sprint15] add mvp15 parity evidence and refresh openapi"
```

---

### Task 9: Push and open PR

Use `superpowers:finishing-a-development-branch` skill.

Push branch `phase2e-sprint15-type2-induced-effects` and open PR with:
- Files changed
- Type II formula summary
- Validation matrix
- Output matrix
- Verification outputs
- Superpowers usage log (all 14)
- MVP-15 completion confirmation
