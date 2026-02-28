# SG Golden-Run Benchmark Test Plan

**Date:** 2026-02-27
**Status:** Pending data from Strategic Gears
**Purpose:** Permanent regression test ensuring ImpactOS reproduces SG's standard IO model results

---

## 1. Objective

Create an automated benchmark test that validates ImpactOS produces identical economic impact results to SG's existing Excel-based IO models. This test:

- Proves ImpactOS can reproduce proven, client-accepted results
- Becomes a permanent regression test (never removed)
- Catches any fundamental change to the Leontief engine
- Builds partner trust incrementally ("your numbers, our platform")

---

## 2. Data Required from SG

All items below are **standard GASTAT national accounting data** — not engagement-specific or confidential. SG uses this same structural data across all their models.

### 2.1 Core IO Structure
| Item | Format | Description |
|------|--------|-------------|
| Z matrix | CSV/Excel | Inter-sector transaction flows (n x n), preferably 2019 or latest available |
| x vector | CSV/Excel | Total output by sector (n,) |
| Sector codes | CSV | Ordered sector identifiers matching Z rows/columns |
| Sector names | CSV | Human-readable labels for each sector code |

### 2.2 Extended ModelVersion Fields (for Phase 2-E)
| Item | Format | Description |
|------|--------|-------------|
| Final demand F | CSV/Excel | (n x k) matrix, columns = household/government/investment/exports |
| Imports vector | CSV/Excel | (n,) imports by sector |
| Compensation of employees | CSV/Excel | (n,) wages by sector |
| Gross operating surplus | CSV/Excel | (n,) operating surplus by sector |
| Taxes less subsidies | CSV/Excel | (n,) net taxes by sector |
| Household consumption shares | CSV/Excel | (n,) how households distribute spending |
| Deflator series | CSV | Year-to-GDP deflator mapping (e.g., 2018-2030) |

### 2.3 Benchmark Scenario
| Item | Description |
|------|-------------|
| Shock vector | One complete exogenous demand shock (delta_d) as applied in a real engagement |
| Type I results | SG model's direct + indirect output by sector |
| Type II results | SG model's direct + indirect + induced output by sector |
| Value measures | All ~22 macro indicators (GDP, employment, BOP, etc.) from the scenario |
| Baseline values | Pre-shock baseline for all indicators |

**Any completed SG engagement** can provide this benchmark scenario. It does not need to be the Hajj/Umrah model specifically.

---

## 3. Test Structure

### 3.1 File Location
```
tests/benchmarks/
    conftest.py              # Fixtures that load SG data from test fixtures
    test_sg_golden_run.py    # The benchmark test suite
    fixtures/
        sg_z_matrix.csv      # Z matrix from SG
        sg_x_vector.csv      # x vector from SG
        sg_sector_codes.csv  # Sector codes
        sg_shock_vector.csv  # Benchmark shock
        sg_type1_results.csv # Expected Type I results
        sg_type2_results.csv # Expected Type II results (when available)
        sg_value_measures.json  # Expected value indicators
```

### 3.2 Test Implementation

```python
# tests/benchmarks/test_sg_golden_run.py (pseudocode — actual impl when data arrives)

class TestSGGoldenRun:
    """Permanent regression test against SG standard model outputs.

    NEVER remove this test. If it fails, something fundamental changed.
    """

    def test_a_matrix_computation(self, sg_data):
        """A = Z * diag(x)^(-1) matches SG's A matrix."""
        # Tolerance: 1e-10 (pure math, no approximation)

    def test_leontief_inverse(self, sg_data):
        """B = (I - A)^(-1) matches SG's Leontief inverse."""
        # Tolerance: 1e-6 (matrix inversion numerical precision)

    def test_type1_shock_propagation(self, sg_data):
        """delta_x = B * delta_d matches SG Type I results."""
        # Tolerance: 1e-6 per sector

    def test_type1_total_output(self, sg_data):
        """Sum of delta_x matches SG total output change."""
        # Tolerance: 1e-6

    def test_type1_direct_indirect_decomposition(self, sg_data):
        """Direct + indirect components match SG decomposition."""
        # Tolerance: 1e-6

    # --- Phase 2-E tests (enabled when Type II is implemented) ---

    @pytest.mark.skip(reason="Requires MVP-15: Type II Induced Effects")
    def test_type2_induced_effects(self, sg_data):
        """Type II delta_x matches SG Type II results."""
        # Tolerance: 1e-6

    @pytest.mark.skip(reason="Requires MVP-16: Value Measures Satellite")
    def test_value_measures_gdp(self, sg_data):
        """GDP measures match SG outputs."""
        # Tolerance: 0.1% (Excel rounding differences)

    @pytest.mark.skip(reason="Requires MVP-16: Value Measures Satellite")
    def test_value_measures_employment(self, sg_data):
        """Employment measures match SG outputs."""
        # Tolerance: 0.1%

    @pytest.mark.skip(reason="Requires MVP-16: Value Measures Satellite")
    def test_value_measures_trade(self, sg_data):
        """Trade balance measures match SG outputs."""
        # Tolerance: 0.1%
```

---

## 4. Acceptance Criteria

### 4.1 Type I (Available Now)
| Metric | Tolerance | Rationale |
|--------|-----------|-----------|
| A matrix coefficients | 1e-10 | Pure division, no approximation |
| Leontief inverse B | 1e-6 | Matrix inversion numerical precision |
| delta-x per sector | 1e-6 | Matrix-vector multiplication |
| Total output change | 1e-6 | Sum of per-sector results |
| Direct/indirect decomposition | 1e-6 | Algebraic decomposition |

### 4.2 Type II (When MVP-15 is implemented)
| Metric | Tolerance | Rationale |
|--------|-----------|-----------|
| B_closed (closed Leontief inverse) | 1e-6 | Larger matrix but same math |
| Induced effects per sector | 1e-6 | Type II minus Type I |
| Total induced effect | 1e-6 | Sum |

### 4.3 Value Measures (When MVP-16 is implemented)
| Metric | Tolerance | Rationale |
|--------|-----------|-----------|
| GDP at basic price | 0.1% | Excel rounding in coefficient chain |
| GDP at market price | 0.1% | Additional tax/subsidy rounding |
| Real GDP | 0.1% | Deflator application |
| Employment | 0.1% | Coefficient-based |
| Balance of trade | 0.1% | Import/export netting |
| Government revenue | 0.1% | Tax ratio application |

---

## 5. Test Lifecycle

1. **Pre-data (now):** Test file created with `pytest.skip` markers. Structure documented. Awaiting SG data.
2. **Data arrival:** Load SG data into `tests/benchmarks/fixtures/`. Enable Type I tests. Validate green.
3. **MVP-15 (Type II):** Remove skip markers on Type II tests. Validate green.
4. **MVP-16 (Value Measures):** Remove skip markers on value measure tests. Validate green.
5. **Ongoing:** Test runs in every CI build. NEVER removed. If it breaks, investigate immediately.

---

## 6. Methodology Parity Gate

The golden-run test is the formal acceptance criterion for the Phase 2-E Methodology Parity Gate:

> ImpactOS reproduces SG standard model Type I + Type II results within tolerance for ALL value measures, PLUS adds feasibility, workforce/Saudization, confidence labels, and governance that Excel models cannot provide.

This gate must pass before ImpactOS can be presented to SG clients as a replacement for their existing Excel-based methodology.
