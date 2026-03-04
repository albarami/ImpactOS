# Sprint 20 Design: Structural Path Analysis + Chokepoint Analytics (MVP-20)

**Date**: 2026-03-04
**Branch**: `phase3-sprint20-structural-path-analytics`
**Baseline**: `sprint-19-complete` (a58909b, 4,347 tests)

---

## 1. Mission

Add deterministic Structural Path Analysis (SPA) and chokepoint analytics as
on-demand, workspace-scoped, run-linked analytics. Fully additive — no changes
to existing run/depth/governance/export endpoints.

## 2. Locked Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | On-demand POST trigger (not auto at run creation) | Keeps run creation fast, avoids forced compute/storage, fully additive |
| D2 | Power series decomposition A^k for k=0..max_depth | Deterministic, fast O(n³·k), straightforward identity checks |
| D3 | Standard Rasmussen linkage indices for chokepoints | Auditable, standard IO economics, lowest-risk for MVP |
| D4 | Persist by (run_id, config_hash) for idempotency | Same run + same config = same deterministic result |
| D5 | Extract delta_d from `direct_effect` ResultSet | direct_effect is the stored proxy for the original final-demand shock Δd |
| D6 | Defer named-path tracing + HHI concentration to Sprint 21+ | YAGNI for MVP |

## 3. Section 1: SPA Decomposition Engine

**New file**: `src/engine/structural_path.py`

### 3.1 Mathematical Foundation

Power series decomposition of the Leontief inverse:

```
B = I + A + A² + A³ + ... = Σ(A^k, k=0..∞)
```

For a configurable max_depth K:

```
B_hat = Σ(A^k, k=0..K)
```

Per-sector-pair contribution at depth k:

```
coefficient[k][i][j] = (A^k)[i,j]
contribution[k][i][j] = (A^k)[i,j] × delta_d[j]
```

Where:
- k=0: A^0 = I — direct effects (identity)
- k=1: A — first-round indirect effects
- k=2: A² — second-round indirect effects
- etc.

### 3.2 Coverage Ratio

Frobenius-norm based coverage metric:

```
coverage_ratio = 1 - ||B - B_hat||_F / ||B||_F
```

Clipped to [0, 1]. Approaches 1.0 as max_depth increases. Independent of shock
vector — purely a function of A and max_depth.

### 3.3 Top-K Path Ranking

Rank all (i, j, k) tuples by `|contribution[k][i][j]|` descending.

Deterministic tie-break: `(k ASC, i ASC, j ASC)` — shorter paths first, then
lower sector indices.

### 3.4 Chokepoint Scoring (Rasmussen Convention)

Computed from B matrix, independent of shock:

```
backward_linkage[j] = Σ_i B[i,j]     # column sum — how much j pulls from suppliers
forward_linkage[i]  = Σ_j B[i,j]     # row sum — how much i pushes to buyers
```

Normalized by cross-sector mean:

```
norm_backward[j] = backward_linkage[j] / mean(backward_linkage)
norm_forward[i]  = forward_linkage[i]  / mean(forward_linkage)
```

Composite score:

```
chokepoint_score[s] = sqrt(norm_forward[s] × norm_backward[s])
```

Flag as chokepoint where **both** `norm_forward > 1.0` AND `norm_backward > 1.0`.
Return top-K ranked by `chokepoint_score` descending, tie-break by sector index.

### 3.5 Data Structures

```python
@dataclass(frozen=True)
class PathContribution:
    source_sector: int          # j (final demand target)
    source_sector_code: str     # sector code for j
    target_sector: int          # i (affected sector)
    target_sector_code: str     # sector code for i
    depth: int                  # k (hop count, 0=direct)
    coefficient: float          # (A^k)[i,j] — pure, pre-shock
    contribution: float         # (A^k)[i,j] × delta_d[j]

@dataclass(frozen=True)
class DepthContrib:
    signed: float               # net contribution at this depth
    absolute: float             # sum of |values| at this depth

@dataclass(frozen=True)
class ChokePointScore:
    sector_index: int
    sector_code: str
    forward_linkage: float      # raw row sum of B
    backward_linkage: float     # raw column sum of B
    norm_forward: float         # / mean(forward)
    norm_backward: float        # / mean(backward)
    chokepoint_score: float     # sqrt(nf × nb)
    is_chokepoint: bool         # both > 1.0

@dataclass(frozen=True)
class SPAResult:
    top_paths: list[PathContribution]
    chokepoints: list[ChokePointScore]
    depth_contributions: dict[int, DepthContrib]
    coverage_ratio: float       # Frobenius-norm, [0, 1]
    max_depth: int
    top_k: int
```

