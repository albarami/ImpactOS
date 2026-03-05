# ImpactOS Full-System Completion Master Plan (Post-Phase 3B)

Date: 2026-03-04 (updated)
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
| 23 | MVP-23 | Advanced Variance Bridges + Explainability | 4609 | 331efcc | sprint-23-complete | 2026-03-05 |

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
10. Sprint 23: MVP-23 Advanced Variance Bridges + explainability package — done (331efcc, tag sprint-23-complete)

### Wave C: Full go-live proof

11. Sprint 24: Full-system staging proof (all layers) + production go/no-go dossier

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

- Sprint 23 (MVP-23 Advanced Variance Bridges + Explainability) complete at 331efcc, tag sprint-23-complete.
- All Phase 1-3 MVPs (1-23) complete. Proceed to Sprint 24 (full-system staging proof).
- Do not start production deployment until Sprint 24 go/no-go criteria pass.

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

Run readiness and smoke:

```powershell
curl http://localhost:8000/readiness
python -m pytest tests/integration/test_path_doc_to_export.py -q
python -m pytest tests/integration/test_governance_chain.py -q
```

If this passes with real creds/config, you will see the system running live end-to-end for the currently implemented scope.
