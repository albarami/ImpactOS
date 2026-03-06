# ImpactOS Master Build Plan v2

**Date:** 2026-03-04
**Status:** Living document — updated as MVPs are completed and new requirements identified

---

## Phase 1 — MVP Foundation (COMPLETED)

All Phase 1 MVPs are built, tested, and committed. Phase 2 and Phase 3 through MVP-20 complete. 4422 tests passing.

| MVP | Component | Status | Tests |
|-----|-----------|--------|-------|
| MVP-1 | Workspace/RBAC + document ingestion + object storage + audit logging | Done | - |
| MVP-2 | Extraction pipeline + BoQ structuring + EvidenceSnippet generation | Done | - |
| MVP-3 | Deterministic I-O engine + ModelVersion management + batch runs | Done | - |
| MVP-4 | HITL reconciliation UI + mapping state machine + ScenarioSpec versioning | Done | - |
| MVP-5 | NFF governance MVP + sandbox/governed gate | Done | - |
| MVP-6 | Reporting/export engine + Excel escape hatch + watermarking | Done | - |
| MVP-7 | Pilot enablement | Done | - |

> **Phase 1 Gate:** Cycle time improvement at least 2x (target 3-5x). Scenario throughput at least 3x.

---

## Phase 2 — Moat Modules

### Phase 2-A: Compiler & Governance (MVP-8)

| Sprint | Component | Description |
|--------|-----------|-------------|
| **A-1** | Scenario Compiler | Document-to-shock automation: mapping suggestion models + domestic/import split heuristics + phasing/deflators |
| **A-2** | NFF Enhancement | Enhanced governance: evidence linking, assumption lifecycle, publication gate refinement |

### Phase 2-B: Intelligence Engines (MVP-9)

| Sprint | Component | Description |
|--------|-----------|-------------|
| **B-1** | Al-Muhasabi Depth Engine | 5-step structured reasoning, tiered disclosure, RESTRICTED fallback library, artifact storage |

### Phase 2-C: Constraint & Workforce Layers (MVP-10, MVP-11, MVP-12, MVP-13)

| Sprint | Component | Description |
|--------|-----------|-------------|
| **C-1** | Feasibility/Constraint Layer (MVP-10) | Two-tier solver (clipping + LP), binding constraint diagnostics, shadow prices, enabler recommendations |
| **C-2** | Workforce/Saudization Satellite (MVP-11) | Sector-occupation bridge, 4-bucket nationality split, min/max saudization gap, achievability assessment |
| **C-3** | Knowledge Flywheel (MVP-12) | Mapping/assumption/pattern libraries, learning loop, override tracker, compiler auto-capture |
| **C-4** | Data Quality Automation (MVP-13) | 6 quality dimensions, structural validity, smooth freshness decay, 3-tier publication gate |

### Phase 2-D: Saudi Data Foundation (MVP-14)

| Sprint | Component | Description |
|--------|-----------|-------------|
| **D-1** | Saudi Base IO Model | Download GASTAT IO/SUT tables. Parse Z matrix, x vector, **final demand F (n x k: household/gov/investment/exports), imports vector, value added components (compensation, operating surplus, taxes less subsidies), deflator series**. Load as ModelVersion with checksum and extended fields. Validate against published GDP aggregates. Compute and cache A and B. **Create golden-run benchmark test against SG standard model outputs.** |
| **D-2** | Nowcasting (RAS) | Target totals ingestion + RAS balancing engine + ModelVersion publication workflow |

### Phase 2-E: SG Methodology Parity (Post-Gate, Pre-Phase 3)

These modules close the methodology gap between ImpactOS and SG's standard IO modeling practice. They are adoption-critical: SG partners must see that ImpactOS produces everything their existing models produce, plus more. These are GENERIC economic modeling capabilities — not tied to any specific sector or client.

See: `docs/SG_Methodology_vs_ImpactOS_Gap_Analysis.md` for full analysis.

| MVP | Component | Description | Dependencies |
|-----|-----------|-------------|-------------|
| MVP-15 | Type II Induced Effects | Close Leontief model with respect to households. Add household row/column to Z. Compute B_closed = (I - A_closed)^(-1). Induced = Type II - Type I. Always output Type I AND Type II side-by-side. Type II carries ESTIMATED confidence. | Requires compensation_of_employees + household_consumption_shares in ModelVersion (from D-1) |
| MVP-16 | Value Measures Satellite | Deterministic post-processing: GDP at basic price, GDP at market price, real GDP, GDP intensity, balance of trade, BOP, non-oil revenue, government revenue/spending ratio. All computed from delta-x + coefficient vectors. | Requires extended ModelVersion fields (F, VA components, deflators) from D-1 |
| MVP-17 | RunSeries (Annual Time-Series) | First-class annual results storage. ResultSet per year per metric. Scenario-vs-baseline delta series. Cumulative and peak-year aggregations. Unlocks annual ramp constraints in feasibility. Dashboard-ready time-series output. | Requires phased solve results (already in BatchRunner) |
| MVP-18 | SG Model Import Adapter | Parse SG Excel workbooks (.xlsb/.xlsx). Extract Z, x, F, VA components, sector codes, deflators. Load as ModelVersion + TaxonomyVersion. Golden-run validation. Works for ANY SG model, not engagement-specific. | Requires actual SG data + extended ModelVersion |