### 3.6 Function Signature

```python
def compute_spa(
    A: np.ndarray,
    B: np.ndarray,
    delta_d: np.ndarray,
    sector_codes: list[str],
    *,
    max_depth: int = 6,
    top_k: int = 20,
) -> SPAResult: ...
```

### 3.7 Domain Errors (Engine Layer)

Engine raises typed exceptions. API layer translates to HTTP 422 + reason codes.

| Exception | Condition |
|-----------|-----------|
| `SPAConfigError` | max_depth or top_k out of bounds |
| `SPADimensionError` | A/B/delta_d shape mismatch or sector_codes length mismatch |

Config bounds: `max_depth ∈ [0, 12]`, `top_k ∈ [1, 100]`.

## 4. Section 2: Persistence & Repository

### 4.1 Migration 015: `path_analyses` Table

**New file**: `alembic/versions/015_path_analyses.py`

| Column | Type | Constraint |
|--------|------|------------|
| `analysis_id` | UUID | PK |
| `run_id` | UUID | FK → run_snapshots, NOT NULL |
| `workspace_id` | UUID | FK → workspaces, NOT NULL, INDEX |
| `analysis_version` | VARCHAR(20) | NOT NULL, default `'spa_v1'` |
| `config_json` | FlexJSON | NOT NULL (canonical request config) |
| `config_hash` | VARCHAR(100) | NOT NULL (`sha256:...` prefixed) |
| `max_depth` | INTEGER | NOT NULL |
| `top_k` | INTEGER | NOT NULL |
| `top_paths_json` | FlexJSON | NOT NULL |
| `chokepoints_json` | FlexJSON | NOT NULL |
| `depth_contributions_json` | FlexJSON | NOT NULL |
| `coverage_ratio` | FLOAT | NOT NULL, CHECK (BETWEEN 0 AND 1) |
| `result_checksum` | VARCHAR(100) | NOT NULL (`sha256:...` prefixed) |
| `created_at` | DateTime | NOT NULL |

**Constraints**:
- UNIQUE: `(run_id, config_hash)` — idempotency key
- INDEX: `ix_path_analyses_workspace_id (workspace_id)`
- INDEX: `ix_path_analyses_run_created (run_id, created_at DESC)` — ordered retrieval
- CHECK: `coverage_ratio BETWEEN 0 AND 1`
- FK: `run_id → run_snapshots.run_id`
- FK: `workspace_id → workspaces.workspace_id`

Uses FlexJSON (JSONB on Postgres, JSON on SQLite) consistent with codebase pattern.

### 4.2 ORM Row

**New in `src/db/tables.py`**: `PathAnalysisRow`

### 4.3 Repository

**New file**: `src/repositories/path_analytics.py`

```python
class PathAnalysisRepository:
    async def create(
        *, analysis_id: UUID, run_id: UUID, workspace_id: UUID,
        analysis_version: str, config_json: dict, config_hash: str,
        max_depth: int, top_k: int,
        top_paths_json: list, chokepoints_json: list,
        depth_contributions_json: dict, coverage_ratio: float,
        result_checksum: str,
    ) -> PathAnalysisRow

    async def get(analysis_id: UUID) -> PathAnalysisRow | None

    async def get_for_workspace(
        analysis_id: UUID, workspace_id: UUID,
    ) -> PathAnalysisRow | None

    async def get_by_run_and_config_for_workspace(
        run_id: UUID, config_hash: str, workspace_id: UUID,
    ) -> PathAnalysisRow | None

    async def list_by_run(
        run_id: UUID, workspace_id: UUID,
        *, limit: int = 20, offset: int = 0,
    ) -> list[PathAnalysisRow]
```

### 4.4 Idempotency with Race Safety

INSERT ... ON CONFLICT (run_id, config_hash) DO NOTHING, then SELECT. Concurrent
POSTs with same (run_id, config_hash) converge to exactly one persisted row.

### 4.5 Config Hash

