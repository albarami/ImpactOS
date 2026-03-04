# Sprint 19: Client Portal Collaboration Flows — Design Document

> **Status:** Approved
> **Sprint:** MVP-19 (Phase 3)
> **Baseline:** 4,231 collected / 4,220 passed / 11 skipped | Alembic head: 013
> **Branch:** `phase3-sprint19-client-portal-collaboration`

---

## 1. Scope

Three portal-ready collaboration flows (API/runtime layer only):

1. **S19-1:** Assumption sign-off workflow — list, detail, approve, reject
2. **S19-2:** Scenario comparison dashboard API — deterministic metric deltas
3. **S19-3:** Evidence browsing — paginated, filtered, workspace-scoped
4. **S19-4:** Docs, OpenAPI refresh, release checklist

No MVP-20/21/22/23 work. No frontend. No AI/LLM behavior in any path.

---

## 2. Hard Constraints (inherited)

1. FastAPI + repository + DI + SQLAlchemy architecture preserved.
2. Deterministic APIs only — no LLM calls in sign-off / comparison / evidence paths.
3. Additive only — no breaking changes to existing public API contracts.
4. Sprint 11+ auth semantics unchanged (401/403/404).
5. Strict workspace scoping — no cross-workspace leakage.
6. Fail-closed with explicit reason codes on invalid requests.
7. Existing run/export/governance paths backward-compatible.

---

## 3. Architecture Overview

```
Client Portal
    │
    ├─► GET  /governance/assumptions         ─► AssumptionRepository.list_by_workspace()
    ├─► GET  /governance/assumptions/{id}    ─► AssumptionRepository.get_for_workspace()
    ├─► POST /governance/assumptions/{id}/approve ─► repo.approve() [manager|admin]
    ├─► POST /governance/assumptions/{id}/reject  ─► repo.reject()  [manager|admin]
    │
    ├─► POST /scenarios/compare-runs         ─► ResultSetRepository.get_by_run()
    │                                           pure delta math on persisted values
    │
    └─► GET  /governance/evidence            ─► EvidenceSnippetRepository.browse()
         (extended with pagination + filters)    dynamic query builder
```

All paths are deterministic. AI never touches these flows.

---

## 4. S19-1: Assumption Sign-Off Collaboration Flow

### 4.1 Migration 014: `assumptions.workspace_id`

```sql
-- upgrade
ALTER TABLE assumptions ADD COLUMN workspace_id UUID NULL
  REFERENCES workspaces(workspace_id);
CREATE INDEX ix_assumptions_workspace_id ON assumptions(workspace_id);

-- downgrade
DROP INDEX ix_assumptions_workspace_id;
ALTER TABLE assumptions DROP COLUMN workspace_id;
```

- Nullable FK: backward-compatible, no backfill required.
- Legacy rows with `workspace_id IS NULL` are hidden from all workspace-scoped APIs (treated as 404 / not listed).
- API always sets `workspace_id` from path on create.

### 4.2 New Endpoints

#### `GET /{ws}/governance/assumptions`

- **Auth:** `require_workspace_member`
- **Query params:**
  - `status: str | None = None` — filter by DRAFT / APPROVED / REJECTED
  - `limit: int = 50` — page size, max 100 (422 `ASSUMPTION_INVALID_PAGINATION` if > 100 or < 1)
  - `offset: int = 0` — pagination offset (422 if < 0)
- **Ordering:** `created_at DESC, assumption_id DESC` (deterministic)
- **Response:**

```python
class AssumptionListItem(BaseModel):
    assumption_id: str
    type: str
    value: float
    units: str
    justification: str
    status: str
    range_min: float | None = None
    range_max: float | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    created_at: str
    updated_at: str

class AssumptionListResponse(BaseModel):
    items: list[AssumptionListItem]
    total: int
    limit: int
    offset: int
    has_more: bool
```

#### `GET /{ws}/governance/assumptions/{assumption_id}`

- **Auth:** `require_workspace_member`
- **Response:** `AssumptionDetailResponse` (same fields as list item + `evidence_refs: list[str]`)
- **404:** if not found or `workspace_id != ws` or `workspace_id IS NULL`

#### `POST /{ws}/governance/assumptions/{assumption_id}/reject`

- **Auth:** `require_role("manager", "admin")`
- **Request body:** `RejectAssumptionRequest { actor: str, reason: str | None = None }`
- **Response:** `RejectAssumptionResponse { assumption_id: str, status: str }`
- **409 `ASSUMPTION_NOT_DRAFT`:** if current status is not DRAFT
- **404 `ASSUMPTION_NOT_FOUND`:** if not found or wrong workspace

