# Sprint 20 Prompt: Phase 3 Structural Path Analysis + Chokepoint Analytics (MVP-20)

Use this prompt exactly with Claude Code.

---

You are implementing **Sprint 20** for ImpactOS.

## Mission

Implement only MVP-20 scope:

- build deterministic **Structural Path Analysis (SPA)** for run outputs,
- compute and expose **chokepoint analytics** (critical path identification in supply chains),
- persist SPA/chokepoint artifacts as first-class run-linked analytics,
- expose additive API contracts for portal and export consumers,
- preserve all current API/auth/security behavior from Sprints 9-19.

No frontend feature work in this sprint.  
No MVP-21 portfolio optimization work in this sprint.  
No MVP-22 live workshop dashboard work in this sprint.  
No MVP-23 advanced variance/explainability work in this sprint.

## Superpowers Plugins - Required Usage (All 14)

You must explicitly use **all 14 Superpowers v4.3.1 skills** and include a final usage log.

### 1) Collaboration / Planning
1. **using-superpowers** - Declare skill execution plan at start.
2. **brainstorming** - Map run outputs -> structural path decomposition -> chokepoint scoring -> API exposure.
3. **writing-plans** - Write short implementation plan after audit.
4. **executing-plans** - Execute in required order.
5. **subagent-driven-development** - Split streams (engine math, persistence/repo, API/tests/docs).
6. **dispatching-parallel-agents** - Run independent test/doc tasks in parallel.

### 2) Build / Test / Debug
7. **test-driven-development** - Add failing tests first for each MVP-20 behavior.
8. **systematic-debugging** - Debug chain: run retrieval -> SPA math -> persistence -> API response.

### 3) Review / Quality
9. **requesting-code-review** - Request focused review from `code-reviewer`.
10. **receiving-code-review** - Apply review findings.
11. **verification-before-completion** - Run full verification before finish.

### 4) Git Workflow
12. **using-git-worktrees** - Use isolated sprint branch/worktree.
13. **finishing-a-development-branch** - Commit, push, open PR, no direct merge.

### 5) Meta
14. **writing-skills** - Capture reusable structural-path/chokepoint implementation patterns.

## Hard Constraints

1. Preserve architecture: FastAPI + repository + DI + SQLAlchemy + deterministic service abstractions.
2. Deterministic math only (no AI/LLM in SPA decomposition or chokepoint scoring).
3. No breaking changes to existing public API contracts (additive only).
4. Keep Sprint 11+ auth behavior unchanged (`401/403/404` semantics).
5. Workspace scoping must remain strict for all SPA/chokepoint reads/writes.
6. Non-dev behavior must fail closed with explicit reason codes for invalid analytics requests.
7. Existing run/depth/export/governance endpoints remain backward-compatible.
8. Secret safety: no raw credentials/tokens/sensitive payload leaks in logs/errors.

## CRITICAL: Audit Before Editing

Run and report findings before any code edits.

```powershell
Select-String -Path "src\engine\leontief.py" -Pattern "solve|solve_phased|delta_x_total|A|B"
Select-String -Path "src\api\depth.py" -Pattern "plans|artifacts|suite|workspace|status_code"
Select-String -Path "src\api\runs.py" -Pattern "get_run_results|create_run|get_batch_status|result_sets"
Select-String -Path "src\api\exports.py" -Pattern "variance|run_id|workspace|status_code"
Select-String -Path "src\models\depth.py" -Pattern "DepthStepName|DepthPlanStatus|SuitePlanningOutput"
Select-String -Path "src\models\run.py" -Pattern "RunSnapshot|ResultSet|metric_type|values"
Select-String -Path "src\db\tables.py" -Pattern "DepthArtifactRow|ResultSetRow|RunSnapshotRow|workspace_id"
Select-String -Path "src\repositories\depth.py" -Pattern "DepthPlanRepository|DepthArtifactRepository|get_by_plan"
Select-String -Path "src\repositories\engine.py" -Pattern "RunSnapshotRepository|ResultSetRepository|get_by_run"
Select-String -Path "tests\agents\depth\test_api_depth.py" -Pattern "status_code|artifacts|suite|workspace"
Select-String -Path "tests\integration\test_path_depth.py" -Pattern "path|depth|suite|disclosure"
Select-String -Path "tests\integration\test_path_engine.py" -Pattern "run|engine|result|path"
python -m pytest --co -q | Select-Object -Last 1
python -m alembic current
python -m alembic heads
python -m alembic check
```

Report:

- exact current gap between existing depth/path coverage and required MVP-20 SPA/chokepoint analytics,
- persistence/versioning gap for storing structured path/chokepoint results,
- API/runtime exposure gap for deterministic path analytics consumption,
- baseline test collection count.

**STOP and report audit findings before editing.**

## Mandatory Files

