# ImpactOS Endpoint Matrix

> Generated from `openapi.json` (88 paths, 106 operations). API version 0.1.0.
>
> Date: 2026-03-02

## Infrastructure

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| GET | `/health` | Liveness probe with component health checks | infra |
| GET | `/api/version` | Return app name, version, environment | infra |

## Auth (B-13)

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/auth/login` | Login | auth |
| POST | `/v1/auth/logout` | Logout | auth |
| GET | `/v1/auth/me` | Get current user | auth |

## Workspaces (B-1)

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces` | Create workspace | workspaces |
| GET | `/v1/workspaces` | List workspaces | workspaces |
| GET | `/v1/workspaces/{workspace_id}` | Get workspace by ID | workspaces |
| PUT | `/v1/workspaces/{workspace_id}` | Update workspace | workspaces |

> Note: DELETE workspace is not implemented (future enhancement).

## Documents + Extraction (B-2, B-3)

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces/{workspace_id}/documents` | Upload a document (multipart) | documents |
| GET | `/v1/workspaces/{workspace_id}/documents` | List documents | documents |
| GET | `/v1/workspaces/{workspace_id}/documents/{doc_id}` | Get document detail | documents |
| POST | `/v1/workspaces/{workspace_id}/documents/{doc_id}/extract` | Trigger extraction | documents |
| GET | `/v1/workspaces/{workspace_id}/jobs/{job_id}` | Poll extraction job status | documents |
| GET | `/v1/workspaces/{workspace_id}/documents/{doc_id}/line-items` | Get extracted line items | documents |

## Compiler + HITL Decisions (B-4, B-17)

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces/{workspace_id}/compiler/compile` | Trigger AI-assisted compilation | compiler |
| GET | `/v1/workspaces/{workspace_id}/compiler/{compilation_id}` | Get full compilation with suggestions (B-17) | compiler |
| GET | `/v1/workspaces/{workspace_id}/compiler/{compilation_id}/status` | Get compilation status counts | compiler |
| POST | `/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions` | Bulk decisions | compiler |
| POST | `/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/bulk-approve` | Bulk approve decisions | compiler |
| GET | `/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}` | Get decision | compiler |
| PUT | `/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}` | Update decision | compiler |
| GET | `/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}/audit` | Get decision audit trail | compiler |

## Scenarios (B-5, B-9, B-10, B-16)

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces/{workspace_id}/scenarios` | Create scenario | scenarios |
| GET | `/v1/workspaces/{workspace_id}/scenarios` | List scenarios (B-9) | scenarios |
| GET | `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}` | Get scenario detail (B-10) | scenarios |
| POST | `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/compile` | Compile scenario | scenarios |
| POST | `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/mapping-decisions` | Bulk mapping decisions | scenarios |
| GET | `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/versions` | Get version history | scenarios |
| POST | `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/lock` | Lock for governed run | scenarios |
| POST | `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/run` | Run from scenario (B-16) | scenarios |

## Taxonomy (B-8)

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| GET | `/v1/workspaces/{workspace_id}/taxonomy/sectors` | List sectors | taxonomy |
| GET | `/v1/workspaces/{workspace_id}/taxonomy/sectors/search` | Search sectors | taxonomy |
| GET | `/v1/workspaces/{workspace_id}/taxonomy/sectors/{sector_code}` | Get sector | taxonomy |

## Engine Runs (B-6)

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/engine/models` | Register I-O model (global) | engine |
| POST | `/v1/workspaces/{workspace_id}/engine/runs` | Execute single run | engine |
| GET | `/v1/workspaces/{workspace_id}/engine/runs/{run_id}` | Get run results | engine |
| POST | `/v1/workspaces/{workspace_id}/engine/batch` | Execute batch runs | engine |
| GET | `/v1/workspaces/{workspace_id}/engine/batch/{batch_id}` | Get batch status | engine |

## Model Versions (B-14)

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| GET | `/v1/workspaces/{workspace_id}/models/versions` | List model versions | models |
| GET | `/v1/workspaces/{workspace_id}/models/versions/{model_version_id}` | Get model version | models |
| GET | `/v1/workspaces/{workspace_id}/models/versions/{model_version_id}/coefficients` | Get coefficients | models |

## Governance + NFF (B-7, B-11)

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces/{workspace_id}/governance/claims/extract` | Extract claims from narrative | governance |
| GET | `/v1/workspaces/{workspace_id}/governance/claims` | List claims | governance |
| GET | `/v1/workspaces/{workspace_id}/governance/claims/{claim_id}` | Get claim detail | governance |
| PUT | `/v1/workspaces/{workspace_id}/governance/claims/{claim_id}` | Update claim status | governance |
| POST | `/v1/workspaces/{workspace_id}/governance/claims/{claim_id}/evidence` | Link evidence to claim | governance |
| GET | `/v1/workspaces/{workspace_id}/governance/evidence` | List evidence (B-11) | governance |
| GET | `/v1/workspaces/{workspace_id}/governance/evidence/{snippet_id}` | Get evidence detail (B-11) | governance |
| POST | `/v1/workspaces/{workspace_id}/governance/nff/check` | NFF gate check | governance |
| POST | `/v1/workspaces/{workspace_id}/governance/assumptions` | Create assumption | governance |
| POST | `/v1/workspaces/{workspace_id}/governance/assumptions/{assumption_id}/approve` | Approve assumption | governance |
| GET | `/v1/workspaces/{workspace_id}/governance/status/{run_id}` | Get governance status | governance |
| GET | `/v1/workspaces/{workspace_id}/governance/blocking-reasons/{run_id}` | Get blocking reasons | governance |

## Exports (B-12)

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces/{workspace_id}/exports` | Create export | exports |
| GET | `/v1/workspaces/{workspace_id}/exports/{export_id}` | Get export status | exports |
| GET | `/v1/workspaces/{workspace_id}/exports/{export_id}/download/{format}` | Download artifact (B-12) | exports |
| POST | `/v1/workspaces/{workspace_id}/exports/variance-bridge` | Variance bridge comparison | exports |

