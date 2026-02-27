# SG Standard IO Methodology vs ImpactOS: Gap Analysis

**Date:** 2026-02-27
**Status:** Living document — updated as gaps are closed
**Context:** Strategic Gears shared a sample production model (Hajj & Umrah DIOM) demonstrating their standard IO modeling methodology. This analysis compares that **methodology** (not the specific engagement) against ImpactOS to identify output-parity gaps.

---

## 1. SG's Standard IO Modeling Methodology

Strategic Gears builds Excel-based (.xlsb) dynamic input-output models for Saudi government clients across multiple sectors. Their standard methodology, as demonstrated by the sample DIOM, includes:

**Structural Foundation**
- National IO tables from GASTAT (General Authority for Statistics) as the structural backbone (~80 sectors)
- Leontief inverse for shock propagation: direct, indirect, AND induced decomposition
- Type I effects (direct + indirect) AND Type II effects (+ induced via household income channel)

**Dynamic Forecasting**
- TFP (Total Factor Productivity) growth rates to evolve intermediate consumption coefficients over time
- Inforum-style econometric regressions for final demand components (household consumption, government spending, investment, exports)
- Fixed ratio method for primary input structure

**Satellite Structures**
- Sector-specific spending structures (OPEX/CAPEX, local/international, overnight/same-day, etc.) translated into exogenous demand shocks
- These satellites are engagement-specific (religious tourism, defense, infrastructure, etc.) but the METHODOLOGY is generic

**Value Indicators (~22 macro measures)**
- GDP at market price, GDP at basic price, real GDP
- Employment, jobs created
- Balance of trade, balance of payments
- Non-oil exports
- Government non-oil revenue, government spending ratios
- GDP intensity (GDP per unit of output)

**Scenario Framework**
- Baseline + 2+ intervention scenarios
- Interventions specified as absolute values, percentage changes, or sectoral allocations
- Master aggregation table feeding Power Query pivot tables and slicer-driven dashboards

**This is the methodology Saudi clients are accustomed to seeing.** ImpactOS must produce everything these models produce, plus more.

---

## 2. Where ImpactOS Is Already Stronger (No Changes Needed)

These capabilities represent clear advantages over SG's Excel-based methodology:

### 2.1 NFF Governance (MVP-5, MVP-8)
Excel models have **zero audit trail**. A formula changes, nobody knows when or why. ImpactOS provides claims ledger, evidence linking, assumption register, publication gate, and sandbox/governed workflow. This is the single biggest differentiator for government clients requiring accountability.

### 2.2 Feasibility & Constraints (MVP-10)
SG models show **unconstrained results only** — "if you spend X, you get Y." ImpactOS adds feasibility analysis: what happens when real-world constraints bind (capacity caps, labor ceilings, budget limits). Binding constraint diagnostics and shadow prices give actionable insight.

### 2.3 Workforce & Saudization (MVP-11)
SG models compute **total employment** as a single satellite coefficient. ImpactOS provides occupation-level bridge tables, 4-bucket nationality splits (Saudi male/female, non-Saudi male/female), min/max saudization gap analysis with achievability assessment, and confidence-driven sensitivity bands.

### 2.4 Confidence Labels & Sensitivity Envelopes
SG models have **no confidence framework**. Every number looks equally certain. ImpactOS labels inputs as HARD/ESTIMATED/ASSUMED and propagates confidence through the computation chain, producing sensitivity envelopes (central, optimistic, pessimistic) that are governance-tagged.

### 2.5 Document-to-Shock Pipeline (MVP-4, MVP-8)
SG models require **manual BoQ-to-sector mapping** — analysts read procurement documents and manually assign spending to sectors. ImpactOS automates this with AI-assisted extraction + HITL reconciliation, preserving evidence links from source document to shock vector.

### 2.6 Knowledge Flywheel (MVP-12)
In SG's methodology, institutional knowledge stays **in individual analysts' heads**. ImpactOS captures mapping decisions, assumption choices, and scenario patterns in versioned libraries that compound across engagements.

