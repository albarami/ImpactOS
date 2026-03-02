# ImpactOS Endpoint Matrix

> Generated from `openapi.json` (64 paths, 75 operations). API version 0.1.0.
>
> Date: 2026-03-01

## Available Now (Phase 3A)

These endpoints exist in the backend and are assigned to frontend sprints F-1 through F-6A.

| Method | Route | Purpose | Request Body | Response Shape | Frontend Sprint |
|--------|-------|---------|--------------|----------------|-----------------|
| GET | `/health` | Liveness probe with component health checks | — | `{ [key: string]: unknown }` | F-1 |
| GET | `/api/version` | Return app name, version, environment | — | `{ [key: string]: string }` | F-1 |
| POST | `/v1/workspaces/{workspace_id}/documents` | Upload a document (multipart) | `{ file, doc_type, source_type, classification, language, uploaded_by }` | `{ doc_id, status, hash_sha256 }` | F-2 |
| POST | `/v1/workspaces/{workspace_id}/documents/{doc_id}/extract` | Trigger extraction on uploaded document | `{ extract_tables, extract_line_items, language_hint }` | `{ job_id, status }` | F-2 |
| GET | `/v1/workspaces/{workspace_id}/jobs/{job_id}` | Poll extraction job status | — | `{ job_id, doc_id, status, error_message }` | F-2 |
| GET | `/v1/workspaces/{workspace_id}/documents/{doc_id}/line-items` | Get extracted line items for a document | — | `{ items }` | F-2 |
| POST | `/v1/workspaces/{workspace_id}/compiler/compile` | Trigger AI-assisted compilation (line items or document_id) | `{ scenario_name, base_model_version_id, base_year, start_year, end_year, line_items?, document_id?, phasing? }` | `{ compilation_id, suggestions, high_confidence, medium_confidence, low_confidence }` | F-3A |
| GET | `/v1/workspaces/{workspace_id}/compiler/{compilation_id}/status` | Get compilation suggestion status counts | — | `{ compilation_id, total_suggestions, high_confidence, medium_confidence, low_confidence, assumption_drafts }` | F-3A |
| POST | `/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions` | Accept/reject suggestions in bulk | `{ decisions }` | `{ accepted, rejected, total }` | F-3A |
| POST | `/v1/workspaces/{workspace_id}/scenarios` | Create a new scenario (version 1) | `{ name, workspace_id?, base_model_version_id, base_year, start_year, end_year }` | `{ scenario_spec_id, version, name }` | F-4A |
| POST | `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/compile` | Compile line items + decisions into shock items | `{ line_items?, document_id?, decisions, phasing, default_domestic_share }` | `{ [key: string]: unknown }` | F-4A |
| POST | `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/mapping-decisions` | Submit bulk mapping decisions (creates new version) | `{ decisions }` | `{ new_version, decisions_processed }` | F-4A |
| GET | `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/versions` | Get all versions of a scenario | — | `{ versions }` | F-4A |
| POST | `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/lock` | Lock mappings for governed run | `{ actor }` | `{ new_version, status }` | F-4A |
| POST | `/v1/engine/models` | Register an I-O model (Z, x, sector codes) — global | `{ Z, x, sector_codes, base_year, source }` | `{ model_version_id, sector_count, checksum }` | F-4A |
| POST | `/v1/workspaces/{workspace_id}/engine/runs` | Execute a single scenario run | `{ model_version_id, annual_shocks, base_year, satellite_coefficients, deflators? }` | `{ run_id, result_sets, snapshot }` | F-4A |
| GET | `/v1/workspaces/{workspace_id}/engine/runs/{run_id}` | Get results for a completed run | — | `{ run_id, result_sets, snapshot }` | F-4A |
| POST | `/v1/workspaces/{workspace_id}/engine/batch` | Execute a batch of scenario runs | `{ model_version_id, scenarios, satellite_coefficients }` | `{ batch_id, status, results }` | F-4A |
| GET | `/v1/workspaces/{workspace_id}/engine/batch/{batch_id}` | Get batch run status and results | — | `{ batch_id, status, results }` | F-4A |
| POST | `/v1/workspaces/{workspace_id}/governance/claims/extract` | Extract atomic claims from draft narrative | `{ draft_text, workspace_id?, run_id }` | `{ claims, total, needs_evidence_count }` | F-5A |
| POST | `/v1/workspaces/{workspace_id}/governance/nff/check` | NFF gate: validate claims are supported | `{ claim_ids }` | `{ passed, total_claims, blocking_reasons }` | F-5A |
| POST | `/v1/workspaces/{workspace_id}/governance/assumptions` | Create a new assumption (draft status) | `{ type, value, units, justification }` | `{ assumption_id, status }` | F-5A |
| POST | `/v1/workspaces/{workspace_id}/governance/assumptions/{assumption_id}/approve` | Approve an assumption with sensitivity range | `{ range_min?, range_max?, actor }` | `{ assumption_id, status, range_min?, range_max? }` | F-5A |
| GET | `/v1/workspaces/{workspace_id}/governance/status/{run_id}` | Get governance status for a run | — | `{ run_id, claims_total, claims_resolved, claims_unresolved, assumptions_total, assumptions_approved, nff_passed }` | F-5A |
| GET | `/v1/workspaces/{workspace_id}/governance/blocking-reasons/{run_id}` | Get blocking reasons for a run | — | `{ run_id, blocking_reasons }` | F-5A |
| POST | `/v1/workspaces/{workspace_id}/exports` | Create a new export (generates formats with watermarks) | `{ run_id, workspace_id?, mode, export_formats, pack_data }` | `{ export_id, status, checksums?, blocking_reasons? }` | F-6A |
| GET | `/v1/workspaces/{workspace_id}/exports/{export_id}` | Get export status and metadata | — | `{ export_id, run_id, mode, status, checksums? }` | F-6A |
| POST | `/v1/workspaces/{workspace_id}/exports/variance-bridge` | Compare two runs and decompose changes into drivers | `{ run_a, run_b }` | `{ start_value, end_value, total_variance, drivers }` | F-6A |