## Data Quality (B-15)

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces/{workspace_id}/runs/{run_id}/quality` | Compute quality summary | data-quality |
| GET | `/v1/workspaces/{workspace_id}/runs/{run_id}/quality` | Get quality summary | data-quality |
| GET | `/v1/workspaces/{workspace_id}/quality` | Get quality overview | data-quality |
| GET | `/v1/workspaces/{workspace_id}/quality/freshness` | Get freshness overview | data-quality |

## Feasibility

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces/{workspace_id}/constraints` | Create constraint set | feasibility |
| GET | `/v1/workspaces/{workspace_id}/constraints` | List constraint sets | feasibility |
| GET | `/v1/workspaces/{workspace_id}/constraints/{constraint_set_id}` | Get constraint set | feasibility |
| POST | `/v1/workspaces/{workspace_id}/constraints/solve` | Run feasibility solver | feasibility |
| GET | `/v1/workspaces/{workspace_id}/runs/{run_id}/feasibility` | Get feasibility results | feasibility |

## Depth Engine

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces/{workspace_id}/depth/plans` | Trigger depth plan | depth |
| GET | `/v1/workspaces/{workspace_id}/depth/plans/{plan_id}` | Get depth plan status | depth |
| GET | `/v1/workspaces/{workspace_id}/depth/plans/{plan_id}/artifacts/{step}` | Get depth artifact | depth |
| GET | `/v1/workspaces/{workspace_id}/depth/plans/{plan_id}/suite` | Get scenario suite | depth |

## Knowledge Flywheel Libraries

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces/{workspace_id}/libraries/mapping/entries` | Create mapping entry | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/mapping/entries` | List mapping entries | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/mapping/entries/{entry_id}` | Get mapping entry | libraries |
| PATCH | `/v1/workspaces/{workspace_id}/libraries/mapping/entries/{entry_id}/status` | Update mapping entry status | libraries |
| POST | `/v1/workspaces/{workspace_id}/libraries/mapping/versions` | Publish mapping version | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/mapping/versions` | List mapping versions | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/mapping/versions/latest` | Get latest mapping version | libraries |
| POST | `/v1/workspaces/{workspace_id}/libraries/assumptions/entries` | Create assumption entry | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/assumptions/entries` | List assumption entries | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/assumptions/entries/{entry_id}` | Get assumption entry | libraries |
| PATCH | `/v1/workspaces/{workspace_id}/libraries/assumptions/entries/{entry_id}/status` | Update assumption entry status | libraries |
| POST | `/v1/workspaces/{workspace_id}/libraries/assumptions/versions` | Publish assumption version | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/assumptions/versions` | List assumption versions | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/assumptions/versions/latest` | Get latest assumption version | libraries |
| POST | `/v1/workspaces/{workspace_id}/libraries/patterns` | Create scenario pattern | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/patterns` | List scenario patterns | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/patterns/{pattern_id}` | Get scenario pattern | libraries |
| PATCH | `/v1/workspaces/{workspace_id}/libraries/patterns/{pattern_id}/usage` | Increment pattern usage | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/stats` | Get library stats | libraries |

## Workforce / Saudization

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces/{workspace_id}/employment-coefficients` | Create employment coefficients | workforce |
| GET | `/v1/workspaces/{workspace_id}/employment-coefficients` | List employment coefficients | workforce |
| GET | `/v1/workspaces/{workspace_id}/employment-coefficients/{employment_coefficients_id}` | Get employment coefficients | workforce |
| POST | `/v1/workspaces/{workspace_id}/occupation-bridge` | Create occupation bridge | workforce |
| GET | `/v1/workspaces/{workspace_id}/occupation-bridge` | List occupation bridges | workforce |
| GET | `/v1/workspaces/{workspace_id}/occupation-bridge/{bridge_id}` | Get occupation bridge | workforce |
| POST | `/v1/workspaces/{workspace_id}/saudization-rules` | Create saudization rules | workforce |
| GET | `/v1/workspaces/{workspace_id}/saudization-rules` | List saudization rules | workforce |
| GET | `/v1/workspaces/{workspace_id}/saudization-rules/{rules_id}` | Get saudization rules | workforce |
| POST | `/v1/workspaces/{workspace_id}/runs/{run_id}/workforce` | Compute workforce impact | workforce |
| GET | `/v1/workspaces/{workspace_id}/runs/{run_id}/workforce` | Get workforce results | workforce |

## Metrics / Observability

| Method | Route | Purpose | Tag |
|--------|-------|---------|-----|
| POST | `/v1/workspaces/{workspace_id}/metrics` | Record metric event | metrics |
| GET | `/v1/workspaces/{workspace_id}/metrics/engagement/{engagement_id}` | Get engagement metrics | metrics |
| GET | `/v1/workspaces/{workspace_id}/metrics/dashboard` | Get dashboard summary | metrics |
| POST | `/v1/workspaces/{workspace_id}/metrics/dashboard` | Post dashboard summary | metrics |
| POST | `/v1/workspaces/{workspace_id}/metrics/readiness` | Run pilot readiness check | metrics |

## Summary

| Category | Count |
|----------|-------|
| Total paths in openapi.json | 88 |
| Total operations (methods) | 106 |
| B-ticket endpoints (B-1..B-17) | All present (see contract guard test) |
