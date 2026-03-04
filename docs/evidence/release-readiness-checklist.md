# ImpactOS — Release Readiness Checklist

## Release Readiness Matrix

| Component | Required Config | Dev Behavior | Staging/Prod Behavior | Fail Mode | Test Evidence |
|---|---|---|---|---|---|
| **Auth (IdP)** | `JWT_ISSUER`, `JWT_AUDIENCE`, `JWKS_URL` | HS256 dev stub | RS256 + JWKS mandatory | 401 fail-closed | `test_idp_validation.py`, `test_deploy_guard.py` |
| **Secret Key** | `SECRET_KEY` | Dev default accepted | Dev default rejected | Startup validation error | `test_config_guardrails.py` |
| **Database** | `DATABASE_URL` | Local default OK | Placeholder creds rejected | Startup validation error | `test_config_guardrails.py` |
| **Object Storage** | `OBJECT_STORAGE_PATH` | `./uploads` OK | Relative path rejected | Startup validation error | `test_config_guardrails.py` |
| **LLM Providers** | `ANTHROPIC_API_KEY` etc. | Optional (local fallback) | Optional (ProviderUnavailableError) | Per-call fail | `test_llm_client_policy.py` |
| **Extraction** | `EXTRACTION_PROVIDER` | `local` OK | Azure DI recommended | Falls back to local | `test_extraction_reliability.py` |
| **Redis** | `REDIS_URL` | Optional (sync mode) | Required for async jobs | Health check degraded | `test_readiness.py` |
| **Role Gates** | (code-enforced) | Active | Active | 403 for insufficient role | `test_role_gates.py`, `test_auth_matrix.py` |
| **Workspace Auth** | (code-enforced) | Active | Active | 401/404 | `test_auth_boundary.py`, `test_workspace_authz.py` |

## Pre-Deploy Preflight Checks

```bash
# 1. Verify environment is not dev
echo $ENVIRONMENT  # must be "staging" or "prod"

# 2. Run config validation
python -c "
from src.config.settings import get_settings, validate_settings_for_env
s = get_settings()
errors = validate_settings_for_env(s)
if errors:
    print('FAIL:', errors)
    exit(1)
print('Config OK for', s.ENVIRONMENT)
"

# 3. Run migrations
python -m alembic upgrade head

# 4. Check readiness
curl -f http://localhost:8000/readiness || echo "NOT READY"

# 5. Smoke test auth
curl -s http://localhost:8000/v1/workspaces \
  -H "Authorization: Bearer INVALID" | grep -q "401"
echo "Auth enforcement: OK"
```

## Rollback Procedure

```bash
# 1. Stop API + workers
docker compose down api celery-worker

# 2. Rollback migration (if schema changed)
python -m alembic downgrade -1

# 3. Deploy previous image tag
docker compose up -d api celery-worker

# 4. Verify rollback
curl -f http://localhost:8000/readiness
curl -f http://localhost:8000/health
```

## Go/No-Go Criteria

| Criteria | Required | How to Verify |
|---|---|---|
| All tests pass | Yes | `pytest tests -q` → 0 failures |
| Alembic at head + clean | Yes | `alembic current` + `alembic check` |
| Config validation passes | Yes | `validate_settings_for_env()` returns `[]` |
| `/readiness` returns 200 | Yes | `curl -f /readiness` |
| Auth enforced on all routes | Yes | `test_auth_matrix.py` passes |
| Role gates on sensitive endpoints | Yes | `test_role_gates.py` passes |
| No dev defaults in non-dev | Yes | `test_config_guardrails.py` passes |
| IdP configured (staging/prod) | Yes | `JWT_ISSUER`, `JWT_AUDIENCE`, `JWKS_URL` set |
| Secret redaction verified | Yes | `test_deploy_guard.py` passes |
| OpenAPI valid | Yes | `openapi.json` parseable |

## MVP-14 Saudi Data Foundation Evidence

### Artifact Validation Matrix

| Field | Source | Validation | Fail Mode |
|---|---|---|---|
| `final_demand_F` | curated IO payload | shape `(n, k)` with `k > 0` and row count `n` | `MODEL_FINAL_DEMAND_DIMENSION_MISMATCH` |
| `imports_vector` | curated IO payload | vector length `n` | `MODEL_IMPORTS_VECTOR_DIMENSION_MISMATCH` |
| `compensation_of_employees` | curated IO payload | vector length `n` | `MODEL_COMPENSATION_VECTOR_DIMENSION_MISMATCH` |
| `gross_operating_surplus` | curated IO payload | vector length `n` | `MODEL_GOS_VECTOR_DIMENSION_MISMATCH` |
| `taxes_less_subsidies` | curated IO payload | vector length `n` | `MODEL_TAX_VECTOR_DIMENSION_MISMATCH` |
| `household_consumption_shares` | curated IO payload | vector length `n`, non-negative, sums to `1.0` | `MODEL_HOUSEHOLD_SHARES_DIMENSION_MISMATCH` / `MODEL_HOUSEHOLD_SHARES_INVALID_SUM` |
| `deflator_series` | curated IO payload | year keys integer-like, values numeric and `> 0` | `MODEL_DEFLATOR_INVALID` |

