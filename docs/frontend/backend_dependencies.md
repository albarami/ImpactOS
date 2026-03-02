# Backend Dependencies for Phase 3B

> Status of backend tickets B-1 through B-17 as verified against `app.openapi()`.
>
> Date: 2026-03-02

## B-Ticket Closure Table

| Ticket | Status | Routes in OpenAPI | Resolved In |
|--------|--------|-------------------|-------------|
| B-1 | DONE | `POST /v1/workspaces`, `GET /v1/workspaces`, `GET /v1/workspaces/{workspace_id}`, `PUT /v1/workspaces/{workspace_id}` | Sprint 1 / PR #1 |
| B-2 | DONE | `POST .../documents`, `GET .../documents`, `GET .../documents/{doc_id}`, `POST .../documents/{doc_id}/extract`, `GET .../jobs/{job_id}` | Sprint 1 / PR #1 |
| B-3 | DONE | `GET .../documents/{doc_id}/line-items` | Sprint 2 / PR #2 |
| B-4 | DONE | `POST .../compiler/compile`, `GET .../compiler/{id}/status`, `POST .../compiler/{id}/decisions`, `POST .../compiler/{id}/decisions/bulk-approve`, `GET/PUT .../compiler/{id}/decisions/{li_id}`, `GET .../compiler/{id}/decisions/{li_id}/audit` | Sprint 3 / PR #3 |
| B-5 | DONE | `POST .../scenarios`, `POST .../scenarios/{id}/compile`, `POST .../scenarios/{id}/mapping-decisions`, `GET .../scenarios/{id}/versions`, `POST .../scenarios/{id}/lock` | Sprint 1 / PR #1 |
| B-6 | DONE | `POST /v1/engine/models`, `POST .../engine/runs`, `GET .../engine/runs/{id}`, `POST .../engine/batch`, `GET .../engine/batch/{id}` | Sprint 1 / PR #1 |
| B-7 | DONE | `POST .../governance/claims/extract`, `GET .../governance/claims`, `GET/PUT .../governance/claims/{id}`, `POST .../governance/claims/{id}/evidence`, `POST .../governance/nff/check`, `POST .../governance/assumptions`, `POST .../governance/assumptions/{id}/approve`, `GET .../governance/status/{run_id}`, `GET .../governance/blocking-reasons/{run_id}` | Sprint 4 / PR #5 |
| B-8 | DONE | `GET .../taxonomy/sectors`, `GET .../taxonomy/sectors/search`, `GET .../taxonomy/sectors/{code}` | Sprint 1 / PR #1 |
| B-9 | DONE | `GET .../scenarios` (list, paginated) | Sprint 2 / PR #2 |
| B-10 | DONE | `GET .../scenarios/{scenario_id}` (full detail) | Sprint 2 / PR #2 |
| B-11 | DONE | `GET .../governance/evidence`, `GET .../governance/evidence/{snippet_id}` | Sprint 4 / PR #5 |
| B-12 | DONE | `POST .../exports`, `GET .../exports/{id}`, `GET .../exports/{id}/download/{format}` | Sprint 5 / PR #6 |
| B-13 | DONE | `POST /v1/auth/login`, `POST /v1/auth/logout`, `GET /v1/auth/me` | Sprint 1 / PR #1 |
| B-14 | DONE | `GET .../models/versions`, `GET .../models/versions/{id}`, `GET .../models/versions/{id}/coefficients` (workspace-scoped) | Sprint 2 / PR #2 |
| B-15 | DONE | `POST .../runs/{id}/quality`, `GET .../runs/{id}/quality`, `GET .../quality`, `GET .../quality/freshness` | Sprint 1 / PR #1 |
| B-16 | DONE | `POST .../scenarios/{scenario_id}/run` | Sprint 5 / PR #6 |
| B-17 | DONE | `GET .../compiler/{compilation_id}` (full compilation with suggestions) | Sprint 3 / PR #3 |

**All 17 B-tickets are DONE.** All required routes are present in OpenAPI.

## Notes

### B-1: Workspace CRUD

- `PUT` is used for update (not `PATCH`).
- `DELETE /v1/workspaces/{workspace_id}` is not implemented. This is a future enhancement and does not block any current frontend sprint.

### B-12: Export Download

- Download path includes format parameter: `GET .../exports/{export_id}/download/{format}`
- Accepted formats: `excel`, `pptx`
- Artifact bytes are persisted at export creation time and served from storage on download.

### B-14: Model Versions

- Model version list/detail routes are workspace-scoped: `/v1/workspaces/{workspace_id}/models/versions/...`
- Model registration remains global: `POST /v1/engine/models`

### B-16: Run-from-Scenario

- Requires a compiled scenario (non-empty shock_items).
- Governed mode requires locked scenario (`is_locked=true`).
- Reuses the deterministic engine path (no duplicated business logic).

## Dependency Graph (Resolved)

```
F-1 (Shell + Auth)  <-- B-1 (Workspace CRUD)    [DONE]
                     <-- B-13 (Auth)              [DONE]
F-2 (Document UI)   <-- B-2 (Documents)          [DONE]
                     <-- B-3 (Line items)         [DONE]
F-3A (Compiler UI)  <-- B-4 (Compiler + HITL)    [DONE]
                     <-- B-17 (Full compilation)  [DONE]
F-4A (Engine UI)    <-- B-5 (Scenarios)           [DONE]
                     <-- B-6 (Engine runs)        [DONE]
                     <-- B-8 (Taxonomy)           [DONE]
                     <-- B-9 (Scenario list)      [DONE]
                     <-- B-10 (Scenario detail)   [DONE]
                     <-- B-14 (Model versions)    [DONE]
                     <-- B-16 (Run-from-scenario) [DONE]
F-5A (Governance)   <-- B-7 (Claims + NFF)       [DONE]
                     <-- B-11 (Evidence)          [DONE]
F-6A (Export UI)    <-- B-12 (Export download)    [DONE]
                     <-- B-15 (Data quality)      [DONE]
```

All frontend sprints F-1 through F-6A are unblocked by backend.
