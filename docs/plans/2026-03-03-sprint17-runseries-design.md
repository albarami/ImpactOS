# Sprint 17 Design: RunSeries Annual Storage + API (MVP-17)

**Date:** 2026-03-03
**Branch:** `phase2e-sprint17-runseries-annual-storage-api`
**Baseline:** 4114 tests on main at `4374376`

## Problem

The Leontief phased solver produces annual per-year results (`PhasedResult.annual_results`), but the batch runner aggregates them into cumulative totals and discards the annual breakdown. There is no persistence, retrieval, or API exposure for per-year time-series data. Scenario-vs-baseline delta series is also absent.

## Locked Constraints

1. **No explicit cumulative rows** — legacy `series_kind=NULL` rows remain the cumulative representation.
2. **Structured columns, not encoded metric_type** — `year`, `series_kind`, `baseline_run_id` are nullable columns on `ResultSetRow`, not string-encoded in `metric_type`.
3. **Partial unique indexes + CHECK constraints** — not COALESCE uniqueness hacks.
4. **Flat API shape** — `include_series=true` returns flat `result_sets` rows with optional `series_kind`, `year`, `baseline_run_id`, `confidence_class` fields. No nested `RunSeriesResponse`.
5. **Delta series in scope** — with explicit reason codes: `RS_BASELINE_NOT_FOUND`, `RS_BASELINE_NO_SERIES`, `RS_YEAR_MISMATCH`, `RS_BASELINE_METRIC_MISMATCH`.
6. **Deterministic math only** — no LLM involvement in series generation or aggregation.
7. **Additive only** — existing API contracts, auth behavior, result keys unchanged.

## Schema Design

### ResultSetRow Extended (3 new nullable columns)

```
ResultSetRow (existing table)
──────────────────────────────────────────────
result_id         UUID PK           (unchanged)
run_id            UUID FK           (unchanged)
metric_type       str(100)          (unchanged)
values            JSON              (unchanged)
sector_breakdowns JSON              (unchanged)
year              int | NULL        NEW — annual year or peak year
series_kind       str(20) | NULL    NEW — 'annual'|'peak'|'delta' or NULL
baseline_run_id   UUID | NULL       NEW — FK for delta series
workspace_id      UUID | NULL       (unchanged)
created_at        timestamp         (unchanged)
```

### Row Interpretation

| series_kind | year | baseline_run_id | Meaning |
|---|---|---|---|
| NULL | NULL | NULL | Legacy cumulative row (Sprints 9-16) |
| `"annual"` | 2026 | NULL | Annual output for year 2026 |
| `"peak"` | 2028 | NULL | Peak-year output (year = peak year) |
| `"delta"` | 2026 | `<uuid>` | Scenario minus baseline for year 2026 |

### Partial Unique Indexes

```sql
-- Legacy cumulative rows: one per (run, metric)
CREATE UNIQUE INDEX uq_resultset_legacy
  ON result_sets (run_id, metric_type)
  WHERE series_kind IS NULL;

-- Annual rows: one per (run, metric, year)
CREATE UNIQUE INDEX uq_resultset_annual
  ON result_sets (run_id, metric_type, year)
  WHERE series_kind = 'annual';

-- Peak rows: one per (run, metric)
CREATE UNIQUE INDEX uq_resultset_peak
  ON result_sets (run_id, metric_type)
  WHERE series_kind = 'peak';

-- Delta rows: one per (run, metric, year, baseline)
CREATE UNIQUE INDEX uq_resultset_delta
  ON result_sets (run_id, metric_type, year, baseline_run_id)
  WHERE series_kind = 'delta';
```

### CHECK Constraints

```sql
-- series_kind must be one of the allowed values
ALTER TABLE result_sets ADD CONSTRAINT chk_series_kind
  CHECK (series_kind IN ('annual', 'peak', 'delta') OR series_kind IS NULL);

-- year required for annual, peak, delta
ALTER TABLE result_sets ADD CONSTRAINT chk_year_required
  CHECK (
    (series_kind IS NULL AND year IS NULL)
    OR (series_kind IS NOT NULL AND year IS NOT NULL)
  );

-- baseline_run_id required only for delta, null otherwise
ALTER TABLE result_sets ADD CONSTRAINT chk_baseline_delta
  CHECK (
    (series_kind = 'delta' AND baseline_run_id IS NOT NULL)
    OR (series_kind != 'delta' AND baseline_run_id IS NULL)
    OR (series_kind IS NULL AND baseline_run_id IS NULL)
  );
```

## Batch Emission Design

### Metrics emitted as annual series