**Methodology Parity Gate:** ImpactOS reproduces SG standard model Type I + Type II results within 0.1% tolerance for all value measures, PLUS adds feasibility, workforce/Saudization, confidence labels, and governance that Excel models cannot provide.

---

## Phase 3 — Premium Boardroom Features

| MVP | Component | Description |
|-----|-----------|-------------|
| MVP-19 | Client Portal | Controlled collaboration: assumption sign-off, scenario comparison dashboard, evidence browsing |
| MVP-20 | Structural Path Analysis | Chokepoint analytics, critical path identification in supply chains |
| MVP-21 | Portfolio Optimization | Goal-seeking workflows, multi-scenario portfolio comparison |
| MVP-22 | Live Workshop Dashboard | Slider-driven scenario adjustments with governance-safe exports |
| MVP-23 | Advanced Variance Bridges | Deterministic artifact-linked attribution, waterfall explainability, additive workspace-scoped API |

---

## Extended ModelVersion Requirements (for Phase 2-E)

To support MVPs 15-17, ModelVersion/ModelData needs optional fields beyond Z and x. These are documented as requirements for sprint D-1 implementation:

| Field | Shape | Purpose | Required For |
|-------|-------|---------|-------------|
| `final_demand_F` | (n, k) | Final demand by category (household, gov, investment, exports) | GDP, BOP, Value Measures |
| `imports_vector` | (n,) | Imports by sector | Balance of trade |
| `compensation_of_employees` | (n,) | Wages by sector | Type II closure + GDP |
| `gross_operating_surplus` | (n,) | Operating surplus by sector | GDP computation |
| `taxes_less_subsidies` | (n,) | Net taxes by sector | GDP at market price |
| `household_consumption_shares` | (n,) | Household spending distribution across sectors | Type II closure |
| `deflator_series` | dict[int, float] | Year-to-deflator mapping | Real GDP |

All fields are optional (None by default). Existing functionality is unaffected. They enable new satellites when populated. Maps to tech spec Section 3.2.2 "Recommended IO/SUT blocks."

---

## Build Progress Tracker

| MVP | Component | Tests | Commit | Date |
|-----|-----------|-------|--------|------|
| MVP-1 through MVP-7 | Phase 1 Foundation | 983 | b98c073 | - |
| MVP-8 | Compiler & NFF Enhancement | - | (within S0-4) | - |
| MVP-9 | Al-Muhasabi Depth Engine | 1190 | 5e453f3 | - |
| MVP-10 | Feasibility/Constraint Layer | 1317 | e235c43 | - |
| MVP-11 | Workforce/Saudization Satellite | 1457 | e66f17d | - |
| MVP-12 | Knowledge Flywheel | 1696 | 24e067e | - |
| MVP-13 | Data Quality Automation | 1898 | 80570bd | 2026-02-27 |
| MVP-14 | Phase 2 Integration + Gate | 1999 | 7a9db9f | 2026-02-28 |
| MVP-15 | Type II Induced Effects | 3980 | 7e98ffc | 2026-03-01 |
| MVP-16 | Value Measures Satellite | 4114 | 4374376 | 2026-03-02 |
| MVP-17 | RunSeries Annual Storage + API | 4220 | 1b2ab3e | 2026-03-02 |
| MVP-18 | SG Model Import Adapter | 4220 | a522d45 | 2026-03-03 |
| MVP-19 | Client Portal Collaboration | 4347 | 1d6dae2 | 2026-03-03 |
| MVP-20 | Structural Path Analysis + Chokepoints | 4422 | e284aa8 | 2026-03-04 |
| MVP-21 | Portfolio Optimization | 4506 | ee25cdf | 2026-03-04 |
| MVP-22 | Live Workshop Dashboard | 4556 | a9c0729 | 2026-03-04 |
| MVP-23 | Advanced Variance Bridges + Explainability | 4609 | 33303cf | 2026-03-05 |
| S24 | Full-System Staging Proof + Go/No-Go | 4932 | 1146f70 | 2026-03-05 |
| S25 | Economist Copilot v1 (Chat + Agent + Confirmation Gate) | 4698 + 320 FE | 599ec87 | 2026-03-05 |
| S26 | Copilot Hardening (Backlog Burn-Down) | 4728 + 328 FE | `sprint-26-complete` | 2026-03-05 |
| S27 | Copilot Tool Execution (Operationalization) — run_engine dry-run MVP | 4852 + 336 FE | ec3dca8 | 2026-03-06 |
| S28 | Copilot Real Execution + Post-Execution Narrative | 4938 + 348 FE | In progress | 2026-03-06 |