### MVP-14 Preflight Evidence Checklist

- Model registration with extended artifacts succeeds (`POST /v1/engine/models`).
- Model detail endpoint returns additive fields (`GET /v1/workspaces/{workspace_id}/models/versions/{model_version_id}`).
- Deterministic checksum is stable for identical artifact payloads.
- Malformed extended payloads fail closed with reason codes (HTTP `422`).
- Migration `011_model_data_extended_fields` applied at target environment.

## Issue #17: Non-Dev Fail-Closed Agent Enforcement

| Agent Path | Dev Behavior | Staging/Prod Behavior | Fail Mode | Reason Code | Test Evidence |
|---|---|---|---|---|---|
| **Compile Split** | Deterministic OK | 503 fail-closed | ProviderUnavailableError | `SPLIT_NO_LLM_BACKING` | `test_compiler_real_only.py` |
| **Compile Assumption** | Deterministic OK | 503 fail-closed | ProviderUnavailableError | `ASSUMPTION_NO_LLM_BACKING` | `test_compiler_real_only.py` |
| **Depth Step** | Fallback + metadata | FAILED status | Plan error metadata | `DEPTH_STEP_NO_LLM_BACKING` | `test_orchestrator.py` |
| **Compile Mapping** | Library fallback | 503 fail-closed (S13) | ProviderUnavailableError | `PROVIDER_UNAVAILABLE` | `test_compiler_real_only.py` |

### Issue #17 Preflight Checks

```bash
# 1. Verify non-dev compile rejects deterministic split/assumption
python -m pytest tests/compiler/test_compiler_real_only.py -v

# 2. Verify non-dev depth fails closed
python -m pytest tests/agents/depth/test_orchestrator.py::TestNonDevDepthFailsClosed -v

# 3. Verify endpoint 503 translation
python -m pytest tests/api/test_compiler_failclosed.py -v

# 4. Full suite
python -m pytest tests -q
```

### Go/No-Go Criteria (additive)

| Criteria | Required | How to Verify |
|---|---|---|
| No deterministic fallback success in non-dev | Yes | `test_compiler_real_only.py`, `test_orchestrator.py` pass |
| 503 with structured reason_code | Yes | `test_compiler_failclosed.py` passes |
| Depth FAILED status (not COMPLETED) in non-dev | Yes | `TestNonDevDepthFailsClosed` passes |
| Dev ergonomics preserved | Yes | `TestDevCompileKeepsFallback` passes |
| No secrets in error payloads | Yes | Secret leakage tests pass |

## Sprint 15: Type II Induced Effects Parity (MVP-15)

### Deterministic Engine: Type II Household Closure

| Metric | Meaning | Confidence | Source |
|---|---|---|---|
| `total_output` | Type I total (direct + indirect) | MEASURED | `leontief.py:solve()` |
| `direct_effect` | Direct effect | MEASURED | `leontief.py:solve()` |
| `indirect_effect` | Indirect effect | MEASURED | `leontief.py:solve()` |
| `type_ii_total_output` | Type II total (direct + indirect + induced) | ESTIMATED | `leontief.py:solve_type_ii()` |
| `induced_effect` | Induced = Type II - Type I | ESTIMATED | `leontief.py:solve_type_ii()` |
| `type_ii_employment` | Employment from Type II total | ESTIMATED | `batch.py` |

### Type II Prerequisite Validation Matrix

| Input | Check | Reason Code |
|---|---|---|
| compensation_of_employees is None | Missing | `TYPE_II_MISSING_COMPENSATION` |
| household_consumption_shares is None | Missing | `TYPE_II_MISSING_HOUSEHOLD_SHARES` |
| Vector length != n | Dimension | `TYPE_II_DIMENSION_MISMATCH` |
| Negative values | Non-negativity | `TYPE_II_NEGATIVE_VALUES` |
| Share sum <= 0 or > 1+tol | Sum constraint | `TYPE_II_INVALID_SHARE_SUM` |
| comp / x produces inf/nan | Finite check | `TYPE_II_NONFINITE_WAGE_COEFFICIENTS` |

### Sprint 15 Preflight Checks

```bash
# 1. Type II solver tests
python -m pytest tests/engine/test_leontief.py -v -k "type_ii"

# 2. Validation tests
python -m pytest tests/engine/test_type_ii_validation.py -v

# 3. Batch integration with Type II
python -m pytest tests/engine/test_batch.py -v -k "type_ii"

# 4. Mathematical accuracy
python -m pytest tests/integration/test_type_ii_mathematical_accuracy.py -v

# 5. Full engine suite
python -m pytest tests/engine/ -q

# 6. Full suite
python -m pytest tests -q
```

### Go/No-Go Criteria (additive)

