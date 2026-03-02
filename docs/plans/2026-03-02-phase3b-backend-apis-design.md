# Phase 3B Backend API Additions — Design Document

**Date:** 2026-03-02
**Branch:** `phase3b-backend-apis` (from main after Phase 3A merge)
**Scope:** 17 ticket groups (B-1 through B-17), purely backend Python/FastAPI
**Baseline:** 3,283 tests, 70 workspace-scoped endpoints, 34 ORM tables

## Purpose

Phase 3A frontend works against existing endpoints but shows placeholders where backend CRUD is missing. This sprint adds 17 groups of endpoints so the frontend team can build the full HITL workstation, scenario management, claim resolution, and export download.

## Architecture

All new endpoints follow the existing Repository + DI + SQLAlchemy pattern:
- Repository classes in `src/repositories/` with `AsyncSession` injection
- DI factories in `src/api/dependencies.py`
- ORM tables in `src/db/tables.py`
- Alembic migrations for schema changes
- Pydantic request/response schemas inline in router files

No module-level dicts. No in-memory stores (except B-13 dev auth tokens).

## Codebase Audit Findings

### Existing Infrastructure
- **WorkspaceRepository** exists (create/get/list) — needs `update()` + DI factory
- **DocumentRepository** exists with `list_by_workspace()` and `get()` — no list/detail endpoints
- **ScenarioVersionRepository** exists — no list/get endpoints
- **ClaimRepository** exists with `get_by_run()` and `update_status()` — no endpoints
- **ModelVersionRepository** exists with `list_all()` and `get()` — no workspace-scoped endpoints
- **CompilationRepository** exists — status endpoint exists but no full detail
- **ExportRepository** exists — no download endpoint, no artifact persistence

### Missing Infrastructure
- **MappingDecisionRepository** — table exists (MappingDecisionRow), no repository
- **EvidenceSnippetRepository** — table exists (EvidenceSnippetRow), no repository
- **AuditTrailRow** — new table needed
- **Evidence NOT persisted** in ingestion (tasks.py:129-147 generates snippets but never writes to DB)
- **Export artifacts NOT persisted** (bytes returned in API response then lost)

### Taxonomy Data Available
- `data/curated/sector_taxonomy_isic4.json` — 20 ISIC Rev.4 sections (A-U) with Arabic names
- `data/curated/sector_taxonomy_isic4_divisions.json` — 97 ISIC divisions
- No seed data creation needed

## Schema Changes (Alembic Migration 007)

### New Table: AuditTrailRow
```
audit_id (UUID, PK)
compilation_id (UUID, indexed)
line_item_id (UUID)
action (str) — BULK_APPROVE, OVERRIDE, ESCALATE, etc.
from_state (str)
to_state (str)
actor (str)
rationale (str)
created_at (datetime)
```

### Modified: MappingDecisionRow
- Add `compilation_id` (UUID, indexed) if missing
- Add `rationale` (str, nullable) if missing
- Verify `decided_by`, `state`, `decision_type` columns exist

### Modified: ExportRow
- Add `artifact_storage_key` (str, nullable) — object storage reference
- Artifacts stored as files under `exports/{export_id}/` in document storage

### Modified: EvidenceSnippetRow
- `source_id` maps to doc_id. For run-based queries (B-7), join through line_items → extraction_jobs → runs, or add optional `workspace_id` column for efficient filtering.

## New Repositories

### MappingDecisionRepository
- `create()`, `get()`, `get_by_compilation()`, `get_by_line_item()`, `update_state()`
- Used by B-4, B-5, B-8, B-17

### EvidenceSnippetRepository
- `create()`, `create_many()`, `get()`, `get_by_source()`, `list_by_workspace()`
- Used by B-7

### AuditTrailRepository
- `create()`, `get_by_line_item()`, `get_by_compilation()`
- Used by B-8

## New Routers

### src/api/workspaces.py (B-1)
- POST /v1/workspaces
- GET /v1/workspaces
- GET /v1/workspaces/{workspace_id}
- PUT /v1/workspaces/{workspace_id}

### src/api/taxonomy.py (B-6)
- GET /v1/workspaces/{workspace_id}/taxonomy/sectors
- GET /v1/workspaces/{workspace_id}/taxonomy/sectors/search?q=
- GET /v1/workspaces/{workspace_id}/taxonomy/sectors/{sector_code}

### src/api/auth.py (B-13)
- POST /v1/auth/login
- GET /v1/auth/me
- POST /v1/auth/logout
- Only active when ENVIRONMENT == "dev"

## Endpoint Additions to Existing Routers

### documents.py: B-2, B-3
- GET /{workspace_id}/documents (list)
- GET /{workspace_id}/documents/{doc_id} (detail)

### compiler.py: B-4, B-5, B-8, B-17
- GET /{workspace_id}/compiler/{compilation_id} (full detail with decisions)
- GET /{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}
- PUT /{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}
- POST /{workspace_id}/compiler/{compilation_id}/decisions/bulk-approve
- GET /{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}/audit

### scenarios.py: B-9, B-10, B-16
- GET /{workspace_id}/scenarios (list)
- GET /{workspace_id}/scenarios/{scenario_id} (detail)
- POST /{workspace_id}/scenarios/{scenario_id}/run (convenience)

### governance.py: B-7, B-11
- GET /{workspace_id}/governance/evidence?run_id=
- GET /{workspace_id}/governance/evidence/{evidence_id}
- POST /{workspace_id}/governance/claims/{claim_id}/evidence
- GET /{workspace_id}/governance/claims?run_id=
- GET /{workspace_id}/governance/claims/{claim_id}
- PUT /{workspace_id}/governance/claims/{claim_id}

### exports.py: B-12
- GET /{workspace_id}/exports/{export_id}/download/{format}

### models.py (new file): B-14, B-15
- GET /{workspace_id}/models/versions
- GET /{workspace_id}/models/versions/{model_version_id}
- GET /{workspace_id}/models/versions/{model_version_id}/coefficients

## Execution Order

Dictated by dependencies:

1. **Phase 1** (parallel): B-1, B-6, B-13, B-14, B-15 + migration 007
2. **Phase 2** (parallel): B-2, B-3, B-9, B-10
3. **Phase 3** (sequential: B-4 first): B-4, B-5, B-8, B-17
4. **Phase 4**: B-11, B-7 (fix evidence persistence first)
5. **Phase 5**: B-12, B-16
6. **Phase 6**: Documentation, OpenAPI regen, TypeScript client regen

## Constraints

- All existing 3,283 tests must pass
- Repository + DI pattern for ALL new endpoints
- 409 for state violations (not 400)
- Proper HTTP codes: 200/201/404/409/422
- Type hints everywhere, ruff clean
- No breaking changes to existing endpoints
- Branch stays unmerged for review