### 2.7 Reproducibility
ImpactOS provides **version IDs, content hashes, RunSnapshots, and immutable result sets**. SG models have Excel's "undo" and file-level versioning at best. Any ImpactOS result can be reproduced exactly given its RunSnapshot.

### 2.8 Data Quality Scoring (MVP-13)
No systematic data quality framework exists in the Excel methodology. ImpactOS scores every input on 6 dimensions, produces run-level quality summaries, monitors freshness, and enforces a 3-tier publication gate.

### 2.9 Multi-Engagement Scaling
SG methodology requires **one workbook per engagement**, manually duplicated and adapted. ImpactOS provides workspace-scoped isolation with shared libraries, enabling concurrent engagements with consistent methodology.

---

## 3. Methodology Gaps to Close (Roadmap Additions)

These are gaps in ImpactOS's **economic methodology** — not tied to any specific sector or client. They represent standard IO modeling capabilities that SG's methodology includes and ImpactOS currently lacks.

### GAP 1 — Type II Induced Effects (HIGH PRIORITY)

**The Gap:**
SG's standard methodology computes induced effects: household income from production generates consumption spending, which generates further demand. This is the "household income channel" — the economic multiplier from wages being spent.

ImpactOS's `LeontiefSolver` only computes Type I effects (direct + indirect via supply chains).

**Why It Matters:**
ANY Saudi client accustomed to SG's standard outputs will see lower impact numbers from ImpactOS and question the platform. Type II multipliers are typically 30-50% larger than Type I. This is not a feature request — it is a **methodology parity requirement**.

**Solution: MVP-15 — Type II Induced Effects**
- Close the Leontief model with respect to households (add household row/column to Z matrix)
- Compute `B_closed = (I - A_closed)^(-1)`
- Induced effect = Type II total - Type I total
- Always output Type I AND Type II side-by-side; never Type II alone
- Type II carries ESTIMATED confidence (the closure assumption is inherently assumption-heavy)

**Data Requirements:**
- `compensation_of_employees` vector (n,) — wages by sector (from GASTAT value added tables)
- `household_consumption_shares` vector (n,) — how households distribute spending across sectors

### GAP 2 — Value Measures Satellite (HIGH PRIORITY)

**The Gap:**
SG's standard dashboard outputs ~22 macro indicators. Clients frame policy discussions around GDP, balance of payments, government revenue — not raw "total output change." ImpactOS satellites produce employment, imports, and value added, but not disaggregated GDP (market vs basic price), trade balances, or government revenue impacts.

**Why It Matters:**
A minister asks "what is the GDP impact?" and the analyst cannot answer from ImpactOS output. The whole point of IO modeling for government is to translate project-level spending into national accounting indicators.

**Solution: MVP-16 — Value Measures Satellite**
- Deterministic post-processing transforms on delta-x using coefficient vectors
- GDP at basic price, GDP at market price, real GDP, GDP intensity
- Balance of trade, balance of payments
- Non-oil exports, government non-oil revenue, government revenue/spending ratio
- All computed from existing Leontief delta-x plus stored coefficient vectors

**Data Requirements:**
- `final_demand_F` matrix (n x k) — k = {household, government, investment, exports}
- Value added components: `compensation_of_employees`, `gross_operating_surplus`, `taxes_less_subsidies`
- `deflator_series` — year-to-deflator mapping for real GDP computation

### GAP 3 — Annual Time-Series Results (MEDIUM PRIORITY)

**The Gap:**
SG models are annual by design — they produce year-by-year results over a multi-year horizon (e.g., 2018-2030) with evolving economic structure. ImpactOS has phased solve capability but stores cumulative results only; there is no first-class annual series storage or API.

