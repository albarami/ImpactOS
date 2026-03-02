# Backend Dependencies for Phase 3B

> Status of backend tickets B-1 through B-17 as verified against `app.openapi()`.
>
> Canonical ticket definitions from sprint prompt files.
>
> Date: 2026-03-02

## B-Ticket Closure Table

| Ticket | Canonical Name | Status | Routes Added by This Ticket | Resolved In |
|--------|---------------|--------|----------------------------|-------------|
| B-1 | Workspace CRUD | DONE | `POST /v1/workspaces`, `GET /v1/workspaces`, `GET /v1/workspaces/{workspace_id}`, `PUT /v1/workspaces/{workspace_id}` | Sprint 1 / PR #1 |
| B-2 | Document list | DONE | `GET .../documents` | Sprint 2 / PR #2 |
| B-3 | Document detail | DONE | `GET .../documents/{doc_id}` | Sprint 2 / PR #2 |
| B-4 | Per-line mapping decision CRUD | DONE | `GET/PUT .../compiler/{id}/decisions/{li_id}` (POST .../decisions is pre-existing) | Sprint 3 / PR #3 |
| B-5 | Bulk threshold approval | DONE | `POST .../compiler/{id}/decisions/bulk-approve` | Sprint 3 / PR #3 |
| B-6 | Taxonomy browsing | DONE | `GET .../taxonomy/sectors`, `GET .../taxonomy/sectors/search`, `GET .../taxonomy/sectors/{code}` | Sprint 1 / PR #1 |
| B-7 | Evidence list/detail/link | DONE | `GET .../governance/evidence`, `GET .../governance/evidence/{id}`, `POST .../governance/claims/{id}/evidence` | Sprint 4 / PR #5 |
| B-8 | Mapping audit trail | DONE | `GET .../compiler/{id}/decisions/{li_id}/audit` | Sprint 3 / PR #3 |
| B-9 | Scenario list | DONE | `GET .../scenarios` (paginated) | Sprint 2 / PR #2 |
| B-10 | Scenario detail | DONE | `GET .../scenarios/{scenario_id}` | Sprint 2 / PR #2 |
| B-11 | Claim list/detail/update | DONE | `GET .../governance/claims`, `GET .../governance/claims/{id}`, `PUT .../governance/claims/{id}` | Sprint 4 / PR #5 |
| B-12 | Export artifact download | DONE | `GET .../exports/{id}/download/{format}` | Sprint 5 / PR #6 |
| B-13 | Auth contract (dev stub) | DONE | `POST /v1/auth/login`, `POST /v1/auth/logout`, `GET /v1/auth/me` | Sprint 1 / PR #1 |
| B-14 | Model version list/detail | DONE | `GET .../models/versions`, `GET .../models/versions/{id}` (workspace-scoped) | Sprint 1 / PR #1 |
| B-15 | Coefficient retrieval | DONE | `GET .../models/versions/{id}/coefficients` | Sprint 1 / PR #1 |
| B-16 | Run-from-scenario | DONE | `POST .../scenarios/{id}/run` | Sprint 5 / PR #6 |
| B-17 | GET compilation detail | DONE | `GET .../compiler/{compilation_id}` (full compilation with suggestions) | Sprint 3 / PR #3 |

**All 17 B-tickets are DONE.** All required routes are present in OpenAPI.

## Notes

### B-1: Workspace CRUD

- `PUT` is used for update (not `PATCH`).
- `DELETE /v1/workspaces/{workspace_id}` is not implemented. This is a future enhancement and does not block any current frontend sprint.

### B-5: Bulk Threshold Approval

- Accepts a confidence threshold and auto-approves all suggestions above it.
- Route: `POST .../compiler/{compilation_id}/decisions/bulk-approve`

### B-7: Evidence List/Detail/Link

- `GET .../governance/evidence` lists evidence snippets (run-scoped via query params).
- `GET .../governance/evidence/{snippet_id}` returns individual snippet.
- `POST .../governance/claims/{claim_id}/evidence` links an evidence snippet to a claim.

### B-8: Mapping Audit Trail

- `GET .../compiler/{compilation_id}/decisions/{line_item_id}/audit` returns the full state-change history for a mapping decision.

### B-11: Claim List/Detail/Update

- `GET .../governance/claims` lists claims (workspace-scoped).
- `PUT .../governance/claims/{claim_id}` updates claim status through governance lifecycle.

### B-12: Export Download

- Download path includes format parameter: `GET .../exports/{export_id}/download/{format}`
- Accepted formats: `excel`, `pptx`

### B-14: Model Versions

- Model version list/detail routes are workspace-scoped: `/v1/workspaces/{workspace_id}/models/versions/...`
- Model registration remains global: `POST /v1/engine/models`

### B-15: Coefficient Retrieval

- Returns satellite coefficients for a specific model version.
- Route: `GET .../models/versions/{model_version_id}/coefficients`

### B-16: Run-from-Scenario

- Requires a compiled scenario (non-empty shock_items).
- Governed mode requires locked scenario (`is_locked=true`).

## Dependency Graph (Resolved)

```
F-1 (Shell + Auth)  <-- B-1  (Workspace CRUD)          [DONE Sprint 1]
                     <-- B-13 (Auth stub)               [DONE Sprint 1]
F-2 (Document UI)   <-- B-2  (Document list)            [DONE Sprint 2]
                     <-- B-3  (Document detail)          [DONE Sprint 2]
F-3A (Compiler UI)  <-- B-4  (Decision CRUD)            [DONE Sprint 3]
                     <-- B-5  (Bulk threshold approval)  [DONE Sprint 3]
                     <-- B-8  (Mapping audit trail)      [DONE Sprint 3]
                     <-- B-17 (Compilation detail)       [DONE Sprint 3]
F-4A (Engine UI)    <-- B-6  (Taxonomy)                  [DONE Sprint 1]
                     <-- B-9  (Scenario list)            [DONE Sprint 2]
                     <-- B-10 (Scenario detail)          [DONE Sprint 2]
                     <-- B-14 (Model versions)           [DONE Sprint 1]
                     <-- B-15 (Coefficients)             [DONE Sprint 1]
                     <-- B-16 (Run-from-scenario)        [DONE Sprint 5]
F-5A (Governance)   <-- B-7  (Evidence)                  [DONE Sprint 4]
                     <-- B-11 (Claims)                   [DONE Sprint 4]
F-6A (Export UI)    <-- B-12 (Export download)            [DONE Sprint 5]
```

All frontend sprints F-1 through F-6A are unblocked by backend.