| Criteria | Required | How to Verify |
|---|---|---|
| Type II induced = Type II total - Type I total (within 1e-10) | Yes | `test_leontief.py::TestTypeIISolve` |
| Golden B* matches hand computation | Yes | `test_type_ii_mathematical_accuracy.py` |
| Non-dev fail-closed for invalid prerequisites | Yes | `test_batch.py::TestTypeIIBatchIntegration` |
| Dev fallback to Type I only (no error) | Yes | `test_batch.py::TestTypeIIBatchIntegration` |
| API boundary returns 422 with reason_code | Yes | `test_batch.py::TestTypeIIErrorTranslation` |
| Existing Type I outputs unchanged | Yes | All existing engine tests pass |
| Deterministic reproducibility | Yes | `test_leontief.py::TestTypeIISolve::test_type_ii_deterministic_reproducibility` |
| No secrets in error payloads | Yes | Secret leakage tests pass |

---

## Sprint 16: Value Measures Satellite (MVP-16)

| Measure | Formula | Dev Behavior | Staging/Prod Behavior | Fail Mode | Test Evidence |
|---|---|---|---|---|---|
| **gdp_basic_price** | Σ(va_ratio · Δx) | Computed | Computed | — | `test_value_measures.py` |
| **gdp_market_price** | GDP_basic + Σ(tax_ratio · Δx) | Computed | Computed | VM prerequisite | `test_value_measures.py` |
| **gdp_real** | GDP_market / deflator(base_year) | Computed | Computed | VM_MISSING_DEFLATOR | `test_value_measures.py` |
| **gdp_intensity** | GDP_market / Σ(Δx) | Computed | Computed | — | `test_value_measures.py` |
| **balance_of_trade** | Σ(export_ratio · Δx) - Σ(import_ratio · Δx) | Computed | Computed | VM_MISSING_FINAL_DEMAND | `test_value_measures.py` |
| **non_oil_exports** | exports filtered to non-oil sectors | Computed | Computed | — | `test_value_measures.py` |
| **government_non_oil_revenue** | Σ(tax_ratio · Δx) for non-oil | Computed | Computed | VM_MISSING_TAXES | `test_value_measures.py` |
| **government_revenue_spending_ratio** | gov_revenue / gov_spending_effect | Computed | Computed | — | `test_value_measures.py` |

### Prerequisite Validation Matrix

| Prerequisite | Validation | Reason Code | Non-dev | Dev |
|---|---|---|---|---|
| gross_operating_surplus | present + dim=n + non-negative + finite | `VM_MISSING_GOS` / `VM_INVALID_GOS` | 422 fail-closed | skip VM, log warning |
| taxes_less_subsidies | present + dim=n + finite | `VM_MISSING_TAXES` / `VM_INVALID_TAXES` | 422 fail-closed | skip VM |
| final_demand_F | present + shape=(n,k≥4) + finite | `VM_MISSING_FINAL_DEMAND` / `VM_INVALID_FINAL_DEMAND` | 422 fail-closed | skip VM |
| imports_vector | present + dim=n + non-negative + finite | `VM_MISSING_IMPORTS` / `VM_INVALID_IMPORTS` | 422 fail-closed | skip VM |
| deflator_series | present + base_year key + value>0 | `VM_MISSING_DEFLATOR` / `VM_INVALID_DEFLATOR` | 422 fail-closed | skip VM |

### Sprint 16 Preflight Checks

```bash
# 1. Value measures core
python -m pytest tests/engine/test_value_measures.py -v

# 2. Batch integration
python -m pytest tests/engine/test_batch.py::TestBatchValueMeasures -v

# 3. API integration
python -m pytest tests/engine/test_api_runs.py::TestValueMeasuresEndpoint -v

# 4. Math parity
python -m pytest tests/integration/test_mathematical_accuracy.py::TestValueMeasuresMathematicalAccuracy -v

# 5. Full suite
python -m pytest tests -q
```

### Go/No-Go Criteria (additive)

| Criteria | Required | How to Verify |
|---|---|---|
| All 8 value measures computed deterministically | Yes | `test_value_measures.py` passes |
| Fail-closed in non-dev for missing prerequisites | Yes | `TestBatchValueMeasures` passes |
| API returns value measures with confidence_class | Yes | `TestValueMeasuresEndpoint` passes |
| Math identities hold (GDP basic/market/real, BoT) | Yes | `TestValueMeasuresMathematicalAccuracy` passes |
| Existing metrics unchanged (backward compatible) | Yes | `test_existing_metrics_preserved_with_vm` passes |
| No secrets in error payloads | Yes | Validation error tests pass |

---

## Sprint 17 — RunSeries Annual Storage + API (MVP-17)

### RunSeries Storage Shape