### 4.3 Modified Endpoints

#### `POST /{ws}/governance/assumptions` (create)

- **Change:** Sets `workspace_id` from path parameter on the repo create call.
- **No other behavior change.**

#### `POST /{ws}/governance/assumptions/{id}/approve`

- **Change 1:** Add `require_role("manager", "admin")` auth gate.
- **Change 2:** Lookup via `get_for_workspace(assumption_id, workspace_id)` instead of bare `get()`.
- **Change 3:** Range validation returns 422 (not 400) with `ASSUMPTION_RANGE_REQUIRED`.
- **Change 4:** Non-DRAFT returns 409 with `ASSUMPTION_NOT_DRAFT`.

### 4.4 Status Transitions

```
DRAFT ──► APPROVED  (manager|admin, requires range_min + range_max)
DRAFT ──► REJECTED  (manager|admin)
```

Terminal states: APPROVED, REJECTED — no further transitions allowed.

### 4.5 Reason Codes

| Code | HTTP | When |
|---|---|---|
| `ASSUMPTION_NOT_FOUND` | 404 | ID not found, wrong workspace, or legacy NULL workspace |
| `ASSUMPTION_NOT_DRAFT` | 409 | Approve/reject on non-DRAFT assumption |
| `ASSUMPTION_RANGE_REQUIRED` | 422 | Approve without range_min and range_max |
| `ASSUMPTION_INVALID_PAGINATION` | 422 | limit < 1, limit > 100, or offset < 0 |

### 4.6 Repository Changes

- **New:** `AssumptionRepository.get_for_workspace(assumption_id, workspace_id)` — returns None if not found or workspace mismatch or NULL workspace.
- **New:** `AssumptionRepository.list_by_workspace(workspace_id, *, status=None, limit=50, offset=0)` — returns `tuple[list[AssumptionRow], int]` (page + total count). Orders by `created_at DESC, assumption_id DESC`. Filters `workspace_id = :ws` (excludes NULL).
- **Modified:** `approve()` and `reject()` — caller uses `get_for_workspace()` before transition (workspace-scoped).

### 4.7 Auth Matrix (tested)

| Action | Role | Expected |
|---|---|---|
| List assumptions | member | 200 |
| List assumptions | unauthenticated | 401 |
| Get detail | member (own ws) | 200 |
| Get detail | member (other ws) | 404 |
| Approve | manager | 200 |
| Approve | analyst (non-manager) | 403 |
| Reject | admin | 200 |
| Reject | analyst | 403 |
| Approve non-DRAFT | manager | 409 |
| Approve missing range | manager | 422 |

---

## 5. S19-2: Scenario Comparison Dashboard API

### 5.1 Endpoint

```
POST /{ws}/scenarios/compare-runs
```

**Route safety:** Declared BEFORE `/{ws}/scenarios/{scenario_id}` to prevent path shadowing.

**Auth:** `require_workspace_member`

### 5.2 Request

```python
class CompareRunsRequest(BaseModel):
    run_id_a: UUID          # baseline run
    run_id_b: UUID          # scenario run
    include_annual: bool = False
    include_peak: bool = False
```

### 5.3 Response

```python
class MetricComparison(BaseModel):
    metric_type: str
    value_a: float
    value_b: float
    delta: float             # value_b - value_a
    pct_change: float | None # delta / value_a * 100; None if value_a == 0

class AnnualComparison(BaseModel):
    year: int
    metrics: list[MetricComparison]

class PeakComparison(BaseModel):
    peak_year_a: int | None
    peak_year_b: int | None
    metrics: list[MetricComparison]

class CompareRunsResponse(BaseModel):
    run_id_a: str
    run_id_b: str
    model_version_a: str
    model_version_b: str
    sector_count_a: int
    sector_count_b: int
    metrics: list[MetricComparison]
    annual: list[AnnualComparison] | None = None
    peak: PeakComparison | None = None
```

### 5.4 Implementation Flow