### Deferred Endpoints (exist but not in Phase 3A scope)

These endpoints exist in the backend but are not assigned to Phase 3A frontend sprints.

| Method | Route | Purpose | Request Body | Response Shape | Tag |
|--------|-------|---------|--------------|----------------|-----|
| POST | `/v1/workspaces/{workspace_id}/constraints` | Create constraint set | — | — | feasibility |
| GET | `/v1/workspaces/{workspace_id}/constraints` | List constraint sets by workspace | — | — | feasibility |
| GET | `/v1/workspaces/{workspace_id}/constraints/{constraint_set_id}` | Get constraint set (latest or specific version) | — | — | feasibility |
| POST | `/v1/workspaces/{workspace_id}/constraints/solve` | Run feasibility solver | — | — | feasibility |
| GET | `/v1/workspaces/{workspace_id}/runs/{run_id}/feasibility` | Get feasibility results for a run | — | — | feasibility |
| POST | `/v1/workspaces/{workspace_id}/runs/{run_id}/quality` | Compute data quality summary for a run | — | — | data-quality |
| GET | `/v1/workspaces/{workspace_id}/runs/{run_id}/quality` | Get quality summary for a run | — | — | data-quality |
| GET | `/v1/workspaces/{workspace_id}/quality/freshness` | Get freshness overview for workspace | — | — | data-quality |
| GET | `/v1/workspaces/{workspace_id}/quality` | Get quality overview for workspace | — | — | data-quality |
| POST | `/v1/workspaces/{workspace_id}/depth/plans` | Trigger a new depth engine plan | — | — | depth |
| GET | `/v1/workspaces/{workspace_id}/depth/plans/{plan_id}` | Get depth plan status and artifacts | — | — | depth |
| GET | `/v1/workspaces/{workspace_id}/depth/plans/{plan_id}/artifacts/{step}` | Get a single depth artifact by step | — | — | depth |
| GET | `/v1/workspaces/{workspace_id}/depth/plans/{plan_id}/suite` | Get the final scenario suite plan | — | — | depth |
| POST | `/v1/workspaces/{workspace_id}/libraries/mapping/entries` | Create mapping library entry | — | — | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/mapping/entries` | List mapping entries | — | — | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/mapping/entries/{entry_id}` | Get mapping entry | — | — | libraries |
| PATCH | `/v1/workspaces/{workspace_id}/libraries/mapping/entries/{entry_id}/status` | Promote/deprecate mapping entry | — | — | libraries |
| POST | `/v1/workspaces/{workspace_id}/libraries/mapping/versions` | Publish mapping version snapshot | — | — | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/mapping/versions` | List mapping versions | — | — | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/mapping/versions/latest` | Get latest mapping version | — | — | libraries |
| POST | `/v1/workspaces/{workspace_id}/libraries/assumptions/entries` | Create assumption library entry | — | — | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/assumptions/entries` | List assumption entries | — | — | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/assumptions/entries/{entry_id}` | Get assumption entry | — | — | libraries |
| PATCH | `/v1/workspaces/{workspace_id}/libraries/assumptions/entries/{entry_id}/status` | Promote/deprecate assumption entry | — | — | libraries |
| POST | `/v1/workspaces/{workspace_id}/libraries/assumptions/versions` | Publish assumption version snapshot | — | — | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/assumptions/versions` | List assumption versions | — | — | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/assumptions/versions/latest` | Get latest assumption version | — | — | libraries |
| POST | `/v1/workspaces/{workspace_id}/libraries/patterns` | Create scenario pattern | — | — | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/patterns` | List scenario patterns | — | — | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/patterns/{pattern_id}` | Get scenario pattern | — | — | libraries |
| PATCH | `/v1/workspaces/{workspace_id}/libraries/patterns/{pattern_id}/usage` | Increment pattern usage count | — | — | libraries |
| GET | `/v1/workspaces/{workspace_id}/libraries/stats` | Get aggregate library stats | — | — | libraries |
| POST | `/v1/workspaces/{workspace_id}/metrics` | Record a metric event | — | — | metrics |
| GET | `/v1/workspaces/{workspace_id}/metrics/engagement/{engagement_id}` | Get all metric events for an engagement | — | — | metrics |
| GET | `/v1/workspaces/{workspace_id}/metrics/dashboard` | Get dashboard summary (empty data) | — | — | metrics |
| POST | `/v1/workspaces/{workspace_id}/metrics/dashboard` | Get dashboard summary (with data) | — | — | metrics |
| POST | `/v1/workspaces/{workspace_id}/metrics/readiness` | Run pilot readiness check | — | — | metrics |
| POST | `/v1/workspaces/{workspace_id}/employment-coefficients` | Create employment coefficients | — | — | workforce |
| GET | `/v1/workspaces/{workspace_id}/employment-coefficients` | List employment coefficients | — | — | workforce |
| GET | `/v1/workspaces/{workspace_id}/employment-coefficients/{employment_coefficients_id}` | Get employment coefficients | — | — | workforce |
| POST | `/v1/workspaces/{workspace_id}/occupation-bridge` | Create sector-occupation bridge | — | — | workforce |
| GET | `/v1/workspaces/{workspace_id}/occupation-bridge` | List occupation bridges | — | — | workforce |
| GET | `/v1/workspaces/{workspace_id}/occupation-bridge/{bridge_id}` | Get occupation bridge | — | — | workforce |
| POST | `/v1/workspaces/{workspace_id}/saudization-rules` | Create saudization rules | — | — | workforce |
| GET | `/v1/workspaces/{workspace_id}/saudization-rules` | List saudization rules | — | — | workforce |
| GET | `/v1/workspaces/{workspace_id}/saudization-rules/{rules_id}` | Get saudization rules | — | — | workforce |
| POST | `/v1/workspaces/{workspace_id}/runs/{run_id}/workforce` | Compute workforce impact for a run | — | — | workforce |
| GET | `/v1/workspaces/{workspace_id}/runs/{run_id}/workforce` | Get workforce results for a run | — | — | workforce |