- `src/engine/leontief.py`
- `src/engine/structural_path.py` (new)
- `src/models/depth.py`
- `src/models/run.py`
- `src/models/path.py` (new)
- `src/db/tables.py`
- `src/repositories/engine.py`
- `src/repositories/depth.py`
- `src/repositories/path_analytics.py` (new)
- `src/api/depth.py`
- `src/api/runs.py`
- `src/api/main.py`
- `tests/agents/depth/test_api_depth.py`
- `tests/integration/test_path_depth.py`
- `tests/integration/test_path_engine.py`
- `tests/integration/test_path_benchmark.py`
- `tests/api/test_paths.py` (new)
- `tests/repositories/test_path_analytics.py` (new)
- `alembic/versions/*`
- `docs/ImpactOS_Master_Build_Plan_v2.md`
- `docs/ImpactOS_Technical_Specification_v1_0.md`

## Implementation Scope

### S20-1: Deterministic Structural Path Decomposition Engine

Implement deterministic SPA logic over run/model artifacts.

Required outcomes:

- compute path contributions by configurable depth (e.g., k-hop decomposition),
- expose top-K structural paths with deterministic ranking/tie-break rules,
- ensure contribution identities hold against aggregate totals within numeric tolerance,
- stable reason-code taxonomy for invalid decomposition requests.

Tests (TDD):

- known toy-model fixture validates exact path contribution outputs,
- decomposition identity tests (path sums vs aggregate impact) pass,
- deterministic repeatability tests (same run/config -> identical output).

### S20-2: Chokepoint Analytics + Persistence

Persist chokepoint analytics as first-class, queryable artifacts.

Required outcomes:

- compute chokepoint scores (influence/dependency concentration) deterministically,
- persist analysis rows linked to `run_id` and `workspace_id`,
- version/config metadata and checksum captured for reproducibility,
- additive persistence only; no regression to existing result paths.

Tests (TDD):

- repository round-trip tests for SPA/chokepoint payloads,
- uniqueness/idempotency behavior for same run+config,
- backward-compat tests confirm existing run result repositories unchanged.

### S20-3: API Additive Exposure for Path Analytics

Expose SPA/chokepoint outputs through additive workspace-scoped endpoints.

Required outcomes:

- add endpoint(s) to create/retrieve path analytics for a run,
- preserve existing run/depth response contracts;
- include explicit 422 reason codes for invalid configs/mismatches,
- retain `401/403/404` semantics and strict workspace isolation.

Tests (TDD):

- endpoint tests for success path and response schema,
- authz/workspace isolation matrix tests,
- invalid configuration tests with structured reason codes.

### S20-4: Docs + Evidence + Contract Sync

Required outcomes:

- update release-readiness checklist with Sprint 20 section,
- document SPA formula/identity checks and chokepoint scoring contract,
- refresh OpenAPI and prove additive compatibility.

Tests (TDD):

- evidence/checklist section presence test,
- contract tests for additive fields and unchanged legacy fields,
- arithmetic parity tests for path decomposition identities.

## Execution Order

1. Audit + findings report.
2. Add failing tests for S20-1 and S20-2.
3. Implement S20-1 and S20-2; run targeted tests.
4. Add failing tests for S20-3 and S20-4.
5. Implement S20-3 and S20-4; run targeted tests.
6. Reconcile helpers/refactor duplicates.
7. Code review + apply findings.
8. Full verification + docs/evidence refresh.

## Verification Commands

```powershell
python -m pytest tests/agents/depth/test_api_depth.py tests/api/test_paths.py tests/repositories/test_path_analytics.py -q
python -m pytest tests/integration/test_path_depth.py tests/integration/test_path_engine.py tests/integration/test_path_benchmark.py -q
python -m pytest tests/integration/test_cross_module_consistency.py tests/integration/test_path_doc_to_export.py -q
python -m pytest tests -q
python -m alembic current
python -m alembic check
python -m ruff check src tests
python -c "import json; from pathlib import Path; from src.api.main import app; Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
python -c "import json; json.load(open('openapi.json', 'r', encoding='utf-8')); print('openapi.json valid')"
```

## Git Requirements

1. Branch: `phase3-sprint20-structural-path-analytics`
2. Commit messages:
   - `[sprint20] implement deterministic structural path decomposition engine`
   - `[sprint20] add chokepoint analytics persistence and repository wiring`
   - `[sprint20] expose additive workspace-scoped path analytics api contracts`
   - `[sprint20] add mvp20 structural path evidence and refresh openapi`
3. Push + open PR (unmerged, review-ready).

## Deliverables

1. Deterministic SPA decomposition implemented and tested.
2. Chokepoint analytics persisted/retrievable with reproducibility metadata.
3. Additive path analytics API exposure with authz/backward compatibility preserved.
4. Docs/evidence updated with decomposition and chokepoint contracts.
5. PR opened with verification outputs and superpowers usage log (all 14).

---

At the end, provide:

- exact files changed,
- structural path matrix (`path_type -> formula -> output field -> validation`),
- chokepoint matrix (`score -> meaning -> threshold -> fail mode -> reason code`),
- verification outputs summary,
- explicit superpowers usage log (all 14),
- explicit MVP-20 completion confirmation.