| metric_type | Annual? | Peak? | Delta? | Notes |
|---|---|---|---|---|
| `total_output` | Yes | Yes | Yes | Core Leontief output |
| `direct_effect` | Yes | No | Yes | Per-year direct from SolveResult |
| `indirect_effect` | Yes | No | Yes | Per-year indirect from SolveResult |
| `type_ii_total_output` | Yes | No | Yes | Only if Type II prerequisites present |
| `induced_effect` | Yes | No | Yes | Only if Type II prerequisites present |

### Metrics NOT emitted as annual series

| metric_type | Reason |
|---|---|
| `employment`, `imports`, `value_added`, `domestic_output` | Satellite coefficients applied to cumulative delta_x only |
| `gdp_*`, `balance_of_trade`, `non_oil_exports`, `government_*` | Value measures computed on cumulative output |
| `type_ii_employment` | Satellite on Type II cumulative |

### Emission logic in batch runner

```python
# After existing cumulative emission...

# Annual series
for year, result in sorted(phased.annual_results.items()):
    result_sets.append(ResultSet(
        metric_type="total_output",
        values=vec_to_dict(result.delta_x_total, sector_codes),
        year=year,
        series_kind="annual",
    ))
    result_sets.append(ResultSet(
        metric_type="direct_effect",
        values=vec_to_dict(result.delta_x_direct, sector_codes),
        year=year,
        series_kind="annual",
    ))
    result_sets.append(ResultSet(
        metric_type="indirect_effect",
        values=vec_to_dict(result.delta_x_indirect, sector_codes),
        year=year,
        series_kind="annual",
    ))
    # Type II annual if available...

# Peak
result_sets.append(ResultSet(
    metric_type="total_output",
    values=vec_to_dict(phased.peak_delta_x, sector_codes),
    year=phased.peak_year,
    series_kind="peak",
))

# Delta series (if baseline_run_id provided)
# Load baseline annual rows, validate overlap, compute per-year deltas
```

### Row count estimate (3-year, 3-sector, with baseline)

- Legacy cumulative: ~17 rows (unchanged)
- Annual: 3 years x 3 metrics = 9 rows
- Peak: 1 row
- Delta: 3 years x 3 metrics = 9 rows (if baseline)
- **Total: ~36 rows per run** (up from ~17)

## Delta Series Design

### Request field

`RunRequest` gains optional `baseline_run_id: UUID | None = None`.

### Validation matrix

| Condition | HTTP | Reason Code | Detail |
|---|---|---|---|
| baseline_run_id not found | 404 | `RS_BASELINE_NOT_FOUND` | Baseline run does not exist |
| baseline has no annual series rows | 422 | `RS_BASELINE_NO_SERIES` | Baseline was run before Sprint 17 |
| year sets don't overlap | 422 | `RS_YEAR_MISMATCH` | No common years between scenario and baseline |
| metric_type sets don't overlap | 422 | `RS_BASELINE_METRIC_MISMATCH` | Metric mismatch between runs |

### Delta computation

```python
delta_values[sector] = scenario_annual[year][metric][sector] - baseline_annual[year][metric][sector]
```

Deterministic subtraction. No interpolation, no extrapolation.

## API Design

### Existing endpoints (backward compatible)

- `POST /v1/workspaces/{wid}/engine/runs` — unchanged default behavior
- `GET /v1/workspaces/{wid}/engine/runs/{run_id}` — unchanged default behavior
- `POST /v1/workspaces/{wid}/engine/batch` — unchanged default behavior

### New query parameter: `include_series=true`

When `include_series=true` on GET endpoints:
- `result_sets` array includes ALL rows (legacy + annual + peak + delta)
- Each `ResultSetResponse` gains optional fields:

```python
class ResultSetResponse(BaseModel):
    result_id: str
    metric_type: str
    values: dict[str, float]
    confidence_class: str = "COMPUTED"
    # New optional fields (Sprint 17):
    year: int | None = None
    series_kind: str | None = None        # "annual"|"peak"|"delta"
    baseline_run_id: str | None = None
```

### New request field: `baseline_run_id`

```python
class RunRequest(BaseModel):
    # ... existing fields ...
    baseline_run_id: UUID | None = None   # NEW — for delta series
```

### Confidence class for series rows

| series_kind | confidence_class |
|---|---|
| NULL (legacy) | Same as Sprint 16 rules |
| `"annual"` | Same as cumulative counterpart |
| `"peak"` | Same as cumulative counterpart |
| `"delta"` | `ESTIMATED` |

## Migration

Single Alembic migration:
1. Add `year` (nullable int) to `result_sets`
2. Add `series_kind` (nullable varchar(20)) to `result_sets`
3. Add `baseline_run_id` (nullable UUID) to `result_sets`
4. Add CHECK constraints
5. Add partial unique indexes

No data migration needed — existing rows have all NULL for new columns.