```python
config_hash = "sha256:" + hashlib.sha256(
    json.dumps({"max_depth": k, "top_k": n}, sort_keys=True).encode()
).hexdigest()
```

Deterministic, allows different configs per run.

## 5. Section 3: API Endpoints

**New file**: `src/api/path_analytics.py`
**Router prefix**: `/v1/workspaces/{workspace_id}/path-analytics`

### 5.1 Pydantic Request/Response Models

```python
class PathAnalysisConfig(ImpactOSBase):
    max_depth: int = Field(default=6, ge=0, le=12)
    top_k: int = Field(default=20, ge=1, le=100)

class CreatePathAnalysisRequest(ImpactOSBase):
    run_id: UUID
    config: PathAnalysisConfig = Field(default_factory=PathAnalysisConfig)

class PathContributionItem(ImpactOSBase):
    source_sector_code: str
    target_sector_code: str
    depth: int
    coefficient: float
    contribution: float

class DepthContributionItem(ImpactOSBase):
    signed: float
    absolute: float

class ChokePointItem(ImpactOSBase):
    sector_code: str
    forward_linkage: float
    backward_linkage: float
    norm_forward: float
    norm_backward: float
    chokepoint_score: float
    is_chokepoint: bool

class PathAnalysisResponse(ImpactOSBase):
    analysis_id: UUID
    run_id: UUID
    analysis_version: str
    config: PathAnalysisConfig
    config_hash: str
    top_paths: list[PathContributionItem]
    chokepoints: list[ChokePointItem]
    depth_contributions: dict[str, DepthContributionItem]  # str(k) -> item
    coverage_ratio: float
    result_checksum: str
    created_at: str

class PathAnalysisListResponse(ImpactOSBase):
    items: list[PathAnalysisResponse]
    total: int
```

### 5.2 Endpoints

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | `/path-analytics` | 201/200 | Compute & persist (or return idempotent hit) |
| GET | `/path-analytics/{analysis_id}` | 200 | Get by ID (workspace-scoped) |
| GET | `/path-analytics?run_id=...` | 200 | List by run with pagination |

### 5.3 POST Flow

1. Validate workspace membership (existing auth middleware)
2. Validate config — explicit domain error for out-of-bounds → 422 `SPA_INVALID_CONFIG`
3. Load run → verify `run.workspace_id == workspace_id` → 404 `SPA_RUN_NOT_FOUND`
4. Compute config_hash → check `get_by_run_and_config_for_workspace` → return **200** if exists
5. Load model data via `run.model_version_id` → 422 `SPA_MODEL_DATA_UNAVAILABLE` if missing
6. Load `direct_effect` ResultSet for run → extract delta_d → 422 `SPA_MISSING_DIRECT_EFFECT`
7. Build LoadedModel → get A, B, sector_codes
8. Call `compute_spa(A, B, delta_d, sector_codes, ...)` → catch domain errors → 422
9. Persist via repository (race-safe ON CONFLICT) → return **201**

### 5.4 Error Taxonomy

| Condition | HTTP | Reason Code |
|-----------|------|-------------|
| Run not found / wrong workspace | 404 | `SPA_RUN_NOT_FOUND` |
| No `direct_effect` ResultSet for run | 422 | `SPA_MISSING_DIRECT_EFFECT` |
| No ResultSet at all for run | 422 | `SPA_NO_RESULTS` |
| Model data unavailable | 422 | `SPA_MODEL_DATA_UNAVAILABLE` |
| max_depth / top_k out of bounds | 422 | `SPA_INVALID_CONFIG` |
| Dimension mismatch (shock vs model) | 422 | `SPA_DIMENSION_MISMATCH` |
| Analysis not found / wrong workspace | 404 | `SPA_ANALYSIS_NOT_FOUND` |

**Error precedence**: workspace check → run exists → results exist → direct_effect
exists → model data loadable → dimension check → compute.

### 5.5 Auth

Workspace membership required (viewer-level). No additional role gate. Follows
existing patterns from `runs.py`.

### 5.6 Reuse

Reuse existing `runs.py` patterns for run/model loading. No divergent workspace
or model resolution code paths.

### 5.7 Pagination

List endpoint: `limit` defaults to 20 (max 100), `offset` defaults to 0.
Backward-compatible with codebase pagination patterns.

## 6. Section 4: Testing Strategy

### 6.1 Test Files