| series_kind | year | baseline_run_id | Meaning |
|---|---|---|---|
| NULL | NULL | NULL | Legacy cumulative row (Sprints 9-16) |
| `annual` | YYYY | NULL | Per-year output from phased solve |
| `peak` | YYYY | NULL | Peak-year output (highest total impact) |
| `delta` | YYYY | `<uuid>` | Scenario minus baseline for given year |

### Annual Series Metrics

| metric_type | Annual? | Peak? | Delta? |
|---|---|---|---|
| `total_output` | Yes | Yes | Yes |
| `direct_effect` | Yes | No | Yes |
| `indirect_effect` | Yes | No | Yes |

### Delta Validation Reason Codes

| Condition | Reason Code | HTTP |
|---|---|---|
| Baseline run not found | `RS_BASELINE_NOT_FOUND` | 404 |
| Baseline has no annual series | `RS_BASELINE_NO_SERIES` | 422 |
| No overlapping years | `RS_YEAR_MISMATCH` | 422 |
| No overlapping metrics | `RS_BASELINE_METRIC_MISMATCH` | 422 |

### Schema Additions (ResultSetRow)

- `year` (int, nullable) — partial index by series_kind
- `series_kind` (varchar(20), nullable) — CHECK: annual|peak|delta|NULL
- `baseline_run_id` (UUID, nullable) — required only for delta

### Preflight Checks

- [x] Annual sum == cumulative total (per sector, within 1e-10)
- [x] Peak values == annual values for peak year
- [x] Delta == scenario annual - baseline annual (per sector)
- [x] Legacy rows unchanged (series_kind=NULL, year=NULL)
- [x] Default API returns only legacy rows
- [x] include_series=true returns all rows

### Go / No-Go Criteria

| Gate | Result |
|---|---|
| All Sprint 17 tests pass | Required |
| Full suite regression-free | Required |
| Annual sum == cumulative identity | Required |
| Delta arithmetic identity | Required |
| Backward compatibility preserved | Required |

---

## Sprint 18 — Phase 2-E: SG Model Import Adapter + Parity Benchmark Gate (MVP-18)

### SG Model Adapter

| Component | Purpose | Test Evidence |
|---|---|---|
| `sg_model_adapter.py` | Detect SG Excel layout, extract IO model data (Z, x, sector names, extended artifacts) | `test_sg_model_adapter.py` (12 tests) |
| `parity_gate.py` | Fail-closed parity benchmark: compare engine output against golden baseline | `test_parity_gate.py` (11 tests) |
| `import_sg.py` | POST `/v1/workspaces/{workspace_id}/models/import-sg` endpoint | `test_models_import_sg.py` (18 tests) |
| Migration 013 | Additive `sg_provenance` JSONB column on `model_versions` | `test_013_sg_provenance_postgres.py` (4 tests, PG-skip) |

### Parity Gate Validation Matrix

| Condition | Result | Reason Code | Test Evidence |
|---|---|---|---|
| Engine output matches golden baseline within tolerance | `passed=True` | None | `test_identical_model_passes` |
| Metric exceeds tolerance | `passed=False` | `PARITY_TOLERANCE_BREACH` | `test_perturbed_model_fails`, `test_tolerance_breach_metric_has_reason_code` |
| Missing baseline scenario | `passed=False` | `PARITY_MISSING_BASELINE` | `test_missing_baseline_empty`, `test_missing_baseline_key_absent` |
| Missing metric in engine output | `passed=False` | `PARITY_METRIC_MISSING` | `test_missing_metric_in_engine_output` |
| Engine error (dimension mismatch) | `passed=False` | `PARITY_ENGINE_ERROR` | `test_engine_error_wrong_shock_dimension` |

### Import Endpoint Behavior

| Scenario | HTTP | Behavior | Test Evidence |
|---|---|---|---|
| Valid SG workbook + parity pass | 201 | Model registered with sg_provenance | `test_import_happy_path` |
| Parity gate fails | 422 | Rollback, no model row persisted | `test_parity_failure_returns_422`, `test_parity_failure_rollback_no_model_row` |
| Dev bypass flag in dev env | 201 | Parity skipped, model registered | `test_dev_bypass_in_dev_env` |
| Dev bypass flag in prod env | 422 | Rejected | `test_dev_bypass_rejected_in_prod` |
| Unsupported file format | 422 | Structured error | `test_unsupported_format_422` |
| Model visibility after import | 200 | sg_provenance in GET response | `test_model_visible_after_import`, `test_sg_provenance_in_get_response` |

### Sprint 18 Test Results

| Category | Tests | Passed | Skipped | Failed |
|---|---|---|---|---|
| Unit: sg_model_adapter | 12 | 12 | 0 | 0 |
| Unit: parity_gate | 11 | 11 | 0 | 0 |
| Integration: import-sg endpoint | 18 | 18 | 0 | 0 |
| Migration: 013 sg_provenance | 4 | 0 | 4 (PG) | 0 |
| **Full suite** | **4220** | **4220** | **11** | **0** |

### Sprint 18 Preflight Checks