1. Load `RunSnapshotRow` for both run_ids — verify both have `workspace_id == ws` (404 `COMPARE_RUN_NOT_FOUND` if not).
2. Load cumulative `ResultSetRow` for both runs (`series_kind IS NULL`).
3. Validate: both runs have results (422 `COMPARE_NO_RESULTS` if empty).
4. Validate: same `model_version_id` (422 `COMPARE_MODEL_MISMATCH` if different).
5. Validate: metric type sets are identical (422 `COMPARE_METRIC_SET_MISMATCH` if they differ).
6. For each metric_type: extract aggregate value via `_extract_aggregate(values)` helper, compute delta and pct_change.
7. If `include_annual`: load `series_kind="annual"` rows for both runs, validate year sets match (422 `COMPARE_ANNUAL_YEAR_MISMATCH` if different), validate metric sets per year match (422 `COMPARE_METRIC_SET_MISMATCH`), compute per-year deltas.
8. If `include_peak`: load `series_kind="peak"` rows for both runs, validate at least one peak row exists per run (422 `COMPARE_PEAK_UNAVAILABLE`), compute deltas.

### 5.5 Value Extraction Helper

```python
def _extract_aggregate(values: dict[str, float]) -> float:
    """Deterministic aggregate: use _total if present, else sum numeric values."""
    if "_total" in values:
        return float(values["_total"])
    return sum(float(v) for v in values.values() if isinstance(v, (int, float)))
```

Same helper used for cumulative, annual, and peak extraction.

### 5.6 Reason Codes

| Code | HTTP | When |
|---|---|---|
| `COMPARE_RUN_NOT_FOUND` | 404 | run_id not found or wrong workspace |
| `COMPARE_NO_RESULTS` | 422 | run has no ResultSet rows |
| `COMPARE_MODEL_MISMATCH` | 422 | runs use different model_version_id |
| `COMPARE_METRIC_SET_MISMATCH` | 422 | metric type sets differ between runs |
| `COMPARE_ANNUAL_UNAVAILABLE` | 422 | include_annual=True but no annual rows |
| `COMPARE_ANNUAL_YEAR_MISMATCH` | 422 | annual year sets differ between runs |
| `COMPARE_PEAK_UNAVAILABLE` | 422 | include_peak=True but no peak rows |

### 5.7 Key Decisions

- **Deterministic:** Pure math on persisted ResultSet values. No engine re-computation.
- **Aggregate-level:** MetricComparison returns scalar per metric. Sector breakdowns are a future extension.
- **Model mismatch is fail-closed:** Different model versions → different sector structures → 422.
- **No behavior bleed from variance-bridge:** `POST /exports/variance-bridge` unchanged and separate.

---

## 6. S19-3: Evidence Browsing API for Portal

### 6.1 Extended Endpoint

```
GET /{ws}/governance/evidence
```

**Auth:** `require_workspace_member` (unchanged)

### 6.2 New Query Parameters (additive)

| Param | Type | Default | Behavior |
|---|---|---|---|
| `run_id` | `UUID \| None` | None | **Existing** — filter by run's source docs |
| `claim_id` | `UUID \| None` | None | **New** — filter to evidence linked from claim's `evidence_refs` |
| `source_id` | `UUID \| None` | None | **New** — filter by source document |
| `text_query` | `str \| None` | None | **New** — case-insensitive substring match on `extracted_text` (trimmed, min 2 chars) |
| `limit` | `int \| None` | None | **New** — page size (max 100). None = return all (backward-compatible) |
| `offset` | `int \| None` | None | **New** — pagination offset. Only valid when `limit` is set |

### 6.3 Response (additive fields)

```python
class EvidenceListResponse(BaseModel):
    items: list[EvidenceListItem]
    total: int                       # existing — always: count of items in this response
    total_matching: int | None = None  # new — total matching across all pages (only in paginated mode)
    limit: int | None = None           # new — echoed back (only in paginated mode)
    offset: int | None = None          # new — echoed back (only in paginated mode)
    has_more: bool | None = None       # new — total_matching > offset + limit (only in paginated mode)
```

**Backward compatibility:**
- When `limit` is None (default): response is identical to current behavior. `total` = len(items), new fields are None.
- When `limit` is set: `total` = len(items on this page), `total_matching` = full count, pagination fields populated.

### 6.4 Filter Interaction Rules

- Filters are AND-combined: multiple filters narrow results.
- `claim_id` filter short-circuits: if claim exists but `evidence_refs` is empty, return empty page with `total_matching=0` immediately (no DB scan).
- `source_id` filter: `WHERE source_id = :source_id` with workspace document join.
- `text_query`: trimmed, then validated min 2 chars, then `WHERE extracted_text ILIKE '%:query%'`.
- `run_id` filter: existing behavior (workspace-scoped via RunSnapshot → Document → EvidenceSnippet chain).
- All filters go through workspace scoping (evidence → document → workspace_id join).