| File | ~Tests | Focus |
|------|--------|-------|
| `tests/engine/test_structural_path.py` | 15 | Pure math, identities, chokepoints, edge cases |
| `tests/repositories/test_path_analytics.py` | 10 | CRUD, idempotency, workspace scoping, race safety |
| `tests/api/test_path_analytics.py` | 18 | Endpoints, auth, 422 codes, pagination, idempotency |
| `tests/migration/test_015_path_analytics_postgres.py` | 4 | PG migration up/down, constraints |

### 6.2 Engine Tests (test_structural_path.py)

- 2×2 toy model with hand-computed A^k values — exact match
- 3×3 model: coverage_ratio approaches 1.0 as max_depth increases
- **Scalar identity**: `Σ(depth_contributions[k].signed, k=0..K)` ≈ `sum(B @ delta_d)` within 1e-10
- **Vector identity**: reconstruct per-sector vector from path contributions grouped by target, compare componentwise to `(B @ delta_d)[i]` within 1e-10
- Top-K ranking: deterministic tie-break verified (k ASC, i ASC, j ASC)
- Chokepoint scores: hand-verified forward/backward linkage on 3×3 model
- `is_chokepoint`: True only when both normalized indices > 1.0
- Zero shock → all contributions zero, top_paths empty; coverage_ratio is model-determined (not necessarily 1.0)
- max_depth=0: direct effects only (identity matrix), coverage < 1.0 for connected economies
- max_depth=1: direct + first-round indirect
- Single-sector model (n=1): degenerate case handled
- Domain errors: mismatched dimensions raise `SPADimensionError`

### 6.3 Repository Tests (test_path_analytics.py)

- Round-trip create → get → verify all fields
- `get_by_run_and_config_for_workspace`: exact match returns row, wrong workspace returns None
- `list_by_run`: multiple configs ordered by created_at DESC, respects limit/offset
- Idempotency: second create same (run_id, config_hash) returns existing row
- **Concurrent race test**: two `asyncio.gather` inserts same key → exactly one row, both get same analysis_id
- Workspace isolation: analysis from workspace A invisible to workspace B

### 6.4 API Tests (test_path_analytics.py)

- Happy path POST → 201 with full response schema validated
- Idempotent POST → 200 with same analysis_id
- GET by ID → 200
- GET by ID wrong workspace → 404 `SPA_ANALYSIS_NOT_FOUND`
- List by run → 200 with pagination
- **Error precedence**: wrong workspace run → 404 `SPA_RUN_NOT_FOUND` (before any result check)
- Run exists but no direct_effect → 422 `SPA_MISSING_DIRECT_EFFECT`
- Run exists + results but model data missing → 422 `SPA_MODEL_DATA_UNAVAILABLE`
- Invalid config (max_depth=-1, top_k=200) → 422 `SPA_INVALID_CONFIG`
- Dimension mismatch → 422 `SPA_DIMENSION_MISMATCH`
- Auth: no token → 401, wrong workspace → 404, valid member → 200

### 6.5 Migration Tests (test_015_path_analytics_postgres.py)

- Upgrade creates table with all columns and constraints
- Unique constraint on (run_id, config_hash) enforced
- CHECK on coverage_ratio BETWEEN 0 AND 1 enforced
- Downgrade drops table cleanly

## 7. Files Changed

### New Files
- `src/engine/structural_path.py` — SPA decomposition engine
- `src/models/path.py` — Pydantic schemas for path analytics
- `src/repositories/path_analytics.py` — PathAnalysisRepository
- `src/api/path_analytics.py` — API endpoints
- `alembic/versions/015_path_analyses.py` — migration
- `tests/engine/test_structural_path.py`
- `tests/repositories/test_path_analytics.py`
- `tests/api/test_path_analytics.py`
- `tests/migration/test_015_path_analytics_postgres.py`

### Modified Files
- `src/db/tables.py` — add PathAnalysisRow
- `src/api/main.py` — mount path_analytics router
- `openapi.json` — refreshed
- `docs/evidence/release-readiness-checklist.md` — Sprint 20 section

## 8. Non-Goals (Deferred)

- Named path tracing (individual sector chains) — Sprint 21+
- HHI concentration scoring — Sprint 21+
- Auto-compute at run creation — future opt-in flag
- Async/background SPA execution — future if latency requires
- Frontend visualization — later phase