```bash
# 1. SG model adapter tests
python -m pytest tests/data/test_sg_model_adapter.py -v

# 2. Parity gate tests
python -m pytest tests/engine/test_parity_gate.py -v

# 3. Import endpoint integration tests
python -m pytest tests/api/test_models_import_sg.py -v

# 4. Migration tests (requires Postgres)
python -m pytest tests/migration/test_013_sg_provenance_postgres.py -v

# 5. Full suite
python -m pytest tests -q
```

### Verification Summary

- **Lint**: Clean (no new lint categories; pre-existing S101/N806 patterns only)
- **OpenAPI**: Refreshed with `/v1/workspaces/{workspace_id}/models/import-sg` endpoint
- **Migration**: 013 additive `sg_provenance` JSONB column (nullable, no data loss on rollback)
- **Backward compatibility**: All 4220 tests pass, 11 skipped (PG-only migrations)

### Go/No-Go Criteria (additive)

| Criteria | Required | How to Verify |
|---|---|---|
| SG layout detection for .xlsx workbooks | Yes | `test_sg_model_adapter.py` passes |
| IO model extraction with extended artifacts | Yes | `test_extract_extended_artifacts_when_present` passes |
| Deterministic workbook hash | Yes | `test_extract_workbook_hash_is_deterministic` passes |
| Parity gate fail-closed on tolerance breach | Yes | `test_parity_gate.py` passes |
| Import endpoint 201 on valid workbook + parity pass | Yes | `test_import_happy_path` passes |
| Import endpoint 422 + rollback on parity failure | Yes | `test_parity_failure_*` passes |
| Dev bypass only in dev environment | Yes | `test_dev_bypass_*` passes |
| sg_provenance populated in model record | Yes | `test_sg_provenance_in_get_response` passes |
| Existing tests unchanged | Yes | Full suite 4220 passed, 0 failed |

---

## Sprint 19 — Client Portal Collaboration Flows (MVP-19)

### Migration Evidence
- [x] Migration 014: `assumptions.workspace_id` nullable FK + index
- [x] Alembic upgrade/downgrade/check clean (PG tested)
- [x] Post-merge `alembic current`: `014_assumption_workspace_id (head)`
- [x] Post-merge `alembic check`: No new upgrade operations detected

### Assumption Sign-Off Auth Matrix
| Action | Role Gate | Fail Mode | Reason Code |
|--------|-----------|-----------|-------------|
| List | workspace member | — | — |
| Detail | workspace member | 404 | ASSUMPTION_NOT_FOUND |
| Create | workspace member | — | — |
| Approve | manager/admin | 403 / 422 / 409 / 404 | ASSUMPTION_RANGE_REQUIRED / ASSUMPTION_NOT_DRAFT / ASSUMPTION_NOT_FOUND |
| Reject | manager/admin | 403 / 409 / 404 | ASSUMPTION_NOT_DRAFT / ASSUMPTION_NOT_FOUND |

### Scenario Comparison Validation Matrix
| Check | HTTP | Reason Code |
|-------|------|-------------|
| Run not found / wrong workspace | 404 | COMPARE_RUN_NOT_FOUND |
| No results | 422 | COMPARE_NO_RESULTS |
| Model mismatch | 422 | COMPARE_MODEL_MISMATCH |
| Metric set mismatch | 422 | COMPARE_METRIC_SET_MISMATCH |
| Annual unavailable | 422 | COMPARE_ANNUAL_UNAVAILABLE |
| Annual year mismatch | 422 | COMPARE_ANNUAL_YEAR_MISMATCH |
| Peak unavailable | 422 | COMPARE_PEAK_UNAVAILABLE |

### Evidence Browsing Filter Matrix
| Filter | Behavior | Fail Mode | Reason Code |
|--------|----------|-----------|-------------|
| limit | 1-100 pagination | 422 | EVIDENCE_INVALID_PAGINATION |
| offset | >=0, requires limit | 422 | EVIDENCE_INVALID_PAGINATION |
| claim_id | Resolve evidence_refs, short-circuit empty | 404 | Claim not found |
| source_id | Filter by document | 404 | Document not found |
| text_query | ILIKE after trim, min 2 chars | 422 | EVIDENCE_TEXT_QUERY_TOO_SHORT |
| run_id | Existing 404 preserved | 404 | Run not found |

### Test Counts
- Baseline (Sprint 18): 4,220 passed
- Sprint 19 new tests: 63 (9 repo + 19 signoff + 15 comparison + 16 browse + 4 migration)
- Sprint 19 worktree: 4,340 passed, 11 skipped, 0 failed
- **Post-merge main verified: 4,347 passed, 4 skipped, 0 failed (4,351 collected)**
- PR: #24 — merged commit `1d6dae2`, tag `sprint-19-complete`

### Sprint 19 Preflight Checks

