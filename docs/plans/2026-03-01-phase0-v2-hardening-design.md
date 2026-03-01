# Phase 0 v2: Remaining Hardening & Workflow Wiring — Design

**Date:** 2026-03-01
**Status:** Approved
**Scope:** Close remaining operational gaps on current main without rebuilding existing infrastructure.

## Context

The repo already has: DB-backed repositories, async SQLAlchemy with UoW,
22+ ORM tables, Docker stack (postgres/redis/minio), extraction providers
(LocalPdfProvider, AzureDIProvider), Celery wiring, CORS, workspace-scoped
routers, quality provenance fields on RunQualityAssessment, and an export
orchestrator that blocks governed exports on synthetic fallback.

This is a **hardening sprint**, not a new architecture sprint.

## Repo Facts This Plan Assumes

- `ExportOrchestrator.execute()` already accepts `quality_assessment` and
  blocks governed exports when `used_synthetic_fallback` is true, but
  `src/api/exports.py` still only passes `claims`.
- `src/api/scenarios.py` compiles from payload-built line items and
  decisions. `src/api/compiler.py` supports document-backed loading from
  the latest completed extraction. These are **different paths** (deterministic
  vs AI suggestion) and must not be collapsed.
- `src/api/documents.py` hardcodes `DocumentStorageService(storage_root="./uploads")`
  even though settings already expose `OBJECT_STORAGE_PATH` and MinIO config.
- `/health` currently checks database only.
- `src/ingestion/extraction.py` contains a stale class docstring saying PDF
  support is not implemented, even though the provider architecture exists.
- Do not re-open already-finished provenance work unless tests prove a regression.

## Non-Goals

- Do not rebuild repositories / ORM / Docker / Celery / persistence.
- Do not modify `src/governance/publication_gate.py`.
- Do not create a parallel quality-provenance model.
- Do not add RunSnapshot provenance fields again.
- Do not add the `real_data` pytest marker again.
- Do not make `scenarios.py` delegate to `compiler.py`.

## Gap Fixes

### G1: Export-Quality Wiring (`src/api/exports.py`)

Inject `DataQualityRepository` via `Depends(get_data_quality_repo)`. Load
the run's saved quality summary, convert to `RunQualityAssessment`, pass
into `_orchestrator.execute(quality_assessment=...)`. If no summary exists,
pass `None` and preserve current behavior.

**Files:** `src/api/exports.py`

### G2: Compile Flow Consolidation (`src/api/scenarios.py`)

**Architectural rule:** `scenarios.py` is the deterministic ScenarioCompiler
path producing shock_items. `compiler.py` is the AI suggestion path returning
mapping suggestions. These are different layers — never collapse them.

Fix:
- Deprecate payload-only compile in `scenarios.py`.
- Add a document-backed deterministic compile path that:
  1. Loads extracted line items from storage/repo.
  2. Loads persisted mapping decisions.
  3. Feeds them into ScenarioCompiler.
- Keep payload-based compile only as temporary compatibility, marked
  deprecated and non-authoritative.
- If stored mapping decisions lack a clean retrieval path, add the
  smallest persistence/query helper needed.

**Files:** `src/api/scenarios.py`, possibly small helper code.

### G3: DI-Driven Document Storage (`src/api/documents.py`)

Add `get_document_storage()` factory in `src/api/dependencies.py` reading
`settings.OBJECT_STORAGE_PATH`. Inject via `Depends()` into document
endpoints. Preserve local-dev default. Make overridable in tests.

**Files:** `src/api/documents.py`, `src/api/dependencies.py`

### G4: Expanded Health Checks (`src/api/main.py`)

Add Redis and object-storage checks to `/health`:
- Redis: `redis.asyncio.from_url(settings.REDIS_URL).ping()`
- Object storage: `os.path.isdir(settings.OBJECT_STORAGE_PATH)` for local;
  MinIO `head_bucket` if S3 mode detected.
- All checks concurrent via `asyncio.gather`.
- Return degraded status, not hard failure.

Response shape: `{"api": true, "database": true, "redis": true, "object_storage": true}`

**Files:** `src/api/main.py`

### G5: Extraction Docstring Reconciliation (`src/ingestion/extraction.py`)

Update module and class docstrings to reflect actual architecture:
- CSV/Excel deterministic extraction in ExtractionService
- PDF/layout via provider-based flow (LocalPdfProvider, AzureDIProvider)
- Async dispatch via tasks/Celery

Verify Makefile `validate-model` path before changing.

**Files:** `src/ingestion/extraction.py`, possibly `Makefile`

### G6: Test Strategy Alignment

All new tests use the same DI/settings-driven storage and config as
production. No parallel test-only architecture. Use FastAPI dependency
overrides for test isolation.

## Execution Order

| Step | Task | Commit message |
|------|------|---------------|
| 0 | Baseline freeze + failing gap tests | `[phase0-v2] add failing tests for remaining hardening gaps` |
| 1 | G1: export-quality wiring | `[phase0-v2] wire quality assessment into export route` |
| 2 | G2: compile flow consolidation | `[phase0-v2] converge deterministic compile flow onto stored document data` |
| 3 | G3: DI document storage | `[phase0-v2] inject document storage from settings` |
| 4 | G4: health checks | `[phase0-v2] expand health endpoint to redis and storage` |
| 5 | G5: extraction docs | `[phase0-v2] align extraction docs and health/storage hardening` |
| 6 | E2E hardening test | `[phase0-v2] add end-to-end hardening integration coverage` |
| 7 | Docs/runbook refresh | `[phase0-v2] update docs for hardened workflow wiring` |

Checkpoints after Tasks 2 and 5 for progress review.

## Success Criteria

1. `exports.py` passes `quality_assessment` to ExportOrchestrator
2. Governed export blocks on unresolved claims AND synthetic fallback
3. Deterministic scenario compile no longer depends on payload-built line items
4. Document storage root is settings-driven
5. `/health` checks DB + Redis + storage
6. Extraction docstrings match actual architecture
7. One E2E integration test proves the full stored-document workflow
8. All existing tests still pass
9. Branch remains unmerged and review-ready

## Git Strategy

Isolated worktree branch `phase0-v2-hardening`. One commit per step.
Branch left unmerged for review.
