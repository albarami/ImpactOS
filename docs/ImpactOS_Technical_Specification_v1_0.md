# ImpactOS for Strategic Gears

## Technical Architecture and Specification

**Version 1.0 (Draft)**

| | |
|---|---|
| **Document ID** | SG-IMPACTOS-TECH-001 |
| **Prepared for** | Strategic Gears (Internal) |
| **Prepared by** | Salim (Architecture Lead) |
| **Date** | 26 February 2026 |
| **Classification** | Confidential — Internal Use Only |
| **Status** | Draft |

---

## Document Control

### Revision History

| Version | Date | Author | Summary of Changes | Approved By |
|---|---|---|---|---|
| 1.0 | 26 February 2026 | Salim | Initial technical specification derived from approved concept v2.1. | TBD |

### Approvals

| Role | Name | Signature | Date |
|---|---|---|---|
| Partner Sponsor | TBD | | |
| Delivery Lead | TBD | | |
| IT/Security Lead | TBD | | |

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [Requirements and Design Principles](#2-requirements-and-design-principles)
3. [Architecture Overview](#3-architecture-overview)
4. [Deployment Topology and Sovereign Options](#4-deployment-topology-and-sovereign-options)
5. [Data Model and Traceability (NFF-Ready)](#5-data-model-and-traceability-nff-ready)
6. [Service Interfaces and API Contracts](#6-service-interfaces-and-api-contracts)
7. [Deterministic Economic Computation Engine](#7-deterministic-economic-computation-engine)
8. [Document Ingestion, Extraction, and BoQ Structuring](#8-document-ingestion-extraction-and-boq-structuring)
9. [Scenario Compiler (Doc → Shock)](#9-scenario-compiler-doc--shock)
10. [AI/Agent Layer: Depth Engine, Drafting, and Guardrails](#10-aiagent-layer-depth-engine-drafting-and-guardrails)
11. [User Interface Workflows and State Machines](#11-user-interface-workflows-and-state-machines)
12. [Governance, Audit, and Reproducibility](#12-governance-audit-and-reproducibility)
13. [Security, Privacy, and Saudi Compliance Posture](#13-security-privacy-and-saudi-compliance-posture)
14. [Observability, Operations, and Support Model](#14-observability-operations-and-support-model)
15. [Testing, Quality Assurance, and Acceptance Criteria](#15-testing-quality-assurance-and-acceptance-criteria)
16. [Implementation Plan (Engineering Roadmap)](#16-implementation-plan-engineering-roadmap)
- [Appendix A. Shock Item Schemas](#appendix-a-shock-item-schemas-illustrative)
- [Appendix B. Assumption Schema](#appendix-b-assumption-schema-illustrative)
- [Appendix C. Claim and Evidence Schemas](#appendix-c-claim-and-evidence-schemas-illustrative)
- [Appendix D. Run Plan Schema](#appendix-d-run-plan-schema-depth-engine-output)
- [Appendix E. Open Decisions](#appendix-e-open-decisions)

---

## 1. Purpose and Scope

This document specifies the technical architecture, data model, service contracts, governance mechanisms, security posture, and delivery workflows for ImpactOS: Strategic Gears' internal Impact & Scenario Intelligence System.

It is written for the dual audience of:

- Engineering and IT teams responsible for building, deploying, and operating the platform.
- Analytics and consulting leadership responsible for governance, methodology, and adoption.

### 1.1 In-Scope Capabilities

- Deterministic input-output (I-O) computation engine (Leontief-based) with versioned base models.
- Scenario Compiler: document-to-shock pipeline with human-in-the-loop (HITL) reconciliation.
- Al-Muhāsibī Depth Engine: agentic scenario suite planning with structured artifacts and red-teaming.
- Feasibility/constraint layer (Phase 2): unconstrained vs feasible impacts and constraint diagnostics.
- Workforce/Saudization satellite (Phase 2): employment impacts with confidence and sensitivity handling.
- No Free Facts (NFF) governance: claim ledger, evidence pack, assumption register, reproducibility snapshots.
- Delivery layer: export of Decision Packs to PPT/Excel/PDF templates; Excel escape hatch with watermarking.
- Security and sovereignty posture suitable for Saudi government/PIF-adjacent work (NCA ECC-aligned).
- Operational model: observability, audit logging, retention, and phase gates.

### 1.2 Out of Scope

- Full computable general equilibrium (CGE) modeling, price equilibrium effects, or behavioral micro-simulation.
- Automatic data acquisition from restricted government systems (requires separate data-sharing agreements).
- Full client-facing portal implementation in Phase 1 (defined for Phase 3).
- Production of final consulting narratives without human review (AI drafts are always reviewable artifacts).

### 1.3 Definitions and Abbreviations

| Term | Definition | Notes |
|---|---|---|
| A | Technical coefficients matrix | Derived from intermediate transactions Z and gross output x. |
| Leontief inverse | (I - A)^-1 | Total requirements matrix; used for Δx = (I - A)^-1 Δd. |
| Δd | Final demand shock vector | Can be phased over time; can include domestic/import split. |
| Run ID | Immutable snapshot of a model execution | Binds scenario spec, assumptions, mappings, and model versions. |
| NFF | No Free Facts governance rule | Claims must be model-derived, source-backed, or explicit assumptions. |
| HITL | Human-in-the-loop | Analyst reconciliation/approval workflow for mappings and assumptions. |
| ECC | Essential Cybersecurity Controls (Saudi NCA) | Design is aligned to ECC expectations; compliance is an operational decision. |

---

## 2. Requirements and Design Principles

ImpactOS is designed around a strict separation of concerns: deterministic economic computation is isolated from probabilistic AI assistance. The platform must improve consulting throughput without compromising auditability, sovereignty, or credibility.

### 2.1 Core Design Principles

- **Deterministic core, intelligent wrappers:** Matrix operations are executed only by the math engine; AI does not compute results.
- **Air-gapped contract:** AI services output validated JSON specs only; all execution occurs in deterministic services.
- **No Free Facts as a publication gate:** Final exports are blocked unless claims are supported or explicitly assumed.
- **Artifact transparency:** The Depth Engine produces structured artifacts (candidate set, bias register, contrarian suite, scores), not hidden reasoning.
- **Engagement-locked reproducibility:** Every Run ID snapshots all versions (model, mappings, assumptions, constraints, prompts) to allow exact reruns years later.
- **Adoption insurance:** Sandbox mode and an Excel escape hatch prevent tool abandonment under time pressure.
- **Sovereign-by-design:** Sensitive documents are processed within approved environments; model choice depends on data classification.

### 2.2 Functional Requirements (High Level)

| Capability | Requirement | Acceptance Indicator |
|---|---|---|
| Scenario compilation | Convert project/policy inputs into a structured ScenarioSpec with Δd, assumptions, and confidence metrics. | ScenarioSpec created with mapping audit trail; analyst can approve/override. |
| Batch scenario runs | Execute 50+ scenarios with sensitivity variants and produce standardized outputs. | Batch run completes within target window; outputs generated without manual formatting. |
| Governed exports | Generate Decision Pack exports that pass NFF governance. | All claims resolved; evidence pack and assumption register attached; export enabled. |
| Reproducibility | Re-run any historical Run ID and reproduce identical outputs. | Hash/signature match and consistent results within numerical tolerance. |
| Feasibility view (Phase 2) | Compute unconstrained vs feasible impacts under constraints with binding-constraint diagnostics. | Feasible impacts generated; top binding constraints ranked; confidence label present. |
| Workforce satellite (Phase 2) | Estimate employment and Saudization feasibility with confidence/sensitivity. | Jobs split produced; sensitivity envelope; explicit data quality summary. |

### 2.3 Non-Functional Requirements

| Dimension | Target | Notes | Phase |
|---|---|---|---|
| Latency — single scenario compute | < 30 seconds | Assumes Leontief inverse precomputed; excludes document ingestion time. | P1 |
| Latency — batch (50 scenarios) | < 10 minutes | Includes sensitivity variants; parallelizable. | P1 |
| Availability | >= 99.5% (business hours) | Higher targets possible with HA deployment. | P1+ |
| RPO/RTO | RPO 24h / RTO 8h | Adjust for client classification and audit needs. | P1+ |
| Audit retention | >= 5–7 years (configurable) | Government/PIF work may require extended retention. | P1+ |
| Security posture | NCA ECC-aligned controls | Identity, encryption, logging, segregation, incident response. | P1+ |
| Scalability | Support 100+ concurrent users | Primarily UI and ingestion bound; math compute is lightweight. | P2 |
| Arabic outputs | Optional bilingual templates | Depends on client requirements; adds template complexity. | P2/P3 |

---

## 3. Architecture Overview

ImpactOS is implemented as a modular, service-oriented platform. The architecture separates: (1) deterministic economic computation, (2) document ingestion and scenario compilation, (3) AI-assisted planning and drafting, and (4) governance and publication controls.

### 3.1 Logical Architecture

*Figure 1 — ImpactOS logical architecture (high level). See attached diagram.*

### 3.2 Key Architectural Boundaries

- **AI-to-math boundary:** AI components generate structured configuration (ScenarioSpec, mapping suggestions, claim drafts) but never execute matrix math.
- **Governance boundary:** Exports to client-ready artifacts are only permitted through the NFF publication gate.
- **Data sovereignty boundary:** Confidential client documents are processed only within approved infrastructure; LLM routing depends on classification.
- **Engagement boundary:** Each engagement is a workspace with isolated data, role-based access, and immutable run snapshots.

### 3.3 Core Components

| Component | Responsibility | Primary Data |
|---|---|---|
| **UI / Portal** | Scenario creation, HITL reconciliation, run management, review/approvals, exports. | ScenarioSpec, mappings, claims, evidence, exports. |
| **API Gateway** | Unified API surface; authentication/authorization; request validation. | All request/response schemas. |
| **Workflow Orchestrator** | Asynchronous job orchestration for ingestion, compilation, batch runs, and export pipelines. | Job state, queues, run snapshots. |
| **Document Ingestion & Extraction** | Ingest PDFs/Excel; extract tables, line items, coordinates; generate structured BoQ datasets. | Document objects, extracted tables/cells. |
| **Scenario Compiler** | Doc → shock: propose sector mappings, domestic/import split, phasing, deflation; produce ScenarioSpec. | BoQ line items, mapping library, assumptions. |
| **Deterministic I-O Engine** | Compute A, (I-A)^-1, Δx, multipliers, satellite impacts; generate results sets. | ModelVersion, matrices, Δd vectors, ResultSets. |
| **Governance Engine (NFF)** | Claim ledger extraction, evidence linking, assumption registry, publication gate, reproducibility signatures. | Claims, EvidenceSnippets, Assumptions, Run IDs. |
| **Reporting/Export Engine** | Generate PPT/Excel/PDF packs; watermark sandbox outputs; embed run metadata. | Report templates, ResultSets, Evidence/Assumption appendices. |
| **Data Stores** | Relational metadata, object storage for documents/artifacts, vector index for retrieval. | Postgres + object store + vector store. |

---

## 4. Deployment Topology and Sovereign Options

ImpactOS supports multiple deployment topologies to meet Saudi data residency and client classification requirements. The final topology is a governance decision jointly owned by Strategic Gears leadership and IT/security.

### 4.1 Reference Deployment Options

- **Option A — Sovereign Cloud (in-Kingdom):** Deploy services into an approved Saudi cloud region/VPC with managed Kubernetes, managed PostgreSQL, and compliant AI endpoints.
- **Option B — Private VPC / On-Prem (highest sovereignty):** Deploy into Strategic Gears-controlled infrastructure using Kubernetes/OpenShift, self-managed PostgreSQL, and locally hosted LLMs.
- **Option C — Hybrid:** Route non-sensitive workloads (e.g., public sources, sandbox drafts) to enterprise cloud AI, while restricted client documents and governed exports remain fully sovereign.

### 4.2 Network Segmentation (Recommended)

- **Presentation zone:** UI/portal and API gateway (internet-facing with WAF).
- **Application zone:** Internal services (orchestrator, compiler, governance, reporting).
- **Data zone:** PostgreSQL, object storage, vector store, key management; no direct internet access.
- **Restricted processing zone (optional):** Document extraction workers and local LLM inference nodes for classified inputs.
- **Outbound egress control:** Allowlisted destinations only; DLP controls for document uploads and external API calls.

### 4.3 AI Inference Routing by Data Classification

| Classification | Allowed AI Endpoint | Typical Use | Controls |
|---|---|---|---|
| Public/Non-sensitive | Enterprise cloud LLM (zero data retention) | General drafting, summarization of public sources, template generation | No client docs; retrieval limited to public corpus. |
| Confidential — Client | In-country enterprise LLM or local model | Scenario compilation on client documents; evidence extraction support | Strict logging; no external retention; workspace isolation. |
| Restricted / High sensitivity | Local model only (air-gapped if required) | Parsing and mapping of sensitive project documents | No external connectivity; enhanced approvals; Tiered disclosure enforced. |

### 4.4 Infrastructure Stack (Reference)

- **Backend services:** Python (FastAPI) for APIs; worker processes for asynchronous jobs.
- **Math engine:** Python (NumPy/SciPy) with validated numerical routines and caching.
- **Database:** PostgreSQL for relational metadata; pgvector (or a dedicated vector store) for retrieval embeddings.
- **Object storage:** S3-compatible store for documents, extracted tables, and generated artifacts.
- **Messaging/queues:** A job queue (e.g., Redis/Celery or Kafka/RabbitMQ) for ingestion and batch runs.
- **Frontend:** React/Next.js optimized for high-throughput HITL reconciliation (keyboard-first).
- **AuthN/AuthZ:** SSO via OIDC/SAML; RBAC with project/workspace scoping.
- **Observability:** Central logs + metrics + tracing; SIEM integration for security monitoring.

---

## 5. Data Model and Traceability (NFF-Ready)

ImpactOS is governed by traceability requirements: every client-facing number or claim must be traceable to either (a) a deterministic model run, (b) a cited evidence source, or (c) an explicit assumption. This section defines the entity model and the end-to-end lineage chain.

### 5.1 Traceability Chain

*Figure 2 — Minimum lineage chain for No Free Facts governance. See attached diagram.*

### 5.2 Storage Layers

- **Relational metadata (PostgreSQL):** Workspaces, scenarios, runs, claims, assumptions, approvals, and indexing.
- **Object storage (S3-compatible):** Source documents (PDF/Excel), extracted intermediate files, and exported report packs.
- **Vector index (pgvector or dedicated store):** Embeddings for retrieval-augmented evidence lookup within the engagement corpus.
- **Secrets/key management:** Encryption keys, API credentials, signing keys (integrated with enterprise KMS).

### 5.3 Core Entities (Logical ER Model)

| Entity | Key Fields (illustrative) | Mutable? | Notes / Invariants |
|---|---|---|---|
| **Workspace** | workspace_id, client_name, engagement_code, classification | Yes | Workspace is the isolation boundary for data, permissions, and audit. |
| **User/Membership** | user_id, role, workspace_id | Yes | RBAC is scoped per workspace; actions are audit logged. |
| **ModelVersion** | model_version_id, base_year, source, sector_count, checksum | Append-only | ModelVersion is immutable; updates create a new version. |
| **TaxonomyVersion** | taxonomy_version_id, sector_codes, hierarchy | Append-only | Taxonomy is immutable per version; concordance handles evolution. |
| **ConcordanceVersion** | concordance_id, from_taxonomy, to_taxonomy, mappings | Append-only | Used to translate between official and internal taxonomies. |
| **PromptPackVersion** | prompt_pack_id, agent_prompts, safety_rules, checksum | Append-only | Captured in Run snapshots for reproducibility. |
| **ScenarioSpec** | scenario_spec_id, name, disclosure_tier, base_model_ref, shock_items | Versioned | ScenarioSpec is versioned; governed exports reference a specific version. |
| **BoQDataset** | boq_id, document_refs, extraction_metadata, line_items | Yes | Represents extracted structured spend lines from ingested documents. |
| **RunRequest** | run_id, scenario_spec_id, mode, sensitivity_plan | Immutable | Created at run start; snapshot of all versions is captured. |
| **RunSnapshot** | run_id, model_version_id, taxonomy_version_id, ..., checksums | Immutable | Captures all version references needed for reproducibility. |
| **ResultSet** | result_id, run_id, metric_type, values, sector_breakdowns | Immutable | Deterministic engine outputs; authoritative source of numerical results. |
| **Assumption** | assumption_id, type, value, range, justification, status | Versioned | Assumptions are governed; changes create new versions. |
| **Claim** | claim_id, text, claim_type, status, disclosure_tier | Versioned | Claims extracted from narratives; must pass NFF resolution. |
| **EvidenceSnippet** | snippet_id, source_id, page, bbox, extracted_text, checksum | Immutable | Fine-grained source reference; supports multiple evidences per claim. |
| **Export** | export_id, run_id, template_version, mode, status, checksum | Append-only | Exports capture final deliverable packs; governed exports require NFF pass. |

### 5.4 Evidence Granularity and Bounding Box Coordinates

To meet audit-grade traceability, evidence must be addressable at fine granularity, not only by document name. ImpactOS stores EvidenceSnippets with exact coordinates for the source location.

- **Page reference:** PDF page number (0-indexed internally, displayed as 1-indexed).
- **Bounding box:** (x0, y0, x1, y1) in normalized page coordinates (0..1) to ensure rendering independence.
- **Table cell reference:** Optional pointer to extracted table ID, row/column index, and cell text.
- **Checksum:** Source document content hash to prevent silent document replacement.

### 5.5 Data Quality Summary Object (Scenario-Level)

Every ScenarioSpec and Run includes a DataQualitySummary to make uncertainty explicit and reusable in narrative generation.

```
DataQualitySummary (illustrative)
- base_table_vintage_years: int
- boq_coverage_pct: float
- mapping_confidence: {high_pct, medium_pct, low_pct}
- unresolved_items_count: int
- assumptions_count: int
- constraint_confidence: {hard_data_pct, estimated_pct, assumed_pct}
- notes: [string]
```

---

## 6. Service Interfaces and API Contracts

ImpactOS uses a schema-first API design. All external and internal contracts are defined as JSON schemas and published via OpenAPI. AI services are restricted to producing JSON that conforms to these schemas.

### 6.1 Air-Gap Boundary: AI Output Contract

AI components (Scenario Compiler agents, Depth Engine agents, narrative drafting agents) are not permitted to execute economic computations. They may only emit structured JSON objects that pass validation.

- All AI outputs are validated using strict JSON schema + Pydantic models.
- Invalid outputs are rejected and re-requested with explicit error messages (no partial execution).
- The deterministic I-O engine accepts only validated RunRequests and ScenarioSpecs.
- Numerical outputs presented to clients must originate from the deterministic engine (ResultSets), not from AI text.

### 6.2 External API Surface (Gateway)

| Domain | Endpoint (example) | Method | Purpose |
|---|---|---|---|
| Workspaces | `/api/workspaces` | GET/POST | List/create workspaces; manage engagement metadata. |
| Documents | `/api/workspaces/{id}/documents` | POST | Upload document; returns document_id. |
| Extraction | `/api/documents/{id}/extract` | POST | Start extraction job (tables/BoQ). |
| BoQ datasets | `/api/workspaces/{id}/boq-datasets` | GET | List structured BoQ datasets for an engagement. |
| Mapping | `/api/boq-datasets/{id}/mapping-suggestions` | POST | Generate mapping suggestions with confidence. |
| Scenarios | `/api/workspaces/{id}/scenarios` | GET/POST | Create and manage ScenarioSpec versions. |
| Runs | `/api/scenarios/{id}/runs` | POST | Create a RunRequest and start execution. |
| Results | `/api/runs/{id}/results` | GET | Fetch ResultSet outputs for visualization and exports. |
| Governance | `/api/runs/{id}/governance/status` | GET | NFF gate status and unresolved claims/assumptions. |
| Exports | `/api/runs/{id}/exports` | POST | Generate report packs (PPT/Excel/PDF) subject to NFF rules. |
| Audit | `/api/workspaces/{id}/audit-log` | GET | Query audit events (restricted). |

### 6.3 Core Payload Schemas (Illustrative)

#### 6.3.1 ScenarioSpec (simplified)

```json
{
  "scenario_spec_id": "uuid",
  "version": 3,
  "name": "NEOM Logistics Zone - Base",
  "workspace_id": "uuid",
  "disclosure_tier": "TIER0|TIER1|TIER2",
  "base_model_version_id": "uuid",
  "currency": "SAR",
  "base_year": 2023,
  "time_horizon": {"start_year": 2026, "end_year": 2030},
  "shock_items": [ ... ],
  "assumptions": [ ... ],
  "data_quality_summary": { ... }
}
```

#### 6.3.2 RunRequest and RunSnapshot

```json
// RunRequest
{
  "scenario_spec_id": "uuid",
  "scenario_spec_version": 3,
  "mode": "SANDBOX|GOVERNED",
  "sensitivity_plan_id": "uuid|null",
  "export_template_version": "SG-DECISIONPACK-2026.1",
  "requested_outputs": ["sector_impacts","multipliers","jobs","imports","waterfall"]
}

// RunSnapshot (immutable, created at run start)
{
  "run_id": "uuid",
  "model_version_id": "uuid",
  "taxonomy_version_id": "uuid",
  "concordance_version_id": "uuid",
  "mapping_library_version_id": "uuid",
  "assumption_library_version_id": "uuid",
  "prompt_pack_version_id": "uuid",
  "constraint_set_version_id": "uuid|null",
  "source_checksums": ["sha256:..."],
  "created_at": "timestamp"
}
```

### 6.4 Error Handling and Idempotency

- All POST endpoints support idempotency keys to prevent duplicate runs/exports on retries.
- Validation errors return machine-readable schema violations to support rapid correction.
- Run execution errors are captured with a structured error taxonomy (ingestion, mapping, compute, governance, export).
- Governed exports are denied with explicit reasons (unresolved claims, unapproved assumptions, missing evidence).

---

## 7. Deterministic Economic Computation Engine

The deterministic engine is the computational core of ImpactOS. It is responsible for all matrix algebra, multiplier calculations, and generation of authoritative ResultSets. It exposes a narrow API surface and must be fully testable, reproducible, and numerically stable.

### 7.1 Inputs and Canonical Data Structures

- **Intermediate transactions matrix Z** (n × n): sector-to-sector inputs (in value terms, base-year currency).
- **Gross output vector x** (n): total output per sector.
- **Final demand vector d** (n) or final demand block (n × k) if disaggregated by category.
- **Optional satellite vectors/matrices:** employment coefficients, import ratios, value-added ratios, emissions factors.
- **Taxonomy metadata:** ordered sector codes, labels, hierarchy, concordances.

### 7.2 Core Computations

```
Technical coefficients:
  A = Z * diag(x)^(-1)    where a_ij = z_ij / x_j

Leontief system:
  x = A·x + d
  (I - A)·x = d

Leontief inverse:
  B = (I - A)^(-1)

Shock propagation (for a final-demand shock Δd):
  Δx = B · Δd
```

### 7.3 Decomposition: Direct vs Indirect (Type I)

```
Total output effect:
  Δx_total = B · Δd

Direct effect (final demand injection):
  Δx_direct = Δd

Indirect effect (supply-chain ripple):
  Δx_indirect = (B - I) · Δd
```

If alternative direct-effect definitions are required for specific client conventions, they must be captured as template-specific rules and recorded in the RunSnapshot.

### 7.4 Phasing and Deflation (Multi-Year Scenarios)

Many Saudi initiatives are phased over multiple years. ImpactOS represents a phased scenario as a set of annual shocks expressed in base-year real terms.

```
For each year t in [start_year..end_year]:
  nominal_shock_t (SAR_t) → deflate → real_shock_t (SAR_base)

Compute annual impacts:
  Δx_t = B · Δd_t

Aggregate outputs:
  - Annual results (time series)
  - Cumulative results (sum over t)
  - Peak-year results (max over t)
```

### 7.5 Satellite Accounts (Jobs, Imports, Value Added)

Satellite impacts are computed as linear transforms of Δx (and optional leakage parameters).

```
Employment (sector-level):
  jobs_coeff_i = jobs_i / output_i
  Δjobs = diag(jobs_coeff) · Δx

Imports/leakage (ratio-based approximation):
  import_ratio_i = imports_i / output_i
  Δimports = diag(import_ratio) · Δx
  Δdomestic_output = Δx - Δimports

Value-added (ratio-based approximation):
  va_ratio_i = value_added_i / output_i
  ΔVA = diag(va_ratio) · Δx
```

All satellite coefficients are versioned and treated as governed inputs. If coefficients are estimated or assumption-based, they must appear in the AssumptionRegister with confidence and sensitivity ranges.

### 7.6 Numerical Stability and Performance

- Avoid explicit matrix inversion in production for large n; use linear solvers/factorization where possible.
- Cache B (or its factorization) per ModelVersion to accelerate batch runs.
- Validate productivity conditions: stability checks on A (e.g., spectral radius < 1) and non-negativity of key outputs.
- Store results with numerical tolerance policy (documented) for reproducibility and regression testing.

### 7.7 Nowcasting / Matrix Balancing Utility (RAS)

To address lagged I-O tables, ImpactOS includes a matrix balancing utility (e.g., RAS) to update Z to match new row/column totals while preserving structure. The output is a new ModelVersion with explicit provenance.

```
RAS (outline)
Inputs:
  Z0: baseline intermediate matrix
  r: target row totals (intermediate inputs by sector)
  c: target column totals (intermediate outputs used by sectors)
Initialize:
  Z = Z0
Iterate until convergence:
  1) Row scaling: Z[i,*] *= r[i] / sum_j Z[i,j]
  2) Column scaling: Z[*,j] *= c[j] / sum_i Z[i,j]
Output:
  Z* balanced to r and c within tolerance
```

RAS runs are governed: the target totals (r, c), sources, and tolerances are stored as explicit assumptions and become part of the ModelVersion provenance.

### 7.8 Feasibility/Constraint Engine (Phase 2)

The feasibility layer adds deliverability realism by applying constraints (capacity, labor, import bottlenecks) to the unconstrained Δx computed by the I-O engine.

```
Feasible impact (conceptual)
Given:
  required Δx_req = B · Δd
Constraints (examples):
  0 <= Δx <= cap_output
  Δjobs <= cap_labor
  ramp_rate limits across years
Compute:
  Δx_feasible = argmin ||Δx - Δx_req|| subject to constraints
Outputs:
  - Δx_feasible
  - binding constraints and shadow diagnostics
  - constraint confidence labels
```

### 7.9 Regional Downscaling (Optional Extension)

For geographically concentrated giga-projects, national results can be downscaled using transparent allocation methods (e.g., location quotients, supplier location assumptions). Regional outputs must be labeled as assumption-sensitive and governed by explicit parameters.

---

## 8. Document Ingestion, Extraction, and BoQ Structuring

The Scenario Compiler depends on reliable extraction of structured spend lines from documents. Bills of Quantities (BoQs) and procurement schedules are often large, multi-format, and scanned. This pipeline must minimize row/column loss, preserve provenance, and store coordinates for evidence traceability.

### 8.1 Ingestion Workflow

1. **Upload:** UI or API uploads documents (PDF, XLSX, CSV, DOCX).
2. **Pre-processing:** Virus scanning, file type validation, checksum computation (SHA-256).
3. **Classification:** Tag document with workspace classification and disclosure tier defaults.
4. **Storage:** Store raw document in object storage with immutable versioning and checksum validation.
5. **Queue extraction:** Create asynchronous extraction job; return job ID to UI.

### 8.2 Extraction Strategy (Layout-Aware)

Extraction must preserve tables and coordinates. The recommended approach is a layout-aware extraction engine with explicit table cell coordinates, operating in a sovereign-compliant environment.

- **Primary extraction (recommended):** A dedicated document intelligence service that outputs tables/cells with bounding boxes.
- **Fallback extraction:** PDF text extraction for digitally-generated PDFs; OCR only for scanned pages.
- **Structured inputs (Excel/CSV):** Bypass OCR and parse directly while still generating evidence references (sheet/cell).

### 8.3 Extracted Data Model (DocumentGraph)

```
DocumentGraph (simplified)
- document_id
- pages: [
    - page_number
    - blocks: [ {text, bbox, type} ]
    - tables: [
        - table_id
        - bbox
        - cells: [ {row, col, text, bbox, confidence} ]
    ]
  ]
- extraction_metadata: {engine, version, started_at, completed_at, errors}
```

### 8.4 BoQ Structuring Pipeline

BoQ structuring converts extracted tables into normalized line items suitable for mapping. This step is deterministic and does not require LLMs.

1. **Table selection:** Identify candidate BoQ/procurement tables (heuristics + optional ML classifier).
2. **Column normalization:** Map headers to canonical fields (description, quantity, unit, unit_price, total_price, year, vendor).
3. **Value parsing:** Parse numeric formats, currencies, and units; detect subtotals and section headers.
4. **Deduplication:** Remove repeated headers and continued tables across pages.
5. **Completeness scoring:** Estimate coverage vs stated totals where available; flag missing sections.
6. **Line item object creation:** Persist BoQLineItem records linked to EvidenceSnippets (page/table/cell).

### 8.5 Evidence Snippet Generation (Automatic)

For every BoQLineItem, ImpactOS generates one or more EvidenceSnippets that point back to the exact source location.

- **PDF sources:** EvidenceSnippet stores (page, bbox) and extracted text.
- **Excel sources:** EvidenceSnippet stores (sheet_name, cell_range) and cell values.
- All snippets include a source checksum to prevent silent replacement.

### 8.6 Quality Failure Modes and Controls

| Failure Mode | Impact | Control |
|---|---|---|
| Row loss in long tables | Missing spend lines → underestimation | Layout-aware extraction; row counts validated; completeness scoring. |
| Column misalignment | Amounts mapped to wrong fields | Schema validation + rule checks (e.g., totals = qty × unit_price). |
| OCR errors in scanned BoQs | Bad numbers and descriptions | Confidence thresholds; mandatory HITL review for low-confidence cells. |
| Ambiguous categories | Incorrect sector mapping | HITL reconciliation; unresolved items bucketed as explicit assumptions. |
| Multi-currency documents | Incorrect scaling | Currency detection + explicit conversion assumptions logged in AssumptionRegister. |

---

## 9. Scenario Compiler (Doc → Shock)

The Scenario Compiler converts structured spend lines and policy inputs into a ScenarioSpec that the deterministic engine can execute. It is the primary productivity moat: it reduces weeks of manual mapping work to hours with controlled analyst review.

### 9.1 Inputs

- BoQDataset and BoQLineItems (from extraction pipeline).
- Scenario intent (natural language brief and/or structured parameters).
- Sector taxonomy and concordances (official to Strategic Gears internal taxonomy).
- Mapping Library (procurement category ↔ sector patterns) with versioning.
- Import/local content assumptions (defaults from assumption library or client-provided targets).
- Phasing schedule and deflators (if the scenario spans multiple years).

### 9.2 Outputs

- **ScenarioSpec (versioned):** Includes shock items, assumptions, and DataQualitySummary.
- **Mapping audit trail:** Line-item mapping decisions with confidence, approver, and override reason.
- **Residual/unresolved buckets:** Explicit assumptions for uncovered or ambiguous portions.
- **Disclosure tier tag:** Default tier for scenario artifacts and narrative drafts.

### 9.3 Compilation Steps (Deterministic + AI-Assisted)

Compilation is split into deterministic steps and AI-assisted steps. AI is used for classification and drafting; deterministic code is used for aggregation, arithmetic, and consistency checks.

1. **Deterministic:** Normalize amounts, currencies, years; detect totals; compute coverage metrics.
2. **AI-assisted:** Propose sector mappings for line items; propose domestic/import split for ambiguous procurement; draft assumption rationales.
3. **Deterministic:** Aggregate mapped line items into sector-year shocks (Δd_t), apply deflators, and produce final shock vectors.
4. **HITL:** Analyst reviews/overrides mappings and key assumptions before ScenarioSpec becomes eligible for governed runs.

### 9.4 Handling Ambiguity and Incomplete Information

| Situation | System Behavior | Governance Outcome |
|---|---|---|
| BoQ coverage < 80% of stated total | Create residual bucket for uncovered spend with a sensitivity range. | Residual becomes explicit Assumption; must be approved for governed export. |
| Conflicting totals across documents | Flag contradiction; require manager decision; record decision log. | Decision recorded in AssumptionRegister with evidence links. |
| Low-confidence mapping suggestion | Route to HITL queue; require analyst selection. | Cannot be auto-approved; remains unresolved until mapped. |
| Multi-year phasing unclear | Propose default phasing template; require analyst confirmation. | Phasing becomes assumption with range (front-loaded vs back-loaded). |

### 9.5 Confidence Thresholds and Escalation

- **High-confidence mappings (>= 0.85):** Eligible for bulk-approval by analyst with one action.
- **Medium-confidence mappings (0.60–0.85):** Require spot-check sampling and/or targeted review.
- **Low-confidence mappings (< 0.60):** Must be explicitly resolved in HITL UI; cannot be auto-applied.
- Disputes or politically sensitive assumptions escalate to Delivery Lead / Partner Sponsor within 48 hours.

### 9.6 Learning Loop: Improving Mapping Suggestions Over Time

Analyst overrides are treated as training signals. ImpactOS stores override pairs (suggested → final) with context and uses them to improve mapping suggestions in later engagements.

- Store feature context: line-item text, supplier category, project type, client sector, and taxonomy version.
- Periodic retraining (Phase 2): update mapping suggestion model and publish a new MappingLibraryVersion.
- Governance: model updates are versioned; historical runs remain reproducible via RunSnapshot references.

---

## 10. AI/Agent Layer: Depth Engine, Drafting, and Guardrails

ImpactOS uses AI to accelerate scenario design, mapping suggestions, narrative drafting, and evidence linking. All AI usage is governed by strict schemas, tiered disclosure policies, and the No Free Facts publication gate.

### 10.1 Agent Orchestration Model

- Agents are orchestrated as a workflow graph (state machine) executed by the orchestrator service.
- Each agent has a single responsibility and produces a typed artifact (JSON) stored in the workspace.
- Agents are stateless at runtime; all state is persisted in the database/object store for auditability.
- Prompt packs are versioned (PromptPackVersion) and captured in RunSnapshots for reproducibility.

### 10.2 Al-Muhāsibī Depth Engine (Structured Artifacts)

The Depth Engine operationalizes the Al-Muhāsibī framework as a set of agents. It produces auditable artifacts rather than hidden reasoning. The Al-Muhāsibī methodology, framework, and underlying intellectual property remain the property of Salim Al-Barami, licensed to Strategic Gears for use within ImpactOS.

| Step | Agent | Output Artifact | Schema Guarantee |
|---|---|---|---|
| 1 — Khawāṭir | Idea Generator | CandidateDirections[] labeled nafs/waswās/insight | Each direction includes a test plan and required levers. |
| 2 — Murāqaba | Bias/Assumption Auditor | BiasRegister + AssumptionDrafts | Assumptions must be explicit objects; no free claims. |
| 3 — Mujāhada | Contrarian Generator | ContrarianDirections[] with broken-assumption tags | Must specify whether quantified or qualitative-only. |
| 4 — Muhāsaba | Novelty/Decision Scorer | Shortlist (>=7 novelty) + Rejections | Scores + rationale captured for review. |
| 5 — Suite Plan | Scenario Suite Planner | ScenarioSuitePlan (runs, sensitivities, tiers) | Output is executable RunPlan JSON. |

### 10.3 Quantified vs Qualitative Contrarian Insights

Agents may identify second-order risks that the deterministic engine cannot quantify (e.g., wage inflation feedback). These are captured as QualitativeRisk objects and attached to scenarios, explicitly labeled as not modeled.

```json
{
  "risk_id": "uuid",
  "title": "Wage inflation pressure in construction",
  "description": "...",
  "trigger_conditions": ["peak simultaneous build across giga-projects"],
  "expected_direction": "reduces feasible employment / increases import leakage",
  "modeled_quantitatively": false,
  "disclosure_tier": "TIER0|TIER1|TIER2"
}
```

### 10.4 Retrieval-Augmented Evidence (RAG) for Governance

- Evidence retrieval is restricted to the engagement corpus (and optionally an approved public corpus).
- Retrieved evidence is stored as EvidenceSnippets with bounding boxes and checksums; citations are never free-text URLs only.
- Agent outputs that reference facts must include evidence pointers; otherwise they must mark the statement as an assumption.

### 10.5 Tiered Disclosure Enforcement

- **Tier 0:** Internal-only red-team scenarios and sensitive findings.
- **Tier 1:** Client technical working team artifacts (assumption-heavy details).
- **Tier 2:** Boardroom-ready outputs (controlled framing and aggregation).
- **Default rule:** Contrarian outputs start at Tier 0 until manager approval elevates them.

### 10.6 AI Safety and Appropriateness Controls

- Policy rules prohibit generation of certain content categories and enforce professional tone and confidentiality.
- Client-specific sensitivity rules can be configured per workspace (e.g., disclosure restrictions).
- All AI drafts are reviewable; the system never auto-publishes client-facing narratives without governance pass.

---

## 11. User Interface Workflows and State Machines

Adoption depends on ergonomics. The UI must be optimized for consultant workflows under time pressure: bulk approvals, keyboard-first reconciliation, instant preview of impacts, and clear governance status.

### 11.1 HITL Mapping Reconciliation (BoQ Line Items)

The mapping reconciliation UI is designed for "Tinder-style" rapid decisions: approve, override, or defer. Every decision is auditable and versioned.

#### 11.1.1 Line Item Mapping State Machine

| State | Description | Allowed Actions | Next States |
|---|---|---|---|
| UNMAPPED | Line item exists but no sector mapping. | Request AI suggestion; manual map; exclude | AI_SUGGESTED / APPROVED / EXCLUDED |
| AI_SUGGESTED | One or more candidate sector mappings with confidence. | Approve; override; request alternatives; escalate | APPROVED / OVERRIDDEN / MANAGER_REVIEW |
| APPROVED | Analyst accepted a suggested mapping. | Edit (creates new decision); lock for run | OVERRIDDEN / LOCKED |
| OVERRIDDEN | Analyst selected a different mapping than suggested. | Provide rationale; lock for run | LOCKED / MANAGER_REVIEW |
| MANAGER_REVIEW | Sensitive or disputed mapping awaiting manager decision. | Approve decision; revise; set disclosure tier | LOCKED / AI_SUGGESTED / OVERRIDDEN |
| EXCLUDED | Line item excluded from scenario scope (with reason). | Re-include; map | UNMAPPED / AI_SUGGESTED |
| LOCKED | Mapping locked for a governed run snapshot. | Unlock (creates new ScenarioSpec version) | APPROVED / OVERRIDDEN |

#### 11.1.2 Speed Ergonomics Requirements

- Keyboard shortcuts for approve/override/escalate; bulk-approve by confidence threshold.
- Side-by-side evidence preview (PDF page crop) for any line item; one click to open source location.
- Inline sector search with taxonomy hierarchy navigation and concordance hints.
- Instant recalculation of sector-year totals as mappings change; real-time feedback loop.

### 11.3 NFF Governance UI

#### 11.3.1 Claim State Machine

| State | Description | Resolution Actions | Next States |
|---|---|---|---|
| EXTRACTED | Claim extracted from draft narrative/template. | Classify claim type; request evidence | NEEDS_EVIDENCE / ASSUMPTION / RECOMMENDATION |
| NEEDS_EVIDENCE | Claim appears factual but lacks evidence link. | Retrieve evidence; rewrite; delete | SUPPORTED / REWRITTEN_AS_ASSUMPTION / DELETED |
| SUPPORTED | Claim linked to EvidenceSnippets or model Run outputs. | Manager approve for tier; publish | APPROVED_FOR_EXPORT |
| REWRITTEN_AS_ASSUMPTION | Claim converted to explicit assumption with range. | Approve assumption; publish with sensitivity | APPROVED_FOR_EXPORT |
| DELETED | Claim removed from deliverable due to lack of support. | N/A | DELETED |
| APPROVED_FOR_EXPORT | Claim cleared for inclusion in governed export. | Locked for export | APPROVED_FOR_EXPORT |

### 11.4 Sandbox vs Governed Mode Enforcement

- Sandbox runs allow exploration with unapproved assumptions; all exports are watermarked "DRAFT — FAILS NFF GOVERNANCE".
- Governed runs require: (a) approved assumptions, (b) resolved claims, (c) locked mappings, and (d) a valid RunSnapshot.
- The export service enforces these rules centrally; UI cannot bypass them.

---

## 12. Governance, Audit, and Reproducibility

ImpactOS is designed for environments where outputs may be audited months or years later. This section specifies the mechanisms for immutable runs, controlled updates, and export integrity.

### 12.1 Run Snapshot Immutability

- Each Run ID is immutable and references exact versions of: ModelVersion, TaxonomyVersion, ConcordanceVersion, MappingLibraryVersion, AssumptionLibraryVersion, PromptPackVersion, and (if used) ConstraintSetVersion.
- Any change to mappings, assumptions, or base models creates a new ScenarioSpec version and a new Run ID; historical runs remain untouched.
- RunSnapshots also capture checksums for all input sources (documents and datasets) used in compilation and evidence.

### 12.2 Deterministic Output Signatures

- Compute checksums (SHA-256) for exported PPT/Excel/PDF files and store them with the Export record.
- Optionally sign exports with an organizational signing key (KMS-backed) to provide non-repudiation.
- Embed run metadata in exports (run_id, model_version, scenario_version) in a visible footer and in hidden metadata.

### 12.3 Excel Escape Hatch (Controlled Ejection)

- Governed Excel exports include a Run ID, input vectors, and linked formulas that reproduce core calculations.
- The workbook includes an integrity signature (hash of key ranges) stored in a hidden sheet.
- If the workbook is modified outside ImpactOS, the signature fails; the workbook is automatically labeled "OUTSIDE GOVERNANCE" if re-imported or attached to a governed export request.
- A re-import workflow can reconcile manual changes back into a ScenarioSpec version with full audit trail (optional extension).

### 12.4 Variance Bridges Between Scenario Versions

- Decompose changes in totals into drivers: phasing changes, mapping changes, assumption changes (import share/local content), constraint activation, model version changes.
- Generate a waterfall dataset for reporting (and optional chart) stored with the RunResult comparison record.
- Variance bridges are governed: they reference the two Run IDs and the diffs between their snapshots.

### 12.5 Retention and Deletion Policies

- Retention is configurable per workspace classification (e.g., 7+ years for government/PIF work).
- Deletion is controlled by policy; evidence sources may be retained longer than derived artifacts if required.
- All deletion actions are logged and require elevated approval.

---

## 13. Security, Privacy, and Saudi Compliance Posture

ImpactOS is intended for sensitive strategic engagements. The platform must align with Saudi security expectations (including NCA Essential Cybersecurity Controls — ECC) and with Strategic Gears' contractual confidentiality obligations.

### 13.1 Data Classification and Handling

- Every workspace is assigned a classification level (e.g., Public, Internal, Confidential, Restricted).
- Classification governs: AI routing, export permissions, retention period, and logging requirements.
- Documents and derived artifacts inherit classification by default; overrides require manager approval and are audit logged.

### 13.2 Identity, Access, and Segregation

- SSO integration (OIDC/SAML) with MFA enforced at the IdP level.
- Role-based access control (RBAC) scoped per workspace; least privilege by default.
- Separation of duties: model stewardship, evidence stewardship, and publication approval roles are distinct.
- Network segregation between presentation, application, and data zones; restricted processing zone for high sensitivity cases.

### 13.3 Encryption and Key Management

- Encryption in transit (TLS 1.2+ or higher) for all service-to-service and client connections.
- Encryption at rest for databases and object storage; customer-managed keys recommended for sensitive work.
- Centralized key management via KMS/HSM; signing keys for export signatures stored in KMS.

### 13.4 Logging, Monitoring, and Audit

- Centralized audit log capturing: document access, mapping decisions, assumption approvals, run execution, and exports.
- Security logs integrated with SIEM; anomaly detection for unusual access patterns.
- Immutable logging for RunSnapshots and governed exports (write-once semantics where possible).

### 13.5 Secure AI Usage (Sovereign AI Posture)

- Do not transmit restricted client documents to non-approved external endpoints.
- Prefer enterprise AI services with contractual zero data retention and in-country deployment where required.
- Provide a local-model option for highly sensitive work (on-prem/VPC).
- Implement DLP checks and allowlisted outbound policies for any external AI calls.

### 13.6 NCA ECC Alignment (Control Mapping)

| ECC Domain (illustrative) | ImpactOS Control | Implementation Notes |
|---|---|---|
| Identity & Access Management | SSO + MFA + RBAC per workspace | Role separation; privileged access reviews. |
| Asset & Data Management | Classification tags + retention policies + immutable document versions | Checksums prevent silent replacement. |
| Network Security | Zone segmentation + restricted processing zone + egress allowlisting | WAF at edge; no public DB access. |
| Cryptography | TLS in transit + encryption at rest + KMS-managed keys | Customer-managed keys for restricted work. |
| Logging & Monitoring | Centralized audit log + SIEM integration | RunSnapshots and exports are auditable objects. |
| Vulnerability Management | SAST/DAST + patch cadence + container scanning | Policy-driven dependency updates. |
| Incident Response | Runbooks + alerting + evidence preservation | Support forensic reconstruction of access and exports. |
| Business Continuity | Backups + restore testing + defined RPO/RTO | Higher availability tiers optional. |

---

## 14. Observability, Operations, and Support Model

ImpactOS must operate as a reliable internal product. This section defines operational telemetry, run lifecycle management, and the stewardship roles needed for sustainability.

### 14.1 Observability (Metrics, Logs, Traces)

- **Key metrics:** Scenario run durations, batch throughput, extraction job times, NFF resolution rates, export success rates.
- **Service health:** CPU/memory, queue depth, database latency, object store IO.
- **User metrics:** Active users, mapping throughput, time-to-first-result, adoption of sandbox vs governed.
- **Distributed tracing:** Across ingestion → compilation → run → governance → export pipelines.

### 14.2 Run Lifecycle Management

- **State model:** QUEUED → RUNNING → COMPLETED / FAILED; governed runs may also be BLOCKED by NFF gate.
- **Retry policy:** Deterministic compute steps can be retried safely (idempotent); governance state is persisted.
- **Partial failure handling:** Extraction failures isolate to document; scenarios can proceed with explicit coverage assumptions if approved.

### 14.3 Stewardship Roles (Operational)

- **Model Steward:** Curates ModelVersions, concordances, nowcasting inputs, and publishes release notes.
- **Evidence Steward:** Curates approved sources, validates evidence packs, and manages citation standards.
- **Quality Gate Owner:** Manages NFF policy, approves waiver requests, and audits governed exports.
- **Escalation:** Unresolved disputes escalate to Delivery Lead / Partner Sponsor within 48 hours (decision recorded).

### 14.4 Maintenance and Release Management

- Release cadence: monthly minor releases and quarterly major releases (adjustable).
- Change control: schema changes are backward compatible or versioned; migrations are tested on staging.
- Prompt pack versioning: changes to prompts are released as new PromptPackVersion; historical runs remain reproducible.
- Template versioning: Decision Pack templates are versioned; exports store the template version used.

---

## 15. Testing, Quality Assurance, and Acceptance Criteria

Given the decision-critical nature of outputs, ImpactOS requires a rigorous testing approach that covers numerical correctness, schema validity, governance enforcement, and export fidelity.

### 15.1 Test Pyramid

- **Unit tests:** Matrix routines, deflator logic, satellite transforms, RAS balancing, and validation checks.
- **Schema tests:** JSON schema/Pydantic validation for all payloads; negative tests for malformed AI outputs.
- **Integration tests:** Ingestion → extraction → BoQ structuring → mapping → ScenarioSpec assembly.
- **End-to-end tests:** Run scenario → produce ResultSet → resolve claims → export Decision Pack.
- **Regression tests:** Golden-model runs with fixed inputs to detect drift across releases.

### 15.2 Numerical Correctness and Regression Strategy

- Use known small matrices with hand-verifiable outputs as baseline unit tests.
- Maintain golden ModelVersions and ScenarioSpecs for regression; store expected ResultSet hashes within tolerance.
- Define numerical tolerances explicitly (e.g., absolute/relative tolerances for Δx and multipliers).
- Validate non-negativity and sanity constraints for each run; fail fast on invalid conditions.

### 15.3 Governance Enforcement Tests (NFF)

- Claims without evidence must not pass governed export.
- Claims rewritten as assumptions must appear in the AssumptionRegister with ranges and approvals.
- Sandbox exports must always include watermarking and must not be labeled as governed.
- RunSnapshots must remain immutable; attempts to mutate snapshot references must fail.

### 15.4 Performance and Load Testing

- Load test batch runs (50–500 scenarios) with realistic sector counts (e.g., 40–120) and satellite metrics.
- Stress test extraction pipeline with large PDFs (100–500 pages) and concurrent jobs.
- Measure UI mapping throughput (line items/hour) and ensure it beats Excel baseline for typical projects.

### 15.5 Phase Acceptance Gates

#### 15.5.1 Phase 1 Gate (after 3 pilot engagements)

- Cycle time improvement >= 2x (target 3–5x) compared to baseline time-motion study.
- Scenario throughput >= 3x (number of scenarios and sensitivities delivered).
- Reduction in revision cycles attributable to sourcing disputes (tracked via governance metrics).
- No critical security issues identified in penetration testing and threat modeling review.

#### 15.5.2 Phase 2 Gate

- Scenario Compiler achieves high-confidence auto-mapping rate >= 60% for typical BoQs (with HITL override).
- Feasibility layer produces consistent unconstrained vs feasible outputs with interpretable binding constraints.
- Workforce/Saudization satellite produces confidence-labeled splits and sensitivity envelopes accepted by delivery leadership.

---

## 16. Implementation Plan (Engineering Roadmap)

This section translates the concept phases into implementable engineering milestones. Exact sprint plans depend on Strategic Gears resourcing and infrastructure decisions.

### 16.1 Phase 1 (MVP) — Build Order

- **MVP-1:** Workspace/RBAC foundation + document ingestion + object storage + audit logging.
- **MVP-2:** Extraction pipeline MVP (DocumentGraph) + BoQ structuring + EvidenceSnippet generation.
- **MVP-3:** Deterministic I-O engine + ModelVersion management + batch run capability + ResultSet schema.
- **MVP-4:** HITL reconciliation UI + mapping state machine + ScenarioSpec versioning.
- **MVP-5:** NFF governance MVP (claim ledger + assumption register + basic evidence linking) + sandbox/governed gate.
- **MVP-6:** Reporting/export engine MVP (Decision Pack templates) + Excel escape hatch + watermarking.
- **MVP-7:** Pilot enablement: baseline study instrumentation, training materials, and support runbooks.

### 16.2 Phase 2 — Moat Modules

- Document-to-shock Scenario Compiler automation: mapping suggestion models + domestic/import split heuristics + phasing/deflators.
- Al-Muhāsibī Depth Engine: agent workflow graph + artifact storage + tiered disclosure tagging.
- Feasibility/constraint engine: constraint schema + solver integration + binding constraint diagnostics.
- Nowcasting (RAS) utility: target totals ingestion + balancing engine + ModelVersion publication workflow.
- Workforce/Saudization satellite: sector→occupation bridge methodology + confidence labeling + sensitivity defaults.
- Library flywheel: publish MappingLibraryVersion and AssumptionLibraryVersion release workflow.

### 16.3 Phase 3 — Premium Modules

- Client portal (controlled collaboration): assumption sign-off, scenario comparison dashboard, evidence browsing.
- Structural path analysis and chokepoint analytics.
- Portfolio optimization and goal-seeking workflows.
- Live workshop dashboard (slider-driven scenario adjustments) with governance-safe exports.
- Advanced variance bridges and executive explainability outputs.

### 16.4 Key Engineering Risks and Mitigations

| Risk | Why it Matters | Mitigation |
|---|---|---|
| Document table extraction quality | BoQ loss/misalignment undermines everything downstream | Use layout-aware extraction, completeness scoring, mandatory HITL for low-confidence. |
| AI hallucinations in drafts | Credibility risk in client outputs | NFF gate + schema validation + evidence-only retrieval. |
| Adoption failure (Excel reversion) | Tool unused despite build | Sandbox + Excel escape hatch + deck-template fidelity + partner sponsor enforcement. |
| Model vintage criticism | Clients reject outputs based on old base tables | RAS nowcasting + explicit DataQualitySummary and sensitivity envelopes. |
| Sovereignty constraints limit AI options | May restrict cloud LLM usage | Local model option and routing policy by classification. |

---

## Appendix A. Shock Item Schemas (Illustrative)

Shock items define how a scenario changes the economy. The deterministic engine supports a limited set of quantified levers; all other effects are captured as qualitative risks.

```json
// 1) FinalDemandShock
{
  "type": "FINAL_DEMAND_SHOCK",
  "sector_code": "C41-C43",
  "year": 2027,
  "amount_real_base_year": 1500000000,
  "domestic_share": 0.65,
  "import_share": 0.35,
  "evidence_refs": ["snippet_id_1", "snippet_id_2"]
}

// 2) ImportSubstitutionShock
{
  "type": "IMPORT_SUBSTITUTION",
  "sector_code": "C24",
  "year": 2028,
  "delta_import_share": -0.10,
  "assumption_ref": "assumption_id"
}

// 3) LocalContentChange
{
  "type": "LOCAL_CONTENT",
  "sector_code": "C33",
  "year": 2029,
  "target_domestic_share": 0.60,
  "assumption_ref": "assumption_id"
}

// 4) ConstraintOverride (Phase 2)
{
  "type": "CONSTRAINT_OVERRIDE",
  "sector_code": "F",
  "year": 2028,
  "cap_output": 0.12,
  "cap_jobs": 15000,
  "confidence": "HARD|ESTIMATED|ASSUMED"
}
```

---

## Appendix B. Assumption Schema (Illustrative)

```json
{
  "assumption_id": "uuid",
  "type": "IMPORT_SHARE|PHASING|DEFLATOR|WAGE_PROXY|CAPACITY_CAP|JOBS_COEFF",
  "value": 0.35,
  "range": {"min": 0.25, "max": 0.45},
  "units": "fraction",
  "justification": "Derived from trade structure benchmarks; adjusted for project profile.",
  "evidence_refs": ["snippet_id_9"],
  "status": "DRAFT|APPROVED|REJECTED",
  "approved_by": "user_id|null",
  "approved_at": "timestamp|null"
}
```

---

## Appendix C. Claim and Evidence Schemas (Illustrative)

```json
// Claim
{
  "claim_id": "uuid",
  "text": "Scenario increases total output by SAR 12.4bn (real 2023).",
  "claim_type": "MODEL|SOURCE_FACT|ASSUMPTION|RECOMMENDATION",
  "status": "EXTRACTED|NEEDS_EVIDENCE|SUPPORTED|REWRITTEN_AS_ASSUMPTION|DELETED|APPROVED_FOR_EXPORT",
  "disclosure_tier": "TIER0|TIER1|TIER2",
  "model_refs": [{"run_id":"uuid","metric":"total_output","value":12400000000}],
  "evidence_refs": ["snippet_id_1"]
}

// EvidenceSnippet
{
  "snippet_id": "uuid",
  "source_id": "uuid",
  "page": 17,
  "bbox": {"x0":0.12,"y0":0.44,"x1":0.88,"y1":0.53},
  "extracted_text": "Total CAPEX: SAR 10,000,000,000 ...",
  "table_cell_ref": {"table_id":"t-3","row":12,"col":4},
  "checksum": "sha256:..."
}
```

---

## Appendix D. Run Plan Schema (Depth Engine Output)

```json
{
  "suite_id": "uuid",
  "base_scenario_spec_id": "uuid",
  "runs": [
    {"name":"Base","scenario_version":3,"mode":"SANDBOX","sensitivities":["S1","S2"],"tier":"TIER1"},
    {"name":"Import stress","scenario_version":4,"mode":"SANDBOX","sensitivities":["S1"],"tier":"TIER0"},
    {"name":"Feasible cap","scenario_version":5,"mode":"SANDBOX","constraints":"CSET-1","tier":"TIER0"}
  ],
  "recommended_outputs": ["multipliers","sector_impacts","jobs","imports","variance_bridge"],
  "notes": "Contrarian runs are Tier 0 until manager approval."
}
```

---

## Appendix E. Open Decisions

- Final choice of extraction engine and whether it must run fully in-Kingdom for all classifications.
- Vector store choice (pgvector vs dedicated) based on scale and governance needs.
- Exact constraint solver approach (LP/QP) and data availability for caps.
- Arabic output template scope and timeline.
- Client portal scope and authentication model (Strategic Gears-hosted vs client-hosted).

---

*End of Document*