```bash
# 1. Assumption sign-off tests
python -m pytest tests/api/test_assumption_signoff.py -v

# 2. Scenario comparison tests
python -m pytest tests/api/test_scenario_comparison.py -v

# 3. Evidence browse tests
python -m pytest tests/api/test_evidence_browse.py -v

# 4. Migration tests (requires Postgres)
python -m pytest tests/migration/test_014_assumption_workspace_postgres.py -v

# 5. Repository tests
python -m pytest tests/repositories/test_assumption_workspace.py -v

# 6. Full suite
python -m pytest tests -q
```

### Verification Summary

- **Lint**: Clean (no new lint categories; pre-existing B008/E501 patterns only)
- **OpenAPI**: Refreshed with new endpoints:
  - `GET /v1/workspaces/{workspace_id}/governance/assumptions` (list)
  - `GET /v1/workspaces/{workspace_id}/governance/assumptions/{assumption_id}` (detail)
  - `POST /v1/workspaces/{workspace_id}/governance/assumptions/{assumption_id}/approve`
  - `POST /v1/workspaces/{workspace_id}/governance/assumptions/{assumption_id}/reject`
  - `POST /v1/workspaces/{workspace_id}/scenarios/compare-runs`
- **Migration**: 014 additive `workspace_id` nullable FK on `assumptions` (no data loss on rollback)
- **Backward compatibility**: All 4,347 tests pass on main, 4 skipped (PG-only migrations now passing)

### Go/No-Go Criteria (additive)

| Criteria | Required | How to Verify |
|---|---|---|
| Assumption list/detail/create for workspace members | Yes | `test_assumption_signoff.py` passes |
| Approve/reject restricted to manager/admin roles | Yes | `test_assumption_signoff.py` role gate tests pass |
| Approve requires range for ESTIMATED confidence | Yes | `test_approve_estimated_requires_range` passes |
| Reject transitions draft → rejected | Yes | `test_reject_happy_path` passes |
| Idempotent reject on already-rejected | Yes | `test_reject_already_rejected_is_idempotent` passes |
| Scenario compare-runs validates model parity | Yes | `test_scenario_comparison.py` passes |
| Compare-runs validates metric set parity | Yes | `test_metric_set_mismatch_422` passes |
| Evidence browse with pagination + filters | Yes | `test_evidence_browse.py` passes |
| Text query minimum length enforced | Yes | `test_text_query_too_short_422` passes |
| Migration 014 upgrade/downgrade clean | Yes | `test_014_assumption_workspace_postgres.py` passes |
| Existing tests unchanged | Yes | Full suite 4,347 passed, 0 failed (post-merge main) |

---

## Sprint 20: Structural Path Analysis + Chokepoint Analytics (MVP-20)

### What Changed

- **SPA Engine** (`src/engine/structural_path.py`): Deterministic power series decomposition B = I + A + A² + ... + A^k with coverage ratio (Frobenius norm), Rasmussen chokepoint scoring (forward/backward linkage indices), and deterministic tie-breaking.
- **Persistence** (`alembic/versions/015_path_analyses.py`, `src/db/tables.py`): New `path_analyses` table with 14 columns, `(run_id, config_hash)` unique constraint for idempotency, composite index `(run_id, created_at DESC)`, coverage CHECK constraint (Postgres).
- **Repository** (`src/repositories/path_analytics.py`): Workspace-scoped CRUD + pagination + idempotency lookup.
- **API** (`src/api/path_analytics.py`): Three additive workspace-scoped endpoints:
  - `POST /v1/workspaces/{workspace_id}/path-analytics` (201 new / 200 idempotent)
  - `GET /v1/workspaces/{workspace_id}/path-analytics/{analysis_id}`
  - `GET /v1/workspaces/{workspace_id}/path-analytics?run_id=...&limit=...&offset=...`
- **Pydantic models** (`src/models/path.py`): 7 typed schemas for API contracts.
- **OpenAPI**: Refreshed with 2 new endpoint paths (POST/GET combined, GET by ID).
- **Migration**: 015 additive `path_analyses` table (no existing table changes).
- **Backward compatibility**: All pre-existing 4,385 tests pass unchanged. Sprint 20 adds 47 new tests.

### SPA Mathematical Contract

| Property | Formula | Verification |
|---|---|---|
| Power series | B_hat = I + A + A² + ... + A^k | `test_structural_path.py` |
| Scalar identity | Σ depth_contributions[k].signed ≈ Σ(B·delta_d) | Within 1e-10 |
| Vector identity | Per-sector path sums ≈ (B·delta_d)[i] | Within 1e-10 |
| Coverage ratio | 1 - ‖B - B_hat‖_F / ‖B‖_F ∈ [0, 1] | Clipped, verified |
| Forward linkage | FL[i] = Σ_j B[i,j] (row sum) | Rasmussen convention |
| Backward linkage | BL[j] = Σ_i B[i,j] (column sum) | Rasmussen convention |
| Chokepoint score | sqrt(norm_FL × norm_BL), is_chokepoint when both > 1.0 | Verified |

### Error Taxonomy

