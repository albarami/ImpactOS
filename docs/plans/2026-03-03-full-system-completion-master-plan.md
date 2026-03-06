# ImpactOS Full-System Completion Master Plan (Post-Phase 3B)

Date: 2026-03-06 (updated)
Owner: Backend + Data + Frontend + Ops

## 1) What is complete now

Based on merged work on `main`:

- Phase 1 foundation (MVP-1 through MVP-7): complete.
- Phase 2-A/2-B/2-C (MVP-8 through MVP-13): complete.
- Phase 3B security and release hardening (Sprints 9-12): complete and merged.
- Wave A methodology parity (MVP-14 through MVP-18): complete.
- Wave B premium boardroom (MVP-19 through MVP-23): complete.

### Completion evidence

| Sprint | MVP | Component | Tests | Commit | Tag | Date |
|--------|-----|-----------|-------|--------|-----|------|
| 14 | MVP-14 | Phase 2 Integration + Gate | 1999 | 7a9db9f | - | 2026-02-28 |
| 15 | MVP-15 | Type II Induced Effects | 3980 | 7e98ffc | - | 2026-03-01 |
| 16 | MVP-16 | Value Measures Satellite | 4114 | 4374376 | sprint-16-complete | 2026-03-02 |
| 17 | MVP-17 | RunSeries Annual Storage + API | 4220 | 1b2ab3e | sprint-17-complete | 2026-03-02 |
| 18 | MVP-18 | SG Model Import Adapter | 4220 | a522d45 | sprint-18-complete | 2026-03-03 |
| 19 | MVP-19 | Client Portal Collaboration | 4347 | 1d6dae2 | sprint-19-complete | 2026-03-03 |
| 20 | MVP-20 | Structural Path Analysis + Chokepoints | 4422 | e284aa8 | sprint-20-complete | 2026-03-04 |
| 21 | MVP-21 | Portfolio Optimization | 4506 | ee25cdf | sprint-21-complete | 2026-03-04 |
| 22 | MVP-22 | Live Workshop Dashboard | 4556 | a9c0729 | sprint-22-complete | 2026-03-04 |
| 23 | MVP-23 | Advanced Variance Bridges + Explainability | 4609 | 33303cf | sprint-23-complete | 2026-03-05 |
| 24 | S24 | Full-System Staging Proof + Go/No-Go | 4932 | 1146f70 | - | 2026-03-05 |
| 25 | S25 | Economist Copilot v1 (Chat + Agent) | 4698 + 320 FE | 599ec87 | sprint-25-complete | 2026-03-05 |
| 26 | S26 | Copilot Hardening (Backlog Burn-Down) | 4728 + 328 FE | 0d0ab79 | sprint-26-complete | 2026-03-05 |
| 27 | S27 | Copilot Tool Execution (Operationalization) | 4852 + 336 FE | ec3dca8 | sprint-27-complete | 2026-03-06 |
| 28 | S28 | Copilot Real Execution + Post-Execution Narrative | 4938 + 348 FE | In progress | - | 2026-03-06 |

## 2) What is not complete yet (blocking "all layers/components")

From `docs/ImpactOS_Master_Build_Plan_v2.md`, the remaining scope is:

- (none — all planned MVPs complete)

## 3) Program sequence (no ambiguity)

### Wave A: Methodology parity — COMPLETE

1. Sprint 14: MVP-14 Saudi Data Foundation — done (7a9db9f)
2. Sprint 15: MVP-15 Type II induced effects — done (7e98ffc)
3. Sprint 16: MVP-16 Value Measures satellite — done (4374376)
4. Sprint 17: MVP-17 RunSeries annual storage + API — done (1b2ab3e)
5. Sprint 18: MVP-18 SG import adapter + parity benchmark gate — done (a522d45)

### Wave B: Premium boardroom layer — COMPLETE (5 of 5 done)

6. Sprint 19: MVP-19 Client Portal (authz-safe collaboration flows) — done (1d6dae2)
7. Sprint 20: MVP-20 Structural Path Analysis — done (e284aa8)
8. Sprint 21: MVP-21 Portfolio Optimization — done (ee25cdf, tag sprint-21-complete)
9. Sprint 22: MVP-22 Live Workshop Dashboard — done (a9c0729, tag sprint-22-complete)
10. Sprint 23: MVP-23 Advanced Variance Bridges + explainability package — done (33303cf, tag sprint-23-complete)