## Missing -- Needed for Phase 3B

These endpoints do not exist in the backend and must be built before the frontend can use them.

| Ticket | Endpoint Needed | Purpose | Request Body | Response Shape | Blocking Sprint |
|--------|----------------|---------|--------------|----------------|-----------------|
| B-1 | `POST /v1/workspaces` | Create workspace | — | — | F-1 |
| B-1 | `GET /v1/workspaces` | List workspaces | — | — | F-1 |
| B-1 | `GET /v1/workspaces/{workspace_id}` | Get workspace by ID | — | — | F-1 |
| B-1 | `PATCH /v1/workspaces/{workspace_id}` | Update workspace | — | — | F-1 |
| B-1 | `DELETE /v1/workspaces/{workspace_id}` | Delete workspace | — | — | F-1 |
| B-12 | `GET /v1/workspaces/{workspace_id}/exports/{export_id}/download` | Download export artifact file | — | — | F-6A |
| B-14 | `GET /v1/engine/models` | List registered model versions | — | — | F-4A |
| B-14 | `GET /v1/engine/models/{model_version_id}` | Get model version by ID | — | — | F-4A |
| B-16 | `POST /v1/workspaces/{workspace_id}/scenarios/{scenario_id}/run` | Convenience: run a scenario directly (auto-build shock vector) | — | — | F-4A |
| B-17 | `GET /v1/workspaces/{workspace_id}/compiler/{compilation_id}` | Get full compilation with suggestions (not just status counts) | — | — | F-3A |

## Summary

| Category | Count |
|----------|-------|
| Total paths in openapi.json | 64 |
| Total operations (methods) | 75 |
| Phase 3A endpoints (F-1 to F-6A) | 28 |
| Deferred endpoints (exist, not in Phase 3A) | 47 |
| Missing endpoints (need backend work) | 10 |