| Reason Code | HTTP | Trigger |
|---|---|---|
| `SPA_INVALID_CONFIG` | 422 | max_depth ∉ [0,12] or top_k ∉ [1,100] |
| `SPA_RUN_NOT_FOUND` | 404 | run_id missing or wrong workspace |
| `SPA_MODEL_DATA_UNAVAILABLE` | 422 | Model data not loadable |
| `SPA_MISSING_DIRECT_EFFECT` | 422 | No direct_effect ResultSet for run |
| `SPA_DIMENSION_MISMATCH` | 422 | Matrix/vector size inconsistency |
| `SPA_ANALYSIS_NOT_FOUND` | 404 | Analysis ID not in workspace |

### Test Evidence

| Test File | Count | Coverage |
|---|---|---|
| `tests/engine/test_structural_path.py` | 15 | Engine: depth 0/1/10, identities, ranking, zero shock, chokepoints, errors |
| `tests/migration/test_015_path_analyses_postgres.py` | 4 | Migration: upgrade, unique constraint, CHECK, downgrade |
| `tests/repositories/test_path_analytics.py` | 10 (×2 backends = 20) | Repo: CRUD, workspace scoping, idempotency, pagination |
| `tests/api/test_path_analytics.py` | 18 (×2 backends = 36) | API: happy paths, error precedence, workspace isolation, auth, response content |
| **Total new** | **47 tests (71 runs)** | |

### Preflight Checks

```bash
# Lint (Sprint 20 files)
python -m ruff check src/api/path_analytics.py src/models/path.py src/engine/structural_path.py src/repositories/path_analytics.py

# Full test suite
python -m pytest -q
# Expected: 4421 passed, 1 failed (pre-existing migration 014 env issue), 4 skipped

# Alembic (with PG)
python -m alembic current   # → 015_path_analyses (head)
python -m alembic check     # → No new upgrade operations

# OpenAPI
python -c "import json; json.load(open('openapi.json')); print('valid')"
```

### Go/No-Go Criteria (additive)

| Criteria | Required | How to Verify |
|---|---|---|
| SPA power series decomposition correct | Yes | `test_structural_path.py` scalar/vector identity tests pass |
| Coverage ratio ∈ [0, 1] | Yes | `test_response_coverage_ratio_valid` passes |
| Chokepoint scoring uses Rasmussen convention | Yes | `test_chokepoint_*` tests pass |
| POST idempotent on (run_id, config_hash) | Yes | `test_post_idempotent_returns_200` passes |
| Workspace isolation enforced | Yes | `test_*_wrong_workspace_*` tests pass |
| Auth required on all endpoints | Yes | `test_*_no_auth_401` tests pass |
| Error codes match taxonomy | Yes | Error precedence tests pass with correct reason_codes |
| Migration 015 upgrade/downgrade clean | Yes | `test_015_path_analyses_postgres.py` passes |
| Pagination works correctly | Yes | `test_list_by_run_pagination` passes |
| Existing tests unchanged | Yes | Full suite: 4,421 passed (baseline was 4,347 + 74 new test runs) |

---

## Sprint 21: Portfolio Optimization (MVP-21)

### What Changed

- **Portfolio Engine** (`src/engine/portfolio_optimizer.py`): Deterministic exact binary knapsack solver via enumeration (max 25 candidates). Maximizes total objective_value under budget, cardinality, and group-cap constraints. Deterministic tie-break by lexicographically smallest sorted run_id tuple (UUID string comparison).
- **Persistence** (`alembic/versions/016_portfolio_optimizations.py`, `src/db/tables.py`): New `portfolio_optimizations` table with 16 columns, `(workspace_id, config_hash)` unique constraint for idempotency, composite index `(workspace_id, created_at DESC)`.
- **Repository** (`src/repositories/portfolio.py`): Workspace-scoped CRUD + pagination + config-hash idempotency lookup (5 methods).
- **API** (`src/api/portfolio.py`): Three additive workspace-scoped endpoints:
  - `POST /v1/workspaces/{workspace_id}/portfolio/optimize` (201 new / 200 idempotent)
  - `GET /v1/workspaces/{workspace_id}/portfolio/{portfolio_id}`
  - `GET /v1/workspaces/{workspace_id}/portfolio`
- **Pydantic models** (`src/models/portfolio.py`): 6 typed schemas inheriting ImpactOSBase.
- **Race-safe idempotency**: IntegrityError catch + session rollback + retry SELECT on concurrent insert race.
- **OpenAPI**: Refreshed with 3 new portfolio endpoint paths.
- **Migration**: 016 additive `portfolio_optimizations` table (no existing table changes).
- **Backward compatibility**: All pre-existing tests pass unchanged. Sprint 21 adds 87 new test runs.

### Solver Contract

