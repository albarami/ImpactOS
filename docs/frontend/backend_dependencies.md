# Backend Dependencies for Phase 3B

> These backend tickets must be completed before the corresponding frontend sprints can be fully implemented.
>
> Date: 2026-03-01

## Backend Tickets

| Ticket | Endpoint | Purpose | Blocking Sprint |
|--------|----------|---------|-----------------|
| B-1 | `POST /v1/workspaces` | Create a new workspace | F-1 |
| B-1 | `GET /v1/workspaces` | List all workspaces for the current user | F-1 |
| B-1 | `GET /v1/workspaces/{workspace_id}` | Get workspace details by ID | F-1 |
| B-1 | `PATCH /v1/workspaces/{workspace_id}` | Update workspace metadata | F-1 |
| B-1 | `DELETE /v1/workspaces/{workspace_id}` | Delete a workspace | F-1 |
| B-12 | `GET /v1/workspaces/{workspace_id}/exports/{export_id}/download` | Download the generated export artifact (PDF/PPTX/XLSX file) | F-6A |
| B-14 | `GET /v1/engine/models` | List all registered model versions (currently only POST registration exists) | F-4A |
| B-14 | `GET /v1/engine/models/{model_version_id}` | Get a model version by ID (metadata, sector count, checksum) | F-4A |
| B-16 | `POST /v1/workspaces/{workspace_id}/scenarios/{scenario_id}/run` | Convenience endpoint to run a scenario directly without manually constructing shock vectors | F-4A |
| B-17 | `GET /v1/workspaces/{workspace_id}/compiler/{compilation_id}` | Get the full compilation result with all suggestions (current status endpoint only returns counts) | F-3A |

## Ticket Details

### B-1: Workspace CRUD Router

**Priority:** Critical -- blocks F-1 (shell + auth)

No workspace router exists in the backend. All workspace-scoped routes assume a `workspace_id` path parameter, but there is no way to create, list, or manage workspaces via the API. The frontend needs workspace CRUD to:

- Display a workspace selector/switcher
- Allow users to create new workspaces
- Show workspace metadata in the UI shell

**Required endpoints:**
- `POST /v1/workspaces` -- create workspace (name, description, classification)
- `GET /v1/workspaces` -- list workspaces (filtered by user RBAC)
- `GET /v1/workspaces/{workspace_id}` -- get workspace details
- `PATCH /v1/workspaces/{workspace_id}` -- update workspace
- `DELETE /v1/workspaces/{workspace_id}` -- soft delete workspace

### B-12: Export Artifact Download

**Priority:** High -- blocks F-6A (export UI)

The export endpoint (`POST /exports`) creates export records and generates checksums, but there is no download endpoint. The frontend needs a way to download the generated PDF/PPTX/XLSX files.

**Required endpoint:**
- `GET /v1/workspaces/{workspace_id}/exports/{export_id}/download` -- stream the artifact file with correct MIME type and content disposition

### B-14: Model Version List and Get

**Priority:** Medium -- blocks F-4A (engine run UI)

Only `POST /v1/engine/models` exists for model registration. The frontend needs to list available models to populate dropdowns when configuring runs.

**Required endpoints:**
- `GET /v1/engine/models` -- list all registered model versions
- `GET /v1/engine/models/{model_version_id}` -- get model version details (sector_count, base_year, source, checksum)

### B-16: Run-from-Scenario Convenience

**Priority:** Low -- F-4A can work without it (manual shock vector construction)

Currently, running a scenario requires manually constructing shock vectors from the compiled scenario. A convenience endpoint would auto-build the shock vector from the scenario's compiled shock items.

**Required endpoint:**
- `POST /v1/workspaces/{workspace_id}/scenarios/{scenario_id}/run` -- compile and run in one step

### B-17: Full Compilation Result

**Priority:** Medium -- blocks F-3A (HITL mapping UI)

The current `GET /compiler/{compilationId}/status` endpoint only returns counts (high/medium/low confidence). The frontend HITL mapping UI needs the full list of suggestions with line item IDs, sector codes, confidence scores, and explanations to render an interactive approval table.

**Required endpoint:**
- `GET /v1/workspaces/{workspace_id}/compiler/{compilation_id}` -- return full compilation with all `mapping_suggestions`, `split_proposals`, and `assumption_drafts`

## Dependency Graph

```
F-1 (Shell + Auth)  ←── B-1 (Workspace CRUD)
F-3A (Compiler UI)  ←── B-17 (Full compilation result)
F-4A (Engine UI)    ←── B-14 (Model version list)
F-4A (Engine UI)    ←── B-16 (Run-from-scenario) [nice-to-have]
F-6A (Export UI)    ←── B-12 (Export download)
```