### 6.5 `run_id` 404 Behavior (backward compatibility)

**Current behavior:** `run_id` not found → 404 (existing code raises HTTPException). **Preserved as-is.** No change to existing `run_id` semantics.

For `claim_id` and `source_id` (new filters): also 404 if not found or wrong workspace, since these are new filters with no backward-compatibility obligation.

### 6.6 Ordering

`created_at ASC, snippet_id ASC` (consistent with existing `list_by_workspace` ordering).

### 6.7 Reason Codes

| Code | HTTP | When |
|---|---|---|
| `EVIDENCE_RUN_NOT_FOUND` | 404 | `run_id` not found or wrong workspace (existing behavior preserved) |
| `EVIDENCE_CLAIM_NOT_FOUND` | 404 | `claim_id` not found or wrong workspace |
| `EVIDENCE_SOURCE_NOT_FOUND` | 404 | `source_id` not found or wrong workspace |
| `EVIDENCE_INVALID_PAGINATION` | 422 | `limit < 1`, `limit > 100`, `offset < 0`, or `offset` without `limit` |
| `EVIDENCE_TEXT_QUERY_TOO_SHORT` | 422 | `text_query` (after trim) is fewer than 2 characters |

### 6.8 Repository Changes

- **New:** `EvidenceSnippetRepository.browse(workspace_id, *, run_id=None, snippet_ids=None, source_id=None, text_query=None, limit=None, offset=None)` → `tuple[list[EvidenceSnippetRow], int | None]`
  - Builds query dynamically from non-None filters.
  - Always applies workspace scoping via document join.
  - `snippet_ids` param: pre-resolved from claim's `evidence_refs` (claim lookup happens in endpoint layer).
  - Returns `(rows, total_count)` when paginated; `(rows, None)` when unpaginated.
  - Count query: separate `SELECT COUNT(*)` with same filters for `total_matching`.

### 6.9 Claim-Evidence Link Visibility

No separate endpoint. Portal flow:
1. `GET /claims/{id}` → read `evidence_refs` list
2. `GET /evidence?claim_id={id}` → get full evidence objects for those refs

Reuses existing contracts without new join endpoints.

---

## 7. S19-4: Docs + Evidence + Contract Sync

### 7.1 OpenAPI Refresh

Regenerate `openapi.json`. Verify:
- Assumption list/detail/reject endpoints present
- `POST /scenarios/compare-runs` present
- Extended evidence query params present
- All new response schemas present
- No removed fields from existing responses

### 7.2 Release Readiness Checklist

Append Sprint 19 section to `docs/evidence/release-readiness-checklist.md`:
- Assumption sign-off auth matrix
- Scenario comparison validation matrix
- Evidence browsing filter matrix
- Sprint 19 test counts
- Migration 014 evidence (upgrade/downgrade/check)

### 7.3 Contract Compatibility Tests

- Verify existing responses still contain all previously-documented fields
- Verify new additive fields are present
- Verify OpenAPI spec is valid JSON with expected paths

---

## 8. Migration Summary

| Migration | Table | Change | Nullable | FK | Index |
|---|---|---|---|---|---|
| 014 | `assumptions` | Add `workspace_id UUID` | Yes | `workspaces(workspace_id)` | `ix_assumptions_workspace_id` |

Down revision: `013_sg_provenance`.

---

## 9. Pre-Implementation Lock Checklist

1. ✅ Route safety: use `/scenarios/compare-runs` to prevent `{scenario_id}` shadowing.
2. ✅ Backward compatibility: evidence pagination fields additive/optional, legacy response shape preserved.
3. ✅ Migration proof: 014 upgrade/downgrade/upgrade + `alembic check` included in evidence.
4. ✅ Assumption `workspace_id`: nullable FK, API enforces, legacy NULL hidden.
5. ✅ Sign-off auth: approve/reject require `manager|admin`.
6. ✅ Scenario comparison: fail-closed `COMPARE_MODEL_MISMATCH`, metric set validation, year alignment validation.
7. ✅ Evidence pagination: `limit=None` default (backward-compatible), `total` semantics preserved, 422 for invalid pagination.
8. ✅ Evidence `claim_id` short-circuit: empty `evidence_refs` → empty page, no DB scan.
9. ✅ Evidence `text_query`: trimmed before validation, min 2 chars after trim.
10. ✅ Evidence `run_id` 404: existing behavior preserved exactly.