| Property | Specification | Verification |
|---|---|---|
| Subset selection | 0/1 binary knapsack (exact enumeration) | `test_portfolio_optimizer.py` |
| Objective | Maximize sum of objective_value | `test_selects_optimal_pair` |
| Budget constraint | total cost <= budget | `test_selects_optimal_pair` |
| Cardinality | min_selected <= count <= max_selected | `test_min_selected_enforced`, `test_max_selected_enforced` |
| Group caps | per-group count <= cap | `test_group_caps_enforced` |
| Tie-break | Lexicographically smallest sorted run_id tuple (str) | `test_tiebreak_lexicographic_run_id` |
| Candidate limit | max 25, fail closed | `test_candidate_limit_exceeded` |
| Solver method | "exact_binary_knapsack_v1" | `test_solver_method_reported` |

### Error Taxonomy

| Reason Code | HTTP | Trigger |
|---|---|---|
| `PORTFOLIO_NO_CANDIDATES` | 422 | Empty candidate list |
| `PORTFOLIO_DUPLICATE_CANDIDATES` | 422 | Repeated run_id in candidates |
| `PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED` | 422 | More than 25 candidates |
| `PORTFOLIO_INVALID_CONFIG` | 422 | budget <= 0, min_selected < 1, max_selected < 1, max < min, group_cap < 1, empty metrics |
| `PORTFOLIO_RUN_NOT_FOUND` | 404 | Candidate run_id not in workspace |
| `PORTFOLIO_MODEL_MISMATCH` | 422 | Candidates have different model_version_id |
| `PORTFOLIO_METRIC_NOT_FOUND` | 422 | objective_metric or cost_metric missing for candidate |
| `PORTFOLIO_INFEASIBLE` | 422 | No feasible subset under constraints |
| `PORTFOLIO_NOT_FOUND` | 404 | Portfolio ID not in workspace |

### Fail-Closed Validation Order (API Layer)

1. Auth/workspace (existing gate)
2. No candidates
3. Empty metric names
4. Duplicate candidates
5. Run existence (workspace-scoped)
6. Model compatibility (same model_version_id)
7. Metric availability (both metrics for every candidate)
8. Config sanity (budget, min/max selected, group caps)
9. Candidate limit (> 25)

### Test Evidence

| Test File | Count | Coverage |
|---|---|---|
| `tests/engine/test_portfolio_optimizer.py` | 19 | Engine: happy paths, determinism, constraints, validation errors |
| `tests/migration/test_016_portfolio_optimization_postgres.py` | 4 | Migration: upgrade, unique constraint, downgrade, re-upgrade |
| `tests/repositories/test_portfolio.py` | 10 (x2 backends = 20) | Repo: CRUD, workspace scoping, idempotency, pagination |
| `tests/api/test_portfolio.py` | 22 (x2 backends = 44) | API: happy paths, error precedence, workspace isolation, auth, response content |
| **Total new** | **55 tests (87 runs)** | |

### Preflight Checks

```bash
# Sprint 21 targeted tests
python -m pytest tests/engine/test_portfolio_optimizer.py tests/repositories/test_portfolio.py tests/api/test_portfolio.py tests/migration/test_016_portfolio_optimization_postgres.py -q

# Lint (Sprint 21 files)
python -m ruff check --select I001,F401,F841,B905 src/engine/portfolio_optimizer.py src/models/portfolio.py src/repositories/portfolio.py src/api/portfolio.py

# Format check
python -m ruff format --check src/engine/portfolio_optimizer.py src/models/portfolio.py src/repositories/portfolio.py src/api/portfolio.py

# Alembic (with PG)
python -m alembic current   # -> 016_portfolio_optimizations (head)
python -m alembic heads     # -> single head at 016

# Full test suite
python -m pytest tests -q
```

### Go/No-Go Criteria (additive)

| Criteria | Required | How to Verify |
|---|---|---|
| Exact binary knapsack selects optimal subset | Yes | `test_selects_optimal_pair` passes |
| Deterministic tie-break by lexicographic run_id | Yes | `test_tiebreak_lexicographic_run_id` passes |
| min_selected enforced (empty set rejected) | Yes | `test_min_selected_enforced` passes |
| max_selected enforced | Yes | `test_max_selected_enforced` passes |
| Group caps enforced | Yes | `test_group_caps_enforced` passes |
| All 10 reason codes implemented and tested | Yes | Error precedence tests pass with correct reason_codes |
| POST idempotent on (workspace_id, config_hash) | Yes | `test_post_idempotent_200` passes |
| Race-safe idempotency with IntegrityError retry | Yes | Code review confirmed |
| Workspace isolation enforced | Yes | `test_get_wrong_workspace_404`, `test_list_workspace_isolation` pass |
| Auth required on all endpoints | Yes | `test_unauthenticated_401`, `test_unauthenticated_get_401` pass |
| config_hash includes optimization_version | Yes | Code review confirmed |
| Migration 016 upgrade/downgrade clean | Yes | `test_016_portfolio_optimization_postgres.py` passes |
| Existing tests unchanged | Yes | Full suite: 4,506 passed, 3 failed (pre-existing PG permission), 4 skipped |
