# ImpactOS — Data, Sources, and API Build Pack (v1.0)

**Document type:** Engineering build pack (Markdown)  
**Scope:** Data inventory, source registry, ingestion/access patterns, and internal API surface for ImpactOS.  
**Audience:** Product, data engineering, backend, frontend, security, and analytics teams.  
**Applies to:** Strategic Gears internal deployment (Saudi-focused), with optional regional extensions.  
**Last updated:** 2026-02-26

---

## Table of contents

1. [Purpose and scope](#1-purpose-and-scope)  
2. [Minimum viable data checklist by phase](#2-minimum-viable-data-checklist-by-phase)  
3. [Data requirements (what data the system needs)](#3-data-requirements-what-data-the-system-needs)  
4. [Source registry (where the data can come from)](#4-source-registry-where-the-data-can-come-from)  
5. [Data access and ingestion patterns](#5-data-access-and-ingestion-patterns)  
6. [Internal APIs (ImpactOS)](#6-internal-apis-impactos)  
7. [External source APIs and access notes (optional)](#7-external-source-apis-and-access-notes-optional)  
8. [Appendix A — Core entities and required fields](#8-appendix-a--core-entities-and-required-fields)  
9. [Appendix B — Standard response envelopes](#9-appendix-b--standard-response-envelopes)  

---

## 1) Purpose and scope

This file is a **single reference** for:

- **All data required** to run ImpactOS end-to-end (model core, scenario compiler, feasibility constraints, workforce satellite, governance/NFF).
- **Trusted sources** and access patterns for Saudi-relevant datasets (plus ESCWA and international benchmarks).
- A **complete internal API surface** (endpoints + payload schemas + examples) suitable for an initial OpenAPI implementation.

**Non-goals**
- This is not the full technical spec (deployment topology, UI designs, or code-level implementation).
- This does not prescribe a single vendor solution for document extraction or AI hosting; it defines interface needs.

---

## 2) Minimum viable data checklist by phase

### Phase 1 — MVP (productivity + minimum governance)
**Required**
- Sector taxonomy (official + internal consulting taxonomy)
- Base IO model (at least `Z` and `x`; ideally full IO/SUT blocks)
- Scenario specs (manual/semi-automated)
- Document storage for evidence + extraction metadata (even if extraction is manual at first)
- Run snapshots (reproducibility)
- Assumption register
- Minimal claim ledger + evidence linking (NFF “lite”)
- Export templates (PPTX/Excel) with watermarking for sandbox outputs

**Optional (but high value)**
- Import leakage blocks / imports by sector
- Basic employment coefficients (jobs per SAR output)

### Phase 2 — Moat build (compiler + depth + feasibility + nowcasting + workforce)
**Required**
- Automated doc-to-line-item extraction pipeline (or integrated service)
- Mapping library (line items → sector codes) with HITL feedback loop
- Data Quality Summary (coverage %, mapping confidence distribution, base vintage, gaps)
- Feasibility constraints (capacity/ramp and at least one labor constraint input)
- Nowcasting / matrix balancing inputs (RAS totals)
- Workforce bridging methodology artifacts + confidence labels

### Phase 3 — Premium (client portal + chokepoints + optimization)
**Required**
- Client-facing read-only portal data views (assumption sign-off, scenario comparisons, evidence pack browser)
- Structural path / chokepoint outputs stored as first-class artifacts
- Portfolio/goal-seeking inputs (initiative library, objective weights, constraints)

---

## 3) Data requirements (what data the system needs)

### 3.1 Reference data (shared across modules)

#### 3.1.1 Sector taxonomy
**Purpose:** Consistent sector codes for model, mapping, reporting, and governance.

**Required fields**
- `sector_code` (string) — stable identifier (e.g., ISIC rev.4 code or internal code)
- `sector_name_en`, `sector_name_ar` (strings)
- `level` (enum: section/division/group/class/custom)
- `parent_sector_code` (nullable string)
- `is_active` (bool)
- `valid_from`, `valid_to` (dates, nullable)
- `notes` (string)

**Optional**
- `isic_code`, `cpc_code` crosswalks
- synonyms / keywords for mapping assistance

#### 3.1.2 Concordance / crosswalk tables
**Purpose:** Map between taxonomies (official ↔ internal; sector ↔ product; product ↔ HS; etc.)

Examples:
- `official_sector_code` ↔ `sg_sector_code`
- `spend_category_code` ↔ `sg_sector_code`
- `hs6_code` ↔ `product_category_code`

#### 3.1.3 Geography and organizations
- Saudi administrative regions (if downscaling is used)
- Client organizations and engagement identifiers (workspace scoping)

#### 3.1.4 Currency, deflators, and time
**Required**
- `currency_code` (e.g., SAR)
- Base-year definition (`base_year`)
- Deflator series (CPI/GDP deflator, and optionally sector deflators):
  - `series_id`, `year`, `index_value`, `base_year`

---

### 3.2 Model Core data (IO engine)

ImpactOS should store **raw**, **curated**, and **derived** model components.

#### 3.2.1 Minimal Leontief inputs (minimum viable)
- `Z` — intermediate transactions matrix (n×n)
- `x` — gross output vector (n)

Derived:
- `A = Z * diag(x)^{-1}`
- `B = (I - A)^{-1}`

#### 3.2.2 Recommended IO/SUT blocks (better defensibility and richer outputs)
- Intermediate matrix `Z`
- Final demand matrix `F` (n×k; k categories like HH/GOV/INV/EXP)
- Imports by sector and/or product (`m`)
- Value added components by sector (compensation, operating surplus, taxes less subsidies)
- Margins/taxes blocks if using purchaser-to-basic conversions (optional)

**Model metadata**
- `model_id`, `model_version_id`
- `country` (Saudi Arabia)
- `year` (base year)
- `price_basis` (basic / purchasers)
- `unit` (SAR; million SAR)
- `source` (official / balanced-nowcast / client augmented)
- `vintage_years_old` (computed)
- `qa_flags` (balances, negatives, stability)

#### 3.2.3 Nowcasting / RAS balancing inputs (Phase 2)
To update an older IO table to a newer year:
- Target row totals and column totals (by sector) for the new year
- Updated macro aggregates (GDP, imports, sector outputs)
- Optional constraints (cells fixed or bounded)

Outputs:
- Balanced `Z'` and `x'`
- New `model_version_id` (explicitly labeled as “balanced-nowcast”)

---

### 3.3 Scenario Compiler data (Doc → Shock)

#### 3.3.1 Document corpus (evidence inputs)
Documents may include:
- Bills of Quantities (BoQs), CAPEX/OPEX tables
- Procurement lists
- Policy documents / strategy text
- Client spreadsheets

**Document metadata required**
- `doc_id`, `workspace_id`
- `doc_type` (boq/capex/policy/other)
- `source_type` (client/public/internal)
- `classification` (public/internal/confidential/restricted)
- `language` (en/ar/bilingual)
- `hash_sha256` (immutability)
- `uploaded_by`, `uploaded_at`

#### 3.3.2 Extraction outputs (structured line items)
Each line item should store:
- `line_item_id`
- `doc_id`, `extraction_id`
- `raw_text`
- `quantity`, `unit_price`, `total_value` (nullable)
- `currency_code`
- `year_or_phase` (nullable)
- `vendor` (nullable)
- `category_code` (nullable)
- `page_ref` (page number) + location pointer (for evidence)

#### 3.3.3 Mapping suggestions and decisions (HITL)
For each line item:
- `suggested_sector_code`
- `suggested_confidence` (0–1)
- `suggestion_explanations` (short tokens, not chain-of-thought)
- Analyst decision:
  - `final_sector_code`
  - `decision_type` (approved/overridden/deferred/residual_bucket)
  - `decision_note`
  - `decided_by`, `decided_at`

#### 3.3.4 Scenario parameters
- Shock type(s):
  - `final_demand_delta` (Δd) by sector/year
  - `import_share_adjustment`
  - `local_content_target`
  - `productivity_adjustment` (ΔA)
- Time phasing:
  - annual profile (year → share)
- Deflation:
  - nominal → base-year conversion rule and series used
- Disclosure tier:
  - Tier 0 internal-only / Tier 1 technical / Tier 2 boardroom
- Mode:
  - `sandbox` or `governed`

#### 3.3.5 Data Quality Summary (always produced)
A scenario compilation should output:
- `base_model_vintage_years_old`
- `document_coverage_pct` (e.g., evidenced CAPEX / total CAPEX)
- `mapping_confidence_histogram` (high/med/low %)
- `unmapped_value_pct` (residual bucket)
- `key_gaps` (list)
- `constraint_confidence` summary (if constraints attached)

---

### 3.4 Feasibility / constraint layer data

Constraints must be explicit and labeled by confidence.

**Constraint categories**
- Sector capacity caps (max output growth per year, max absolute output)
- Ramp constraints (min/max year-on-year changes)
- Labor availability (max jobs by skill group, max Saudis available)
- Import/logistics bottlenecks (max imported inputs growth, port capacity proxies)
- Project/program constraints (budget ceilings, timing gates)

**Required fields**
- `constraint_set_id`, `workspace_id`, `model_version_id`
- `constraint_type` (capacity/ramp/labor/import/budget/other)
- `applies_to` (sector_code / group / all)
- `value`, `unit`
- `time_window` (year range)
- `confidence_level` (hard/estimated/assumed)
- `evidence_links` (optional)
- `owner` (client/steward)
- `notes`

---

### 3.5 Workforce & Saudization satellite data

This module is Saudi-critical but must be transparent about uncertainty early on.

**Core datasets**
- Employment coefficients by sector (jobs per SAR output), by year
- Sector→occupation bridge matrix (sector_code × occupation_code)
- Saudization feasibility tags (occupation/skill → tiers: ready/trainable/expat-reliant)
- Training pipeline data (capacity, duration, throughput) — optional but powerful
- Wage distribution by occupation/sector — optional (can inform constraint/risk narratives)

**Required fields**
- `employment_coeff_id`, `sector_code`, `year`, `jobs_per_million_sar`, `source`, `confidence`
- `bridge_id`, `sector_code`, `occupation_code`, `share`, `source`, `confidence`
- `saudization_rule_id`, `occupation_code`, `tier`, `rationale`, `source`, `confidence`

**Important implementation note**
- In early iterations, the “Saudi-ready/trainable/expat-reliant” split will be **assumption-heavy** and must carry:
  - explicit `confidence` labels
  - sensitivity ranges
  - improvement loop via analyst overrides + library updates

---

### 3.6 Governance / No Free Facts (NFF) data

#### 3.6.1 Evidence objects
Evidence must support claim-level traceability to:
- a document location (page + bounding box / table cell)
- a dataset row (table + primary key)
- a model run artifact (run_id + result_id)

**Required fields**
- `evidence_id`, `workspace_id`
- `evidence_type` (document/dataset/model_run)
- `pointer`:
  - for documents: `{doc_id, page, bbox}` or `{doc_id, table_id, cell_ref}`
  - for datasets: `{dataset_id, primary_key}`
  - for model runs: `{run_id, artifact_id}`
- `excerpt` (<= 1–2 sentences or cell values; avoid large quotes)
- `captured_at`, `captured_by`

#### 3.6.2 Claims ledger
**Required fields**
- `claim_id`, `workspace_id`, `engagement_id`
- `claim_text` (atomic)
- `claim_type` (model_fact/source_fact/assumption/recommendation)
- `status` (supported/rewritten_as_assumption/deleted/pending)
- `needs_evidence` (bool)
- `evidence_ids[]` (0..n)
- `used_in` (slide_id/page_id/section_id)

#### 3.6.3 Assumption register
**Required fields**
- `assumption_id`
- `name`, `description`
- `value`, `unit`
- `range_low`, `range_high` (nullable)
- `rationale`
- `status` (draft/approved/rejected)
- `approved_by`, `approved_at`
- `evidence_ids[]` (optional)
- `linked_to` (scenario_id/run_id)

#### 3.6.4 Run snapshots (reproducibility)
Each run must snapshot:
- base model version
- mapping library version
- assumption library version
- scenario spec version
- constraints set version
- evidence pack version (if governed)
- disclosure tier

---

## 4) Source registry (where the data can come from)

> **Note:** Some sources are public; others require agreements/credentials. Treat this as a registry of *candidate sources* and preferred authoritative references.

### 4.1 Saudi official sources (primary)

#### GASTAT — IO/SUT + national accounts
- **What it provides:** Supply-use tables, input-output tables, national accounts statistics.
- **Primary reference pages:**
  - Methodology & quality report for SUT/IO:  
    `https://stats.gov.sa/en/w/methodology-and-quality-report-for-supply-and-use-tables-and-the-input-output-table`
  - SUT/IO statistics tab landing (publications/methodology):  
    `https://www.stats.gov.sa/en/statistics-tabs/-/categories/419265`
  - Labor market statistics (for workforce calibration inputs):  
    `https://www.stats.gov.sa/en/statistics-tabs/-/categories/417515`
- **Access method:** download tables from portal (manual or automated where permitted).
- **Refresh cadence:** per GASTAT release schedule (IO often periodic; verify per release).

#### Saudi Central Bank (SAMA) — macro/financial + open data portal
- **What it provides:** monetary and financial statistics, exchange rates, etc.
- **Open data portal:**  
  `https://www.sama.gov.sa/en-US/EconomicReports/pages/database.aspx`
- **Portal summary (notes API service exists):**  
  `https://www.sama.gov.sa/en-US/EconomicReports/Pages/Summary.aspx`
- **Monthly statistics portal:**  
  `https://www.sama.gov.sa/en-US/EconomicReports/pages/monthlystatistics.aspx`
- **Access method:** portal downloads and/or portal API (per SAMA documentation).

#### MHRSD — labor market policy + statistics pages
- Ministry homepage:  
  `https://www.hrsd.gov.sa/en`
- Data & statistics landing:  
  `https://www.hrsd.gov.sa/en/knowledge-centre/data-and-statistics`
- **Access method:** public pages + potential secure feeds by agreement (if applicable).

#### GOSI — social insurance statistics
- Statistics & data landing:  
  `https://www.gosi.gov.sa/en/StatisticsAndData`
- **Access method:** public aggregates; detailed records may require agreements.

#### ZATCA — tax/customs statistics & open data
- ZATCA statistics:  
  `https://zatca.gov.sa/en/Pages/Statistics.aspx`
- Open data portal note:  
  `https://zatca.gov.sa/en/e-participation/PublicData/Pages/Datasets-in-Saudi-Open-Data-Portal.aspx`

#### NCA — Essential Cybersecurity Controls (ECC) (security posture alignment)
- ECC controls list page (ECC 2-2024):  
  `https://nca.gov.sa/en/regulatory-documents/controls-list/ecc/`

---

### 4.2 Regional sources (Saudi-relevant enrichment)

#### UN ESCWA — External Trade Data Platform (Arab region)
- Platform landing:  
  `https://www.unescwa.org/portal/external-trade-data-platform`
- Dashboard:  
  `https://etdp.unescwa.org/dashboard/platform.html`
- Trade & industry statistics landing:  
  `https://www.unescwa.org/external-trade-industry-statistics`
- **What it provides:** harmonized Arab trade time series (HS 2017), partner flows, detailed product-level trade.
- **Primary use in ImpactOS:** import leakage assumptions, trade partner splits, regional spillover context, plausibility checks.

#### Arab Development Portal (ESCWA)
- Portal:  
  `https://data.unescwa.org/`

---

### 4.3 International sources (benchmarks + optional enrichment)

#### UN Comtrade
- Portal:  
  `https://comtrade.un.org/`
- **Use:** trade benchmarks, alternative source for HS trade series.

#### UN Statistics Division — SUT/IOT handbook (methodology reference)
- Handbook PDF:  
  `https://unstats.un.org/unsd/nationalaccount/docs/SUT_IOT_HB_Final_Cover.pdf`

#### KAPSARC (benchmark multipliers and IO analysis)
- Example publication referencing Saudi IO tables:  
  `https://www.kapsarc.org/our-offerings/publications/saudi-arabia-s-input-output-table-computing-type-i-multiplier/`

---

### 4.4 Client/internal sources (often the most valuable)
- Project documents: BoQs, procurement schedules, CAPEX/OPEX plans
- Internal engagement memory: mapping overrides, accepted assumption ranges, scenario templates
- Client-provided constraints: capacity plans, labor plans, localization targets

---

## 5) Data access and ingestion patterns

### 5.1 Storage zones (recommended)
- **Raw zone:** immutable copies of source files (documents, tables) + hashes
- **Curated zone:** cleaned, standardized tabular data (parquet/csv) with schema versions
- **Derived zone:** computed artifacts (A, B matrices; run results; scenario vectors)

### 5.2 Versioning and reproducibility (non-negotiable)
- Every **run_id** must snapshot:
  - model_version_id
  - scenario_version_id
  - mapping_library_version_id
  - assumption_library_version_id
  - constraint_set_version_id
  - evidence_pack_version_id (governed runs)
  - disclosure_tier

### 5.3 Data quality scoring (systematic)
Each scenario compilation emits a **Data Quality Summary** that is stored and displayed:
- base model vintage
- document coverage %
- mapping confidence distribution
- residual bucket %
- known gaps
- constraint confidence summary

### 5.4 Learning loop (Phase 2+)
Analyst overrides should feed:
- mapping library improvements
- default assumption ranges
- “most disputed” mappings/assumptions surfaced for steward review

---

## 6) Internal APIs (ImpactOS)

### 6.1 Conventions

**Base URL**
- `https://<impactos-host>/api/v1`

**Auth**
- SSO via OIDC (browser flows) and service-to-service tokens for internal services.
- Every request is workspace-scoped.

**Workspace scoping**
- Prefer path-based scoping:
  - `/v1/workspaces/{workspace_id}/...`

**Idempotency**
- For POST that creates resources: support `Idempotency-Key` header.

**Pagination**
- `limit` + `cursor` (opaque), responses include `next_cursor`.

**Error model**
- Use RFC7807-style `application/problem+json`.

**Modes**
- Most operations accept `mode: "sandbox" | "governed"`.
- Exports to client-ready templates require `mode="governed"` and successful NFF check.

**Disclosure tier**
- `disclosure_tier: 0 | 1 | 2` enforced at export time.

---

### 6.2 API groups and endpoints

> Below is an OpenAPI-like outline in Markdown. All JSON shown is illustrative.

---

#### 6.2.1 Health
**GET** `/v1/health`  
Returns service health.

**200 response**
```json
{"status":"ok","time_utc":"2026-02-26T00:00:00Z","version":"1.0.0"}
```

---

#### 6.2.2 Workspaces and members

**POST** `/v1/workspaces`  
Create a workspace (client/engagement container).

Request:
```json
{"name":"SG - Client X - Engagement Y","country":"SAU","classification":"confidential"}
```

Response:
```json
{"workspace_id":"ws_123","name":"SG - Client X - Engagement Y","created_at":"..."}
```

**GET** `/v1/workspaces`  
List workspaces available to the user.

---

#### 6.2.3 Taxonomies (sectors, occupations, concordances)

**GET** `/v1/workspaces/{workspace_id}/taxonomies/sectors?version=latest`

Response:
```json
{"version":"tax_2026_01","items":[{"sector_code":"C","sector_name_en":"Manufacturing","sector_name_ar":"الصناعات التحويلية"}]}
```

**POST** `/v1/workspaces/{workspace_id}/taxonomies/concordances`  
Upload a crosswalk (official ↔ internal).

---

#### 6.2.4 Models and model versions

**POST** `/v1/workspaces/{workspace_id}/models`  
Create a model container (e.g., “Saudi IO Model”).

Request:
```json
{"name":"Saudi IO Model","country":"SAU","default_currency":"SAR"}
```

**POST** `/v1/workspaces/{workspace_id}/models/{model_id}/versions`  
Create a model version (base-year + matrices + metadata).

Request (minimal):
```json
{
  "year": 2020,
  "unit": "million_SAR",
  "price_basis": "basic",
  "source": "official",
  "sector_taxonomy_version": "tax_2026_01",
  "matrices": {
    "Z": {"storage_ref":"s3://.../Z.parquet"},
    "x": {"storage_ref":"s3://.../x.parquet"}
  }
}
```

Response:
```json
{"model_version_id":"mv_2020_official_v1","status":"ready"}
```

**GET** `/v1/workspaces/{workspace_id}/models/{model_id}/versions/{model_version_id}`  
Return version metadata + QA flags.

**GET** `/v1/workspaces/{workspace_id}/models/{model_id}/versions/{model_version_id}/matrices/{name}`  
Where `{name}` ∈ `Z,x,A,B,F,imports,value_added`.

---

#### 6.2.5 Documents and extraction

**POST** `/v1/workspaces/{workspace_id}/documents`  
Upload a document.

Request (multipart): file + metadata JSON:
```json
{"doc_type":"boq","source_type":"client","language":"en","classification":"restricted"}
```

Response:
```json
{"doc_id":"doc_987","status":"stored","hash_sha256":"..."}
```

**POST** `/v1/workspaces/{workspace_id}/documents/{doc_id}/extract`  
Trigger extraction (tables/line items). Async.

Request:
```json
{"extract_tables":true,"extract_line_items":true,"language_hint":"en"}
```

Response:
```json
{"job_id":"job_extract_001","status":"queued"}
```

**GET** `/v1/workspaces/{workspace_id}/jobs/{job_id}`  
Poll job status (extraction/compile/run/export).

---

#### 6.2.6 Scenario resources

**POST** `/v1/workspaces/{workspace_id}/scenarios`  
Create a scenario (draft).

Request:
```json
{
  "name":"Logistics Zone CAPEX (Base)",
  "model_version_id":"mv_2020_official_v1",
  "mode":"sandbox",
  "disclosure_tier":0,
  "inputs":{
    "doc_ids":["doc_987"],
    "total_budget_value": 10000,
    "currency":"million_SAR",
    "timeline_years":[2026,2027,2028,2029,2030]
  }
}
```

Response:
```json
{"scenario_id":"sc_001","scenario_version_id":"scv_001","status":"draft"}
```

**POST** `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/compile`  
Compile docs/inputs into Δd + assumptions + data quality summary. Async.

Request:
```json
{
  "scenario_version_id":"scv_001",
  "compile_options":{
    "deflator_series_id":"gdp_deflator",
    "base_year":2020,
    "residual_bucket_policy":"assumption_with_range"
  }
}
```

Response:
```json
{"job_id":"job_compile_001","status":"queued"}
```

**GET** `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/versions/{scenario_version_id}/compiled`  
Return compiled outputs:
- Δd vectors (by year)
- mapping decisions
- assumption register drafts
- data quality summary

---

#### 6.2.7 HITL mapping decisions

**POST** `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/mapping-decisions:bulk`  
Approve/override suggested mappings.

Request:
```json
{
  "scenario_version_id":"scv_001",
  "decisions":[
    {"line_item_id":"li_1","final_sector_code":"F","decision_type":"approved"},
    {"line_item_id":"li_2","final_sector_code":"H","decision_type":"overridden","decision_note":"Equipment maps to transport services"}
  ]
}
```

Response:
```json
{"updated":2,"pending":15}
```

---

#### 6.2.8 Depth Engine (Muḥāsibī artifacts)

**POST** `/v1/workspaces/{workspace_id}/depth/plans`  
Generate scenario suite plan (candidate set → bias register → contrarian suite → shortlist). Output is structured artifacts. Async.

Request:
```json
{"scenario_id":"sc_001","scenario_version_id":"scv_001","constraints":"model_executable_only"}
```

Response:
```json
{"job_id":"job_depth_001","status":"queued"}
```

**GET** `/v1/workspaces/{workspace_id}/depth/plans/{plan_id}`  
Returns artifacts:
- candidates[]
- bias_register[]
- contrarian_suite[]
- shortlist[]

---

#### 6.2.9 Runs (deterministic IO engine)

**POST** `/v1/workspaces/{workspace_id}/runs`  
Create a run from a compiled scenario.

Request:
```json
{
  "scenario_id":"sc_001",
  "scenario_version_id":"scv_001",
  "model_version_id":"mv_2020_official_v1",
  "mode":"sandbox",
  "options":{
    "include_import_leakage":true,
    "include_direct_indirect_split":true
  }
}
```

Response:
```json
{"run_id":"run_001","status":"running"}
```

**GET** `/v1/workspaces/{workspace_id}/runs/{run_id}`  
Status + snapshot metadata.

**GET** `/v1/workspaces/{workspace_id}/runs/{run_id}/results`  
Results object (core):
- Δx by sector/year
- multipliers
- decomposition
- leakage (if enabled)
- attachments (artifacts)

---

#### 6.2.10 Batch runs

**POST** `/v1/workspaces/{workspace_id}/runs:batch`  
Submit many runs (scenario variants, sensitivities).

Request:
```json
{
  "batch_name":"Tourism sensitivities",
  "items":[
    {"scenario_version_id":"scv_101","model_version_id":"mv_2020_official_v1"},
    {"scenario_version_id":"scv_102","model_version_id":"mv_2020_official_v1"}
  ]
}
```

Response:
```json
{"batch_id":"batch_77","status":"queued","count":2}
```

---

#### 6.2.11 Nowcasting / RAS balancing

**POST** `/v1/workspaces/{workspace_id}/nowcasting/ras`  
Create a balanced-nowcast model version. Async.

Request:
```json
{
  "base_model_version_id":"mv_2020_official_v1",
  "target_year":2025,
  "target_row_totals_ref":"s3://.../row_totals_2025.csv",
  "target_col_totals_ref":"s3://.../col_totals_2025.csv",
  "constraints":{"fixed_cells_ref":null}
}
```

Response:
```json
{"job_id":"job_ras_001","status":"queued"}
```

---

#### 6.2.12 Constraints / feasibility solve

**POST** `/v1/workspaces/{workspace_id}/constraints/solve`  
Compute feasible impacts given a constraint set.

Request:
```json
{
  "run_id":"run_001",
  "constraint_set_id":"cs_2026_01",
  "mode":"sandbox"
}
```

Response:
```json
{
  "feasible_run_id":"run_001_feasible",
  "binding_constraints":[{"constraint_id":"c_9","type":"capacity","sector_code":"F"}],
  "delta_vs_unconstrained":{"metric":"jobs","value":-12000}
}
```

---

#### 6.2.13 Workforce / Saudization impacts

**POST** `/v1/workspaces/{workspace_id}/runs/{run_id}/workforce`  
Compute workforce impacts for a run (jobs, tiers).

Request:
```json
{
  "employment_coeff_version":"empcoef_2025_v1",
  "bridge_version":"bridge_2025_v1",
  "saudization_rules_version":"saudrule_2025_v1"
}
```

Response:
```json
{
  "jobs_total":50000,
  "tiers":{
    "saudi_ready":12000,
    "saudi_trainable":18000,
    "expat_reliant":20000
  },
  "confidence_summary":{"median":"medium","notes":"bridge matrix partial coverage"}
}
```

---

#### 6.2.14 Governance (No Free Facts)

**POST** `/v1/workspaces/{workspace_id}/governance/claims:extract`  
Extract atomic claims from a draft narrative / slide text. Async.

Request:
```json
{"run_id":"run_001","draft_text_ref":"s3://.../draft.txt"}
```

**POST** `/v1/workspaces/{workspace_id}/governance/nff:check`  
NFF gate: validate claims are supported or rewritten.

Request:
```json
{"run_id":"run_001","claim_set_id":"claims_01","mode":"governed"}
```

Response:
```json
{
  "passed": false,
  "unsupported_claims":[{"claim_id":"c_17","reason":"no evidence or assumption tag"}],
  "required_actions":["attach_evidence","rewrite_as_assumption","delete_claim"]
}
```

**POST** `/v1/workspaces/{workspace_id}/governance/assumptions/{assumption_id}:approve`  
Manager approval workflow.

---

#### 6.2.15 Exports (Decision Pack)

**POST** `/v1/workspaces/{workspace_id}/exports`  
Generate export artifacts. Requires governed mode + NFF pass if client-ready.

Request:
```json
{
  "run_id":"run_001",
  "export_type":"pptx",
  "template_id":"decision_pack_v1",
  "language":"en",
  "mode":"governed",
  "disclosure_tier":2
}
```

Response:
```json
{"export_id":"exp_555","status":"queued"}
```

**GET** `/v1/workspaces/{workspace_id}/exports/{export_id}`  
Returns status and download link (signed URL) when ready.

---

#### 6.2.16 Libraries (mappings, assumptions, scenario patterns)

**POST** `/v1/workspaces/{workspace_id}/libraries/mappings`  
Add a validated mapping example to the library.

**GET** `/v1/workspaces/{workspace_id}/libraries/assumptions?sector_code=F`  
Retrieve default ranges for a sector.

---

#### 6.2.17 Audit logs

**GET** `/v1/workspaces/{workspace_id}/audit-logs?since=...&actor=...`  
Returns immutable audit trail events (who changed what, when).

---

## 7) External source APIs and access notes (optional)

This section lists sources that commonly provide APIs or machine-readable downloads. Exact endpoints may change; implementers should rely on the provider’s official API documentation and terms.

- **SAMA Open Data Portal:** notes an API service; integrate per SAMA portal documentation.  
  Reference: `https://www.sama.gov.sa/en-US/EconomicReports/Pages/Summary.aspx`

- **UN Comtrade:** provides programmatic access; use official API/docs.  
  Reference: `https://comtrade.un.org/`

- **World Bank / IMF SDMX:** useful for macro aggregates and benchmark series (if needed).  
  (Use official API docs and ensure licensing/terms compliance.)

---

## 8) Appendix A — Core entities and required fields

> This appendix is a compact “data dictionary” for the minimum entities needed to implement ImpactOS.

### Workspace
- `workspace_id` (PK), `name`, `country`, `classification`, `created_at`

### Model / ModelVersion
- `model_id` (PK), `workspace_id` (FK), `name`, `country`
- `model_version_id` (PK), `model_id` (FK), `year`, `unit`, `price_basis`, `source`, `sector_taxonomy_version`, `created_at`, `qa_flags`

### Matrices (stored by reference)
- `matrix_id` (PK), `model_version_id` (FK), `name` (Z/x/A/B/F/etc), `storage_ref`, `hash_sha256`, `shape`

### Document / Extraction / LineItem
- `doc_id` (PK), `workspace_id` (FK), `doc_type`, `source_type`, `classification`, `language`, `hash_sha256`
- `extraction_id` (PK), `doc_id` (FK), `status`, `output_ref`
- `line_item_id` (PK), `extraction_id` (FK), `raw_text`, `total_value`, `currency`, `page_ref`, `location_ptr`

### Scenario / ScenarioVersion
- `scenario_id` (PK), `workspace_id` (FK), `name`
- `scenario_version_id` (PK), `scenario_id` (FK), `model_version_id`, `mode`, `disclosure_tier`, `inputs_ref`, `compiled_ref`, `data_quality_ref`

### MappingDecision
- `mapping_decision_id` (PK), `scenario_version_id` (FK), `line_item_id` (FK), `suggested_sector_code`, `suggested_confidence`, `final_sector_code`, `decision_type`, `decided_by`, `decided_at`

### Assumption
- `assumption_id` (PK), `scenario_version_id` (FK), `name`, `value`, `unit`, `range_low`, `range_high`, `status`, `approved_by`, `approved_at`

### Evidence
- `evidence_id` (PK), `workspace_id` (FK), `evidence_type`, `pointer_json`, `excerpt`, `captured_at`

### Claim
- `claim_id` (PK), `workspace_id` (FK), `run_id` (FK), `claim_text`, `claim_type`, `status`, `needs_evidence`, `used_in`

### Run / RunArtifact / Export
- `run_id` (PK), `workspace_id` (FK), `scenario_version_id` (FK), `model_version_id` (FK), `mode`, `snapshot_json`, `status`, `started_at`, `completed_at`
- `artifact_id` (PK), `run_id` (FK), `artifact_type`, `storage_ref`, `hash_sha256`
- `export_id` (PK), `run_id` (FK), `export_type`, `template_id`, `language`, `mode`, `disclosure_tier`, `status`, `download_ref`

---

## 9) Appendix B — Standard response envelopes

### Success envelope (recommended)
```json
{
  "data": {},
  "meta": {"request_id":"req_...","time_utc":"..."},
  "errors": []
}
```

### Error envelope (RFC7807-style)
```json
{
  "type":"https://impactos/errors/validation",
  "title":"Validation error",
  "status":400,
  "detail":"model_version_id is required",
  "instance":"/v1/workspaces/ws_123/runs"
}
```

---

**End of file.**
