# E2E Baseline Evidence — main @ 53a647b

**Date:** 2026-03-03
**Branch:** main
**Commit:** 53a647b (Merge PR #12 — Sprint 10 AuthN/AuthZ)
**Includes:** Sprint 9 (LLM Provider Rollout) + Sprint 10 (AuthN/AuthZ Rollout)

## Test Suite

```
python -m pytest tests -q
3838 passed, 27 warnings in 125.04s
```

## Alembic

```
python -m alembic current  -> 010 (head)
python -m alembic heads    -> 010 (head)
python -m alembic check    -> No new upgrade operations detected.
```

## OpenAPI

```
openapi.json valid: 88 paths, 145 schemas
```

## Security Posture

**Non-production.** Auth is enforced on all protected routes but with
development-grade security (HS256 self-signed JWT, dev stub users).

**Deploy blocker:** Issue #13 must be closed before production deployment.
Covers: role gates on sensitive endpoints, external IdP/RS256, final auth
matrix + penetration checks.

## Deploy Checklist

- [x] All tests pass (3838)
- [x] Alembic at head (010), check clean
- [x] openapi.json valid
- [ ] **Issue #13: Security Gate** — REQUIRED before production deploy
  - [ ] Role gates on sensitive endpoints (model registration, governed export, scenario lock)
  - [ ] External IdP / RS256 token validation
  - [ ] Final auth matrix review + penetration checks