### Wave C: Full go-live proof — COMPLETE

11. Sprint 24: Full-system staging proof + go/no-go dossier — done (1146f70)
    - Carryover I-2 CLOSED: ScenarioSpec wired to bridge engine (8bece0c)
    - Carryover I-4 CLOSED: RunSelector populated from workspace runs (d9829c6)
    - Staging proof evidence: `docs/evidence/sprint24-staging-proof.md`
    - Go/No-Go dossier: `docs/evidence/sprint24-go-no-go-dossier.md`

### Wave D: AI-Assisted Workflows — COMPLETE

12. Sprint 25: Economist Copilot v1 — merged (PR #30 → `599ec87`, tag `sprint-25-complete`)
    - Conversational AI economist assistant with versioned prompt (`copilot_v1`)
    - Chat persistence: migration 020, `chat_sessions` + `chat_messages` tables
    - Confirmation gate: `build_scenario` and `run_engine` require user approval
    - Trace metadata: provenance on every results message (run_id, scenario, confidence)
    - Agent-to-math boundary enforced: LLM never computes numbers
    - Post-merge verification: 4698 backend passed (29 skipped), 320 frontend passed
    - Alembic: `020_chat_sessions_messages (head)`, no drift
    - Evidence: `docs/evidence/sprint25-copilot-evidence.md`
    - Known gaps → Sprint 26 backlog: S26-BL-1 (multi-turn history), S26-BL-2 (chatFetch client), S26-BL-3 (nested JSON regex), S26-BL-4 (unused settings), S26-BL-5 (unstructured LLM mode)

13. Sprint 26: Copilot Hardening (Backlog Burn-Down) — merged (PR #31 → `0d0ab79`, tag `sprint-26-complete`)
    - All 5 Sprint 25 backlog items resolved: S26-BL-1 through S26-BL-5
    - Multi-turn history: LLMRequest `messages` field, all 3 providers updated
    - Unstructured mode: `call_unstructured()`, `_DummySchema` removed
    - Nested JSON parser: balanced-brace extractor replaces regex
    - Settings wiring: COPILOT_MODEL/COPILOT_MAX_TOKENS into runtime
    - Frontend migration: useChat hooks to shared openapi-fetch client
    - Zero new product surface, full backward compatibility
    - Post-merge verification: 4728 backend passed (29 skipped), 328 frontend passed
    - Evidence: `docs/evidence/sprint25-copilot-evidence.md` (Sprint 26 Resolutions section)

14. Sprint 27: Copilot Tool Execution (Operationalization) — merged (PR #32 → `ec3dca8`, tag `sprint-27-complete`)
    - `ChatToolExecutor` with 5 workspace-scoped tool handlers: `lookup_data`, `build_scenario`, `run_engine`, `narrate_results`, `create_export`
    - Safety caps: max 5 tool calls/turn, max 1 `run_engine` + 1 `create_export` per turn
    - `run_engine`: dry-run validation MVP (validates scenario in workspace, honors `scenario_spec_version` for provenance pinning; full `BatchRunner.run()` deferred)
    - `create_export`: initiation only (creates PENDING row, workspace-scoped RunSnapshot guard; ExportOrchestrator deferred)
    - Runtime wiring: `_build_copilot()` factory, `COPILOT_ENABLED` kill switch, fail-closed non-dev (503)
    - Trace metadata: populated from execution results; `run_id` suppressed from dry-run
    - Frontend: status badges on tool calls, deep links to runs/exports
    - Post-merge verification: 4852 backend passed (29 skipped), 336 frontend passed
    - Evidence: `docs/evidence/sprint25-copilot-evidence.md` (Sprint 27 section)
    - Design: `docs/plans/2026-03-05-sprint27-copilot-tool-execution-design.md`

15. Sprint 28: Copilot Real Execution + Post-Execution Narrative — merged (PR #33 → `bcd9c10`, tag `sprint-28-complete`)
    - Shared `RunExecutionService` and `ExportExecutionService` extracted for reuse across API and chat
    - `run_engine` wired to real `BatchRunner.run()` with persisted RunSnapshot + ResultSet (closes S27 dry-run deferral)
    - `create_export` wired to real `ExportOrchestrator.execute()` with governance gates (returns COMPLETED/BLOCKED/FAILED)
    - Post-execution narrative: `ChatNarrativeService` + `EconomistCopilot.enrich_narrative()`
    - Frontend: export blocking reasons, deep links, amber badge for BLOCKED status
    - Post-merge verification: 4958 backend passed (29 skipped), 350 frontend passed
    - Evidence: `docs/evidence/sprint25-copilot-evidence.md` (Sprint 28 section)

16. Sprint 29: Staging Activation + Release Candidate Closeout — merged (PR #34 → 0e1d33e, tag sprint-29-complete)
    - Repeatable staging preflight: `scripts/staging_preflight.py` (6 checks, structured JSON, secret redaction)
    - Staging smoke harness: `scripts/staging_smoke.py` (6 ordered stages, cascade-skip)
    - Non-dev fail-closed audit: all 14 paths verified, no gaps found
    - Release evidence refreshed: go/no-go dossier updated from CONDITIONAL GO to GO
    - Evidence: `docs/evidence/sprint29-staging-activation.md`

## 4) Definition of "fully built and wired"

The system is only considered fully complete when all are true:

1. MVP-1 through MVP-23 marked complete with code/test evidence.
2. No planned entries remain in the build tracker.
3. Real staging E2E works across full path:
   - auth (external IdP)
   - document extraction (real provider policy)
   - compiler + depth agents (real LLM in non-dev or fail-closed)
   - deterministic engine runs
   - governance/NFF
   - delivery/export/download
   - premium workflows (portal + optimization + structural + workshop + advanced variance)
4. Methodology parity gate passed against SG benchmark dataset.
5. Readiness + rollback runbook evidence complete and reproducible.

## 5) Immediate next action

- Sprint 25 (Economist Copilot v1) merged: PR #30 → `599ec87`, tag `sprint-25-complete`.
- Sprint 26 (Copilot Hardening) merged: PR #31 → `0d0ab79`, tag `sprint-26-complete`. All 5 backlog items resolved.
- Sprint 27 (Copilot Tool Execution) merged: PR #32 → `ec3dca8`, tag `sprint-27-complete`. Executor infrastructure with workspace-scoped handlers, safety caps, version pinning. `run_engine` is dry-run MVP; full engine execution deferred.
- Sprint 28 (Copilot Real Execution) merged: PR #33 → `bcd9c10`, tag `sprint-28-complete`. All S27 dry-run deferrals closed.
- Sprint 29 (Staging Activation) merged: PR #34 → `0e1d33e`, tag `sprint-29-complete`. Preflight/smoke automation, copilot runtime probe, fail-closed audit, evidence refresh.
- All Phase 1-3 MVPs (1-23) complete. Sprint 24 carryovers (I-2, I-4) closed. Sprints 25-29 merged.
- Post-Sprint 29 verification (on main): 5016 backend passed (29 skipped), 350 frontend passed, alembic head `020_chat_sessions_messages`, no drift.
- Go/No-Go dossier: GO (updated post-Sprint 29). Infrastructure prerequisites only.
- See `docs/evidence/sprint24-go-no-go-dossier.md` for full criteria and rollback plan.
- See `docs/evidence/sprint25-copilot-evidence.md` for copilot evidence (Sprints 25-28).
- See `docs/evidence/sprint29-staging-activation.md` for staging activation evidence.

## 6) Minimum environment needed to see "live" behavior

Set real non-dev config (staging profile):

- `ENVIRONMENT=staging`
- `JWT_ISSUER`, `JWT_AUDIENCE`, `JWKS_URL` (external IdP)
- Real provider keys/config (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` and extraction provider config)
- Non-local object storage config
- Non-placeholder `DATABASE_URL`, `REDIS_URL`, strong `SECRET_KEY`

Bring stack up:

```powershell
docker compose up -d postgres redis minio
python -m alembic upgrade head
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
celery -A src.ingestion.tasks.celery_app worker -l info
cd frontend
pnpm install
pnpm dev
```

Run preflight and smoke:

```powershell
# Preflight (before starting server — validates config + alembic)
python scripts/staging_preflight.py --json

# After server is up — one-command smoke verification
python scripts/staging_smoke.py --json --url http://localhost:8000

# Integration tests (optional — deeper path verification)
python -m pytest tests/integration/test_path_doc_to_export.py -q
python -m pytest tests/integration/test_governance_chain.py -q
```

If this passes with real creds/config, you will see the system running live end-to-end for the currently implemented scope.
