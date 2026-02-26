# ImpactOS for Strategic Gears

## Internal Impact & Scenario Intelligence System — Comprehensive Project Document

**CONFIDENTIAL — INTERNAL USE**

| | |
|---|---|
| **Prepared for** | Strategic Gears |
| **Prepared by** | Salim Al-Barami |
| **Date** | 26 February 2026 |
| **Version** | 3.0 (Comprehensive) |
| **Classification** | Confidential — Internal Use |
| **Status** | For Review and Approval |

*This document defines the complete project vision, system capabilities, operating model, governance, competitive differentiators, and phased delivery plan for ImpactOS. It is intentionally non-technical. After approval, the next step is a detailed technical architecture and specification.*

---

## Document Control

| | |
|---|---|
| **Document Title** | ImpactOS for Strategic Gears — Comprehensive Project Document |
| **Version** | 3.0 |
| **Classification** | Confidential — Internal Use |
| **Prepared by** | Salim Al-Barami |
| **Prepared for** | Strategic Gears |
| **Date** | 26 February 2026 |

### Approval

| Role | Name | Signature | Date |
|---|---|---|---|
| Partner Sponsor | | | |
| Delivery Lead | | | |
| Model Steward | | | |
| Evidence Steward | | | |

---

## Table of Contents

1. [Day in the Life: Before and After ImpactOS](#1-day-in-the-life-before-and-after-impactos)
2. [Executive Summary](#2-executive-summary)
3. [Competitive Positioning](#3-competitive-positioning)
4. [The Problem Being Solved](#4-the-problem-being-solved)
5. [System Definition and Architecture Overview](#5-system-definition-and-architecture-overview)
6. [Core Moat One: The Scenario Compiler](#6-core-moat-one-the-scenario-compiler)
7. [Core Moat Two: No Free Facts Governance](#7-core-moat-two-no-free-facts-governance)
8. [The Al-Muhāsibī Depth Engine](#8-the-al-muhāsibī-depth-engine)
9. [Data Foundations and the ESCWA Advantage](#9-data-foundations-and-the-escwa-advantage)
10. [Workforce, Saudization, and Employment Realism](#10-workforce-saudization-and-employment-realism)
11. [Feasibility and Constraint Layer](#11-feasibility-and-constraint-layer)
12. [Model Validation and Credibility Monitoring](#12-model-validation-and-credibility-monitoring)
13. [Tiered Disclosure Framework](#13-tiered-disclosure-framework)
14. [Delivery Layer: The Decision Pack](#14-delivery-layer-the-decision-pack)
15. [The Knowledge Flywheel](#15-the-knowledge-flywheel)
16. [Versioning, Reproducibility, and Retention](#16-versioning-reproducibility-and-retention)
17. [Adoption and Change Management](#17-adoption-and-change-management)
18. [Security, Sovereignty, and Saudi Government Readiness](#18-security-sovereignty-and-saudi-government-readiness)
19. [Stewardship and Dependency Risk](#19-stewardship-and-dependency-risk)
20. [Phase Plan, Gates, and Investment Envelope](#20-phase-plan-gates-and-investment-envelope)
21. [Success Metrics](#21-success-metrics)
22. [Intellectual Property and Commercial Terms](#22-intellectual-property-and-commercial-terms)
23. [Approval Checklist](#23-approval-checklist)
24. [Appendix A: Worked Example — BoQ to Demand Shock](#appendix-a-worked-example--bill-of-quantities-to-demand-shock)
25. [Appendix B: Scenario Compiler Decision Tree](#appendix-b-scenario-compiler-decision-tree)
26. [Appendix C: Sandbox Versus Governed Output Policy](#appendix-c-sandbox-versus-governed-output-policy)
27. [Appendix D: Variance Bridge](#appendix-d-variance-bridge)

---

## 1. Day in the Life: Before and After ImpactOS

The most effective way to understand the value of ImpactOS is to compare how a typical economic impact engagement runs today against how it would run with the system in place. This comparison is drawn from the real operational patterns observed in consulting teams that deliver Leontief-based impact studies.

### Current State: A Typical Impact Engagement

**Week 1 — Data Assembly and Model Construction.** The engagement begins with a data hunt. Analysts locate the most recent input-output tables, clean them, rebuild or re-validate the base model in Excel, and establish sector mappings between the client's project categories and the statistical classification used in the IO tables. If the base table is several years old, additional time is spent debating whether and how to adjust it. Client documents are manually reviewed and translated into sector-level demand shocks. This mapping process is where most disputes later originate, because the choices are often undocumented.

**Week 2 — Scenario Development and Output Production.** With the model built, the team develops two to three scenarios. Each requires manual computation, chart creation, table formatting, and narrative writing. Sensitivity analysis is limited because each variation requires manual recalculation.

**Week 3 — Revision Cycles and Finalization.** The draft goes to the partner, who raises assumption questions. The client review introduces further challenges: "Where did this number come from?" Each question triggers a manual trace-back through the spreadsheet. Revisions consume the final week. The deck is finalized under time pressure.

**Observed outcome:** Two to three scenarios delivered, limited stress testing, multiple revision cycles driven by trust disputes, and significant senior time consumed on spreadsheet assembly rather than strategic insight.

### Future State: The Same Engagement with ImpactOS

**Day 1 — Document Ingestion and Automated Scenario Compilation.** The analyst uploads client documents into ImpactOS. The Scenario Compiler extracts spend lines, maps them to the IO sector taxonomy with confidence scores, proposes domestic-versus-imported splits, applies phasing and deflation to base-year equivalents, and generates a structured demand shock vector along with a complete assumption register. A Data Quality Summary is produced showing base table vintage, document coverage, and mapping confidence distribution.

**Day 2 — Human Review, Depth Engine, and Batch Execution.** The analyst resolves flagged items in the reconciliation interface in two to three hours. The Al-Muhāsibī Depth Engine generates a scenario suite with contrarian variants. The system executes twenty or more scenarios with sensitivity sweeps in a single batch.

**Day 3 — Governance, Outputs, and Delivery.** The No Free Facts gate processes the draft outputs, checking every claim against the four permissible types. The Decision Pack exports in deck-ready format with charts, tables, narrative blocks, and a full evidence and assumption appendix.

**Observed outcome:** Twenty or more scenarios delivered, default stress testing, fewer trust disputes, faster revisions, and senior time redirected to strategic interpretation and client advisory.

> **Bottom Line Promise:** ImpactOS delivers three to ten times the scenario throughput, materially fewer revision cycles, and audit-grade defensibility on every engagement. The system does not replace consulting judgment — it removes the mechanical friction that prevents that judgment from being applied at scale.

---

## 2. Executive Summary

Strategic Gears already uses Leontief input-output modelling. The mathematical model itself is not a differentiator. Multiple competitors can compute the Leontief inverse. The competitive advantage lies in the speed, depth, defensibility, and deliverability of the work that surrounds the model.

ImpactOS is an internal platform designed to industrialise the end-to-end consulting workflow around IO modelling. It creates two structural moats, two signature differentiators, and a compounding knowledge asset:

- **Scenario Compiler (Document to Shock) — Moat One.** Converts real project evidence (bills of quantities, CAPEX plans, procurement schedules, policy documents) into a defensible demand shock vector with confidence scoring, assumption documentation, and human-in-the-loop review. This is where consulting time disappears and credibility disputes originate.

- **No Free Facts Governance — Moat Two.** Enforces audit-grade truthfulness by requiring every claim to be model-derived, source-backed, an explicit assumption with sensitivity range, or a clearly labelled recommendation. Anything else is blocked from export.

- **Al-Muhāsibī Depth Engine — Licensed Methodology.** A structured reasoning loop, developed by Salim Al-Barami and licensed to Strategic Gears, producing auditable artifacts: candidate scenario angles, bias audits, contrarian variants, novelty scoring, and a curated scenario suite plan.

- **Feasibility and Constraint Layer — Saudi Credibility Differentiator.** Produces unconstrained impacts alongside feasible impacts, ranks binding constraints, and identifies the policy levers needed to close the gap between paper multipliers and deliverable outcomes.

- **Knowledge Flywheel — Compounding Institutional Value.** Every engagement strengthens growing libraries of sector mappings, assumption benchmarks, scenario patterns, and calibration notes. After twenty to thirty engagements, these become a proprietary asset that is expensive to replicate.

---

## 3. Competitive Positioning

### Core Positioning Statement

> **Positioning for Proposals and Steering Committees:** Strategic Gears does not out-math competitors. We out-process, out-govern, and out-deliver. Our impact analysis is faster because we compile initiatives automatically, deeper because we run a disciplined contrarian and stress-testing loop by default, and more defensible because every claim carries an audit trail.

### Competitive Response Framework

When a competitor claims "we also have IO modelling," Strategic Gears partners can respond:

| What Competitors Offer | What Strategic Gears Delivers |
|---|---|
| They have the Leontief inverse. | We have the Scenario Compiler: document-to-shock in hours, not weeks. |
| They have results. | We have provenance: No Free Facts evidence packs and reproducible run IDs. |
| They deliver 2–3 scenarios. | We deliver 20–30 scenarios with default sensitivity sweeps and contrarian variants. |
| They produce paper impacts. | We produce deliverable impacts with feasibility constraints and workforce realism. |
| They do one-off work. | We have a compounding library that makes every engagement faster and better. |
| Their model is a black box. | Our model is audit-grade: traceable, versioned, and reproducible. |

---

## 4. The Problem Being Solved

Even when the IO mathematics is straightforward, impact engagements are slowed and weakened by friction that has nothing to do with the model itself.

### Scenario Input Translation

The most time-consuming step is not running the model. It is translating client-provided project documentation into a defensible demand shock. Client documents come in many forms: bills of quantities with hundreds of line items, CAPEX plans organised by project phase, procurement schedules with brand names rather than commodity categories. Converting these into the sector-level demand vector that the IO model requires demands deep mapping knowledge and judgment calls. This work is typically undocumented, leading to disputes.

### Low Scenario Coverage

Because each scenario requires significant manual effort, most engagements deliver only two to three scenarios. Sensitivity analysis is limited. Stress testing and contrarian scenarios are rare because each variation requires manual recalculation, charts, and narrative.

### Credibility Disputes

A disproportionate share of engagement time is consumed by credibility challenges. When a client asks "where did this number come from?" the answer often involves tracing through Excel cells, some containing hard-coded assumptions without documentation. In government and PIF-adjacent work, untraceable assumptions create institutional risk.

### Repeated Rework

Every engagement rebuilds common components from scratch: sector mappings, import share assumptions, sensitivity ranges, chart templates. The firm's accumulated knowledge exists in analysts' heads rather than in a reusable asset.

### Lagged Base Tables

IO tables are typically published with a lag of three to five years. When an engagement uses a 2019 base table to model 2030 scenarios, clients legitimately question whether the economic structure has shifted. The absence of a systematic nowcasting method means this criticism often goes unaddressed.

---

## 5. System Definition and Architecture Overview

ImpactOS is an internal platform comprising nine tightly integrated layers. Each layer addresses a specific category of consulting friction while maintaining a clear boundary between deterministic computation and AI-assisted intelligence.

| # | Layer | Purpose |
|---|---|---|
| 1 | **Model Core** | Deterministic IO engine: fast, consistent, versioned impact computations. |
| 2 | **Scenario Compiler** | Document-to-shock translation: converts project evidence into defensible demand vectors. |
| 3 | **Depth Engine** | Al-Muhāsibī structured reasoning: red-teaming, contrarian generation, novelty scoring. |
| 4 | **Feasibility Layer** | Constraint modelling: unconstrained vs feasible impacts with binding constraint identification. |
| 5 | **Workforce Satellite** | Saudization and employment realism: sector jobs, occupation mapping, nationality feasibility. |
| 6 | **Governance Layer** | No Free Facts enforcement: claims, evidence, assumptions, run traceability. |
| 7 | **Delivery Layer** | Decision Pack generation: deck-ready charts, tables, narratives, and appendices. |
| 8 | **Adoption Layer** | Sandbox mode, Excel escape hatch, and workflow ergonomics for consulting teams. |
| 9 | **Security Layer** | Saudi-grade sovereignty posture: data residency, encryption, access control, NCA alignment. |

### Operating Principle: The Agent-to-Math Boundary

ImpactOS enforces a strict separation between AI-assisted intelligence and deterministic computation. The IO calculations are always performed by the deterministic engine. They are transparent, reproducible, and auditable. AI components propose scenario specifications and narrative drafts, but they never modify or replace the mathematical core. If a client asks how a number was produced, the answer traces to a deterministic computation with documented inputs, not to a language model's generation.

---

## 6. Core Moat One: The Scenario Compiler

The Scenario Compiler is the single most consequential component of ImpactOS because it addresses the activity that consumes the most time, generates the most disputes, and is hardest to replicate through generic tooling.

### What the Compiler Accepts

- Structured CAPEX and OPEX tables with line-item breakdowns by category and phase.
- Unstructured PDFs including bills of quantities, procurement schedules, and engineering scope documents.
- Policy briefs and strategy documents expressing targets in qualitative or percentage terms.
- Simple manual inputs where an analyst specifies a sector-level percentage increase directly.

### What the Compiler Produces

- **Demand shock vector (Δd).** The sector-level demand vector that enters the IO model, traced to its source document and mapping decision.
- **Domestic and import split.** Share of each spend category sourced domestically versus imported.
- **Phasing and deflation.** Year-by-year allocation deflated to base-year equivalents.
- **Assumption register.** Every mapping choice, import share assumption, and residual treatment logged with justification and sensitivity bounds.
- **Confidence scoring.** Each mapping scored for confidence. High-confidence items proceed automatically; low-confidence items are queued for human review.
- **Unresolved ambiguity handling.** When documents do not cover the full budget, the remaining portion is treated as an explicit assumption bucket with a defined range.

### The Human-in-the-Loop Workflow

The Compiler is designed as a human-in-the-loop system where the AI does the heavy lifting and the analyst provides judgment on the cases that matter. The reconciliation interface presents items in priority order: high-confidence items can be bulk-approved; low-confidence items are presented with suggested alternatives. This compresses a multi-day mapping exercise into a focused two-to-three-hour review session.

---

## 7. Core Moat Two: No Free Facts Governance

No Free Facts is a publication gate that transforms credibility from an aspiration into an enforced standard.

### The Four Permissible Claim Types

| Claim Type | Requirement | Example |
|---|---|---|
| **Model-derived** | Traceable to a specific run ID, model version, and input set. | "Construction output increases by SAR 4.2bn." → Run ID 2026-041. |
| **Source-backed** | Cited to a specific document, page, and table. | "Construction grew 6.2% in 2024." → GASTAT Table 3. |
| **Assumption** | Logged with value, rationale, sensitivity range, and approval. | "Local content at 60%." → A-017, range 45-75%, approved. |
| **Recommendation** | Clearly labelled as opinion or strategic advice. | "Prioritise logistics infrastructure." → Labelled. |

Any claim that does not meet one of these criteria is blocked from client-ready exports. It must be supported, rewritten as an assumption, or deleted.

### Sandbox and Governed Modes

**Sandbox mode** allows rapid exploration without governance constraints. All outputs are watermarked "DRAFT — fails NFF governance" and cannot be exported as client-ready deliverables.

**Governed mode** requires a full No Free Facts compliance pass before any deliverable can be exported. This is the mode used for all client-facing work.

---

## 8. The Al-Muhāsibī Depth Engine

The Depth Engine is proprietary intellectual property developed by Salim Al-Barami, licensed to Strategic Gears for use within ImpactOS. It operationalises a structured reasoning framework inspired by the classical Islamic scholarly tradition of muhasaba (critical self-accounting) as a multi-step loop that produces auditable artifacts.

### The Five-Step Process

**Step 1 — Khawāṭir (Generate, Do Not Trust).** Generates initial scenario directions. Each idea is labelled: nafs (ego-driven), waswās (noise), or genuine insight (analytically grounded). This forces intellectual honesty about why a direction is being proposed.

**Step 2 — Murāqaba (Bias and Frame Audit).** Audits the engagement framing. What is the default optimisation target? Are there hidden assumptions or political sensitivities? What is missing? Output: Bias Register and draft Assumption Register.

**Step 3 — Mujāhada (Contrarian Scenario Generation).** Produces stress cases and assumption-breaking variants. What if import leakage doubles? What if capacity constraints delay the project by two years? What if wage inflation displaces employment gains?

**Step 4 — Muhāsaba (Novelty and Decision-Value Scoring).** Each candidate is scored on novelty and decision value. Scenarios below threshold are rejected with documented rationale. Output: curated Shortlist.

**Step 5 — Final Scenario Suite Assembly.** Surviving scenarios are assembled into a coherent suite with story angles and narrative structures. Output: Scenario Suite Plan for team review.

### Quantitative Versus Qualitative Outputs

Some high-value contrarian insights involve second-order effects that a linear IO model cannot quantify. The Depth Engine handles this through a two-track approach: quantified levers use only the deterministic engine's available mechanisms, while qualitative risk flags attach second-order risks as labelled caveats marked "qualitative — not modelled." This provides strategic depth without overpromising the mathematics.

---

## 9. Data Foundations and the ESCWA Advantage

### Baseline Data Strategy

The primary baseline is official Saudi national accounts and IO or supply-use table releases from the General Authority for Statistics (GASTAT). Where official tables are available, they form the authoritative base.

### The ESCWA Advantage

The United Nations Economic and Social Commission for Western Asia provides structured, internationally credible resources that significantly accelerate ImpactOS:

- Inter-country input-output tables for Arab states already structured in IO format.
- Harmonised trade flow data supporting regional spillover analysis and cross-country validation.
- Sectoral benchmarks for plausibility checking of model results.
- Internationally credible provenance strengthening defensibility for government clients.

Even when the final Saudi base uses GASTAT tables, ESCWA resources reduce months of setup friction and enable regional analysis. Access to ESCWA data, combined with established organisational relationships, represents a structural advantage.

### Nowcasting Utility

IO tables typically lag the present economy by three to five years. ImpactOS includes a matrix balancing utility (RAS-type) that updates older tables using recent macro aggregates while maintaining accounting consistency. Updated matrices are explicitly labelled as balanced-nowcast versions with all assumptions recorded.

### Data Quality Summary

Every scenario run produces a Data Quality Summary reporting base table vintage, document coverage percentage, mapping confidence distribution, key missing data items, and constraint confidence indicators.

---

## 10. Workforce, Saudization, and Employment Realism

Workforce realism is a critical differentiator. Almost every Saudi client asks not just "how many jobs?" but "how many Saudi jobs?" and "is this achievable?"

### What the Workforce Satellite Produces

- Total employment impacts by sector using baseline coefficients.
- Where data exists, breakdown by broad occupation group.
- A practical three-tier nationality feasibility split: Saudi-ready, Saudi-trainable, and expatriate-reliant in the near term.

### Data Reality

IO tables are sector-based while Saudization feasibility is occupation-and-skill-level. Early deployments will be assumption-heavy. Every workforce output carries a confidence label and sensitivity range. The three-tier split is presented as an indicative assessment, not a precise prediction.

### Improvement Over Time

Each engagement refines sector-to-occupation bridges, captures analyst overrides, and calibrates against observed outcomes. After ten to fifteen workforce-focused engagements, the bridging methodology becomes a proprietary asset with empirical grounding.

---

## 11. Feasibility and Constraint Layer

The common credibility failure in Saudi consulting is the gap between model-predicted impacts and what can actually be delivered. The Feasibility Layer produces two sets of results for every scenario.

**Unconstrained impacts:** Pure IO model result showing the theoretical multiplier structure and upper bound.

**Feasible impacts:** Real-world constraints applied, producing a more realistic estimate. The difference quantifies the deliverability gap.

### Types of Constraints

- **Capacity and ramp constraints.** Sector production capacity limits and realistic ramp-up rates.
- **Labour availability.** Workforce availability by sector and skill level.
- **Import bottlenecks.** Supply chain constraints for import-dependent sectors.

### Enablers

Beyond identifying constraints, the system produces a ranked list of policy actions needed to unlock feasibility. This transforms the analysis from descriptive ("here is what the model says") to actionable ("here is what must change to make the plan deliverable").

---

## 12. Model Validation and Credibility Monitoring

ImpactOS adopts a pragmatic approach to validation through plausibility checks (multiplier magnitudes within credible benchmark ranges), consistency monitoring (sign and monotonicity checks), structural break flags (widened uncertainty when base year is misaligned), and a growing calibration library documenting known biases per sector.

---

## 13. Tiered Disclosure Framework

In Saudi consulting, sensitivity is about politically uncomfortable truths. ImpactOS uses three tiers:

| Tier | Label | Description |
|---|---|---|
| **Tier 0** | Internal Only | Contrarian and red-team outputs. Visible only to the Strategic Gears team. |
| **Tier 1** | Client Technical | Detailed analysis shared with client technical teams with full methodology. |
| **Tier 2** | Boardroom | Executive-safe narratives for steering committees and boards. |

---

## 14. Delivery Layer: The Decision Pack

The signature deliverable is the Decision Pack, a standardised output that becomes Strategic Gears' recognisable gold standard:

1. Executive summary with headline numbers and key findings.
2. Sector impact tables with multipliers and direct versus indirect decomposition.
3. Import leakage and domestic value creation analysis.
4. Employment impacts with Saudization assessment.
5. Sensitivity envelope with tornado charts.
6. Approved assumption register with ranges.
7. No Free Facts evidence ledger.
8. Feasibility-adjusted results with binding constraints.

### Excel Escape Hatch

Exports a fully linked workbook for partners who need bespoke adjustments. Manual edits trigger an "outside governance" watermark unless reconciled back into ImpactOS.

### Variance Bridge

When scenarios are revised, ImpactOS auto-produces a bridge decomposing changes into contributing factors: phasing, import shares, mapping updates, and constraints. This eliminates executive confusion and accelerates approval.

---

## 15. The Knowledge Flywheel

The Knowledge Flywheel is arguably the most valuable long-term component of ImpactOS. While productivity and governance provide immediate value, the flywheel creates compounding value that increases with every engagement.

### What the Flywheel Captures

- **Mapping Library.** How procurement categories map to IO sectors, with confidence scores refined through validation across engagements.
- **Assumption Library.** Standard import shares, local content ratios, and employment coefficients by sector.
- **Scenario Pattern Library.** Recurring scenario structures by sector and policy type.
- **Calibration Notes.** Documented observations of where multipliers overstate or understate.
- **Engagement Memory.** What clients challenged, what was accepted, what required additional evidence.
- **Workforce Bridges.** Refined bridges from sector impacts to occupation groups and nationality feasibility.

### The Lock-In Effect

> **Strategic Implication:** After twenty to thirty engagements, the Knowledge Flywheel becomes Strategic Gears' most valuable analytical asset. Competitors can replicate the IO engine and even the governance framework, but they cannot replicate accumulated validated mappings, calibrated assumptions, and institutional memory. Switching to any alternative means abandoning this knowledge base.

---

## 16. Versioning, Reproducibility, and Retention

Every model run generates a unique Run ID that snapshots the complete computational environment: base model version, mapping concordance, assumption library, scenario specification, constraint set, and evidence pack. During active engagements, the default is locked snapshot. Model updates require explicit migration workflows. Retention policies accommodate the long audit windows required by government and sovereign fund clients.

---

## 17. Adoption and Change Management

Rollout begins with one to two champion teams. For the first two to three engagements, selected outputs are validated against the traditional workflow. Role-based training covers analysts (two hours), managers (assumption approval and governance), and partners (scenario interpretation and workshop mode).

### Adoption Insurance

**Sandbox mode** ensures governance does not block exploration during the creative phase.

**Excel escape hatch** ensures partners can always make last-minute adjustments, preventing tool rejection.

**Library recognition** creates positive incentives for analysts who contribute to the institutional libraries.

---

## 18. Security, Sovereignty, and Saudi Government Readiness

ImpactOS is designed for Saudi government, PIF-affiliated, and ministry-adjacent security expectations:

- **Data residency.** Saudi-based cloud regions or on-premises VPC deployment.
- **GenAI posture.** Enterprise zero-data-retention API endpoints or locally deployed open-weight models. No client documents sent to public consumer endpoints.
- **Encryption.** TLS in transit, AES-256 at rest, managed key rotation.
- **Access control.** Role-based access, least privilege, SSO integration, workspace segregation.
- **Audit logging.** Immutable logs of access, approvals, exports, and model runs.
- **Regulatory alignment.** Controls mapped to NCA Essential Cybersecurity Controls framework.

---

## 19. Stewardship and Dependency Risk

Three stewardship roles ensure the system is self-sustaining: Model Steward (base models, taxonomy, concordances), Evidence Steward (source library, citation standards), and Quality Gate Owner (NFF compliance, claim ledger review). The system is designed so that the architect role is the designer, not the daily operator. Strategic Gears' team operates the system through playbooks, SOPs, and documentation-first development. Optional code escrow ensures full continuity.

---

## 20. Phase Plan, Gates, and Investment Envelope

### Phase 1 — MVP

- Core IO engine with model versioning.
- Scenario builder with HITL reconciliation.
- Automated outputs and baseline Decision Pack.
- Minimal NFF governance: claim ledger, assumption register, basic evidence linking.
- Sandbox mode and Excel escape hatch.

> **Phase 1 Gate (after 3 pilots):** Cycle time improvement at least 2x (target 3–5x). Scenario throughput at least 3x. Sourcing-dispute revision cycles materially reduced. If not met, root-cause review before Phase 2.

### Phase 2 — Moat Build

- Full document-to-shock Scenario Compiler.
- Al-Muhāsibī Depth Engine.
- Feasibility and constraint layer.
- Nowcasting and matrix balancing utility.
- Workforce and Saudization satellite.
- Knowledge Flywheel operational.

### Phase 3 — Premium Boardroom Features

- Client collaboration portal.
- Structural path and chokepoint analytics.
- Portfolio optimisation and goal-seeking.
- Live workshop dashboard.
- Automated variance bridges.

### Investment Envelope

| Phase | Build Effort | Stewardship | Notes |
|---|---|---|---|
| **Phase 1 (MVP)** | 8–14 person-months | 0.2–0.5 FTE | Speed, adoption, minimum governance. |
| **Phase 2 (Moat)** | 10–20 person-months | 0.5–1.5 FTE | Compiler, feasibility, workforce, security. |
| **Phase 3 (Premium)** | Variable | Variable | Depends on adoption and demand. |

---

## 21. Success Metrics

Before launch, conduct a time-motion baseline study on two to three past engagements. After rollout, track:

### Productivity

- Time from scenario request to first results.
- Number of scenario variants per engagement.
- Time on data preparation, charting, and narrative writing.

### Quality

- Percentage of claims supported versus rewritten in NFF.
- Revision cycles driven by sourcing disputes.
- Sensitivity coverage rate.

### Commercial

- Win rate on bids where defensibility is a differentiator.
- Partner leverage: engagements per team.
- Client satisfaction on clarity, speed, and trust.

---

## 22. Intellectual Property and Commercial Terms

### System IP Ownership

All ImpactOS system IP, including platform code, libraries, mappings, trained components, and engagement artifacts generated through the system, is owned by Strategic Gears. Development partners have no right to reuse proprietary components.

### Al-Muhāsibī Depth Engine IP

The Al-Muhāsibī Depth Engine methodology, framework, and underlying intellectual property remain the property of Salim Al-Barami. Strategic Gears is granted a licence to use the framework within ImpactOS under terms to be defined in the commercial agreement. Salim retains the right to use, develop, license, and commercialise the Al-Muhāsibī framework independently outside of the Strategic Gears engagement.

### Commercial Model

Commercial terms (build and retainer, platform licence, outcome-linked, or hybrid) will be defined separately from this concept document.

---

## 23. Approval Checklist

The following decisions require approval before proceeding to the technical specification:

| # | Decision Item | Approved (Y/N) |
|---|---|---|
| 1 | Scenario Compiler and No Free Facts governance as non-negotiable foundations. | |
| 2 | Al-Muhāsibī Engine produces structured artifacts with qualitative risk flags. | |
| 3 | Feasibility layer included in Phase 2 as a Saudi credibility requirement. | |
| 4 | Workforce/Saudization satellite with explicit data realism and confidence labels. | |
| 5 | Tiered disclosure model (Internal / Client Technical / Boardroom). | |
| 6 | Sandbox mode and Excel escape hatch as adoption insurance. | |
| 7 | Engagement-locked snapshots and reproducibility guarantees. | |
| 8 | Saudi security posture: data residency, sovereign AI, NCA ECC alignment. | |
| 9 | Phase gates and kill criteria with measurable success thresholds. | |
| 10 | Knowledge Flywheel as a core strategic asset. | |
| 11 | Investment envelope and IP ownership: system IP to Strategic Gears, Al-Muhāsibī methodology IP retained by Salim Al-Barami with licence to Strategic Gears. | |
| 12 | Technical specification to follow as the next deliverable. | |

> **Next Step:** Upon approval of this comprehensive project document, the next deliverable is the Technical Specification: system architecture, data model schemas, agent prompt interfaces, quality assurance gates, user interface definitions, security controls, and Saudi-compliant deployment options.

---

## Appendix A: Worked Example — Bill of Quantities to Demand Shock

**Scenario:** Logistics Zone and Industrial Park, SAR X billion CAPEX over five years.

**Client provides:** Bill of quantities, procurement schedule, phased CAPEX plan, local content targets.

1. Extract spend lines from the BoQ and normalise amounts.
2. Map each line to the IO sector taxonomy with confidence scores.
3. Classify domestic versus imported procurement using trade data and project guidance.
4. Convert nominal future-year spend to base-year equivalents using deflators.
5. Generate Δd by sector and year; identify residual buckets as explicit assumptions.
6. Analyst reviews in HITL interface: bulk-approve high-confidence, review low-confidence individually.
7. Run base scenario plus contrarian variants (import stress, capacity-constrained).
8. Export Decision Pack after passing No Free Facts governance gate.

**Result:** One to two weeks compressed into one to two days with full provenance and governance compliance.

---

## Appendix B: Scenario Compiler Decision Tree

- **Structured CAPEX table exists:** auto-map and quick HITL review.
- **Only unstructured PDFs:** extract, map with confidence gating, HITL reconciliation.
- **Coverage below 80%:** treat remainder as assumption bucket with sensitivity.
- **Contradictions detected:** escalate for manager approval and log decision.
- **Multi-year phasing:** apply deflators and annual shock vectors.
- **Constraints enabled:** run unconstrained and feasible side by side.

---

## Appendix C: Sandbox Versus Governed Output Policy

**Sandbox:** Exploration permitted. Outputs watermarked "DRAFT" and non-exportable as client-ready.

**Governed:** NFF pass mandatory. Run ID snapshots and evidence packs required for export.

**Transition:** Moving from Sandbox to Governed requires passing the NFF gate. One-way promotion.

---

## Appendix D: Variance Bridge

When scenarios are revised, ImpactOS decomposes changes into: phasing adjustments, import share revisions, mapping updates, feasibility constraints, and base model updates. Formatted as a waterfall chart in the Decision Pack.

---

*End of Document*