**Why It Matters:**
Dashboard time-series charts require annual data points. Ramp constraints (previously rejected in MVP-10 as "requires annual ResultSets") need year-by-year results to enforce. Scenario-vs-baseline delta series are standard SG deliverables.

**Solution: MVP-17 — RunSeries (Annual Time-Series)**
- First-class annual results storage: ResultSet per year per metric
- Scenario-vs-baseline delta series with cumulative and peak-year aggregations
- Unlocks ramp constraint enforcement in feasibility solver
- Dashboard-ready time-series output format

### GAP 4 — SG Model Import Adapter (MEDIUM PRIORITY)

**The Gap:**
SG has years of calibrated, validated IO models in Excel. The adoption strategy should be "we don't replace your models — we industrialize them."

**Solution: MVP-18 — SG Model Import Adapter**
- Parse SG Excel workbooks (.xlsb/.xlsx)
- Extract Z matrix, x vector, F matrix, VA components, sector codes, deflators
- Load as ModelVersion + TaxonomyVersion in ImpactOS
- Golden-run validation: same shock applied to both platforms, compare outputs within tolerance
- Works for ANY SG model (not engagement-specific)

**Strategic Value:**
Partners see ImpactOS reproduce their existing numbers before it adds new capabilities. Trust is built incrementally. The import adapter also serves as a data ingestion accelerator for new engagements.

---

## 4. Extended ModelVersion Requirements

To support Gaps 1-3, the `ModelVersion` / `ModelData` schema needs optional fields beyond the current Z matrix and x vector:

| Field | Shape | Purpose | Required For |
|-------|-------|---------|-------------|
| `final_demand_F` | (n, k) | Final demand by category | GDP, BOP, Value Measures |
| `imports_vector` | (n,) | Imports by sector | Balance of trade |
| `compensation_of_employees` | (n,) | Wages by sector | Type II + GDP |
| `gross_operating_surplus` | (n,) | Operating surplus by sector | GDP computation |
| `taxes_less_subsidies` | (n,) | Net taxes by sector | GDP at market price |
| `household_consumption_shares` | (n,) | Household spending distribution | Type II closure |
| `deflator_series` | dict[int, float] | Year-to-deflator mapping | Real GDP |

**Critical:** These are ALL optional, defaulting to None. Existing functionality is unaffected. They enable new satellites when populated. This maps to the technical specification Section 3.2.2 "Recommended IO/SUT blocks."

---

## 5. Immediate Actions (No Code Changes)

1. **Request standard data from SG:** GASTAT Z matrices, x vectors, sector codes, final demand F, value added components. These are generic national accounting data, not engagement-specific.

2. **Build golden-run benchmark test:** Load SG data into ImpactOS, apply a known shock, compare Type I output to SG model Type I output. This becomes a permanent regression test.

3. **Seed Knowledge Flywheel:** Import SG's standard sector taxonomies, category-to-sector mappings, and default assumption ranges into the library system (MVP-12).

4. **Use SG dashboard patterns as UI requirements:** SG's slicer-driven dashboards and master aggregation tables inform the frontend sprint F-4 design requirements.

---

## 6. Priority Summary

| Gap | Priority | MVP | Effort Estimate | Adoption Impact |
|-----|----------|-----|----------------|-----------------|
| Type II Induced Effects | HIGH | MVP-15 | 2-3 sprints | Blocks adoption — clients expect these numbers |
| Value Measures Satellite | HIGH | MVP-16 | 2 sprints | Blocks adoption — clients frame discussions around GDP |
| Annual Time-Series | MEDIUM | MVP-17 | 2 sprints | Enables dashboards and ramp constraints |
| SG Model Import Adapter | MEDIUM | MVP-18 | 1-2 sprints | Accelerates trust and data onboarding |

**Methodology Parity Gate:** ImpactOS reproduces SG standard model Type I + Type II results within 0.1% tolerance for all value measures, PLUS adds feasibility, workforce/Saudization, confidence labels, and governance that Excel models cannot provide.
