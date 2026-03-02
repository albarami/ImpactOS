# Sprint 2 Design: Read APIs (B-2, B-3, B-9, B-10)

**Date**: 2026-03-02
**Branch**: `phase3b-sprint2-read-apis`
**Baseline**: 3356 tests, alembic at `fa33e2cd9dda` (head)

## Endpoints

| Ticket | Method | Path | Description |
|--------|--------|------|-------------|
| B-2 | GET | `/v1/workspaces/{workspace_id}/documents` | Document list (paginated) |
| B-3 | GET | `/v1/workspaces/{workspace_id}/documents/{doc_id}` | Document detail + extraction status + line item count |
| B-9 | GET | `/v1/workspaces/{workspace_id}/scenarios` | Scenario list (latest version per spec, paginated) |
| B-10 | GET | `/v1/workspaces/{workspace_id}/scenarios/{scenario_id}` | Scenario detail (full fields, derived status) |

## Pagination Pattern (shared)

Cursor-based using `created_at` timestamp + UUID tie-breaker:
- `limit: int = 20` (query param)
- `cursor: str | None = None` (query param, opaque base64-encoded `{timestamp}|{uuid}`)
- Response envelope: `{ items, total, next_cursor }`

## Scenario Status Derivation

No explicit status column. Derived from data:
- `version == 1` AND `shock_items == []` → `"DRAFT"`
- `shock_items != []` → `"COMPILED"`

Lock tracking is not stored on the row (lock endpoint just bumps version).
A future sprint can add a `locked` boolean if needed.

## Repository Additions

### DocumentRepository
- `list_by_workspace_paginated(workspace_id, limit, cursor)` → `(list[DocumentRow], total, next_cursor)`

### ExtractionJobRepository
- `get_latest_by_doc(doc_id)` → `ExtractionJobRow | None` (latest job, any status)

### LineItemRepository
- `count_by_doc(doc_id)` → `int`

### ScenarioVersionRepository
- `list_latest_by_workspace(workspace_id, limit, cursor)` → `(list[ScenarioSpecRow], total, next_cursor)`

## Files Changed

- `src/api/documents.py` — add GET list + GET detail
- `src/api/scenarios.py` — add GET list + GET detail
- `src/repositories/documents.py` — add paginated list, count
- `src/repositories/scenarios.py` — add workspace list
- `tests/api/test_documents_read.py` — new test file
- `tests/api/test_scenarios_read.py` — new test file
- `openapi.json` — regenerated
