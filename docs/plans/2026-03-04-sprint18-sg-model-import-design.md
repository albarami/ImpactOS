# Sprint 18: SG Model Import Adapter + Parity Benchmark Gate — Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan from this design.

**Goal:** Build a production-ready SG workbook import adapter that extracts IO model artifacts from `.xlsb`/`.xlsx`, wires them through existing validation and persistence, and enforces an output-level parity benchmark gate before marking imported models ready for runtime use.

**Architecture:** Thin adapter module + standalone parity gate. SG-specific parsing stays isolated in a new module (`sg_model_adapter.py`), separate from the existing intervention parser (`sg_template_parser.py`). The parity gate operates on engine outputs (not raw matrices), catching real methodology drift. Provenance is persisted in DB so it survives rehydration.

**Tech Stack:** Python 3.11+, openpyxl (.xlsx), pyxlsb (.xlsb), NumPy, FastAPI, SQLAlchemy, Alembic.

---

## 1. Architecture Overview

### 1.1 New/Modified Modules

| Module | Action | Purpose |
|--------|--------|---------|
| `src/data/sg_model_adapter.py` | NEW | Extract IO artifacts from SG workbooks |
| `src/engine/parity_gate.py` | NEW | Output-level golden-run comparison |
| `src/data/io_loader.py` | MODIFY | Implement `load_from_excel()` delegation |
| `src/api/models.py` | MODIFY | Add `POST /{workspace_id}/models/import-sg` endpoint |
| `src/db/tables.py` | MODIFY | Add `sg_provenance` column to `ModelVersionRow` |
| `src/repositories/engine.py` | MODIFY | Wire `sg_provenance` through create/get/list |
| `alembic/versions/013_sg_provenance.py` | NEW | Additive migration for sg_provenance column |

### 1.2 Data Flow (Happy Path)

```
SG Workbook (.xlsb/.xlsx)
  -> sg_model_adapter.extract_io_model()        # parse sheets, extract Z/x/codes/artifacts
  -> validate_extended_model_artifacts()          # existing dimension/range checks
  -> ModelStore.register(artifact_payload=...)    # existing checksum + spectral radius validation
  -> DB persistence (model_versions + model_data rows, with sg_provenance JSON)
  -> parity_gate.run_parity_check()              # solve golden scenario, compare outputs vs baseline
  -> If parity passed: provenance_class="curated_real", return 200
  -> If parity failed + dev bypass: provenance_class="curated_estimated", return 200 with bypass audit
  -> If parity failed + no bypass: rollback model row, return 422
```

### 1.3 Key Design Principle

The parity gate operates on **engine outputs** (total_output, employment, gdp_basic_price, gdp_market_price, gdp_real), not raw matrix comparison. A matrix could look different but produce identical economic results, or look identical but produce wrong results due to upstream extraction bugs. Output-level comparison catches real methodology drift.

---

## 2. Components

### 2.1 `src/data/sg_model_adapter.py`

**Responsibility:** Parse SG workbook sheets to extract IO model artifacts. Knows SG-specific layout conventions (dynamic header scanning, same pattern as `sg_template_parser.py`). Returns `IOModelData` -- nothing SG-specific leaks past this boundary.

**Public API:**

```python
@dataclass(frozen=True)
class SGSheetLayout:
    """Discovered sheet positions from dynamic header scanning."""
    z_sheet: str
    x_sheet: str              # may be same sheet, different range
    sector_codes_sheet: str
    sector_count: int
    year_columns: list[int]
    # Extended artifact sheet names (None = not present in workbook)
    final_demand_sheet: str | None
    imports_sheet: str | None
    value_added_sheet: str | None


class SGImportError(ValueError):
    """SG workbook import failure with stable reason code."""
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code
        self.message = message


def detect_sg_layout(path: Path) -> SGSheetLayout:
    """Scan workbook headers to discover sheet positions dynamically.

    Raises SGImportError(reason_code="SG_LAYOUT_DETECTION_FAILED") if
    required sheets/headers not found.
    """

def extract_io_model(path: Path, *, layout: SGSheetLayout | None = None) -> IOModelData:
    """Extract full IO model from SG workbook.

    If layout is None, calls detect_sg_layout() automatically.
    Returns IOModelData with metadata["sg_provenance"] populated
    (workbook_sha256, source_filename, import_mode, imported_at).

    Raises SGImportError with stable reason codes on any extraction failure.
    """
```

**Header scanning approach:** Mirrors `sg_template_parser.py` -- scan for known header patterns (CODE, SECTOR, year columns matching `r"\d{4}"`) rather than hardcoded cell positions. Resilient to minor template revisions.

**File format support:** `.xlsb` via `pyxlsb`, `.xlsx` via `openpyxl` -- same dual-format pattern proven in `sg_template_parser.py`.

**Provenance metadata:** `extract_io_model()` computes SHA-256 of the raw workbook file and populates `IOModelData.metadata["sg_provenance"]` with:
- `workbook_sha256`: full file hash
- `source_filename`: original filename
- `import_mode`: `"sg_workbook"`
- `imported_at`: UTC ISO timestamp

### 2.2 `src/engine/parity_gate.py`

**Responsibility:** Deterministic output-level comparison. Takes a registered model, runs a golden scenario through the engine, compares outputs against stored baseline. Pure function -- no DB access, no side effects.

**Public API:**

```python
@dataclass(frozen=True)
class ParityMetric:
    """Single metric comparison result."""
    metric_name: str          # "total_output", "employment", "gdp_basic_price", etc.
    expected: float
    actual: float
    relative_error: float
    tolerance: float          # 0.001 (0.1%)
    passed: bool
    reason_code: str | None   # None if passed, "PARITY_TOLERANCE_BREACH" if exceeded


@dataclass(frozen=True)
class ParityResult:
    """Full parity gate outcome."""
    passed: bool
    benchmark_id: str         # identifies which golden scenario was used
    tolerance: float
    metrics: list[ParityMetric]
    reason_code: str | None   # summary reason code if failed
    checked_at: datetime      # UTC timestamp


def run_parity_check(
    *,
    model: LoadedModel,
    benchmark_scenario: dict,   # golden scenario spec (shock vector + expected outputs)
    tolerance: float = 0.001,   # 0.1%
) -> ParityResult:
    """Run golden scenario through engine, compare outputs against baseline.

    Compares only metrics present in benchmark_scenario["expected_outputs"].
    Uses existing metric names: total_output, employment, gdp_basic_price,
    gdp_market_price, gdp_real.

    If a benchmark expects a metric not emitted by the engine, returns
    PARITY_METRIC_MISSING reason code for that metric (does not mask as
    generic engine error).

    Always returns a result -- never raises. Fail-closed logic is caller's
    responsibility.
    """
```

**Tolerance math:** `relative_error = |actual - expected| / |expected|`. Passes when `relative_error <= tolerance`. For expected=0, uses absolute comparison with `atol=1e-10`.

**Reason codes emitted:**
- `PARITY_TOLERANCE_BREACH` -- one or more metrics exceed tolerance
- `PARITY_MISSING_BASELINE` -- no golden benchmark found/loaded
- `PARITY_ENGINE_ERROR` -- engine solve failed during benchmark run
- `PARITY_METRIC_MISSING` -- benchmark expects a metric not emitted by engine

### 2.3 `src/data/io_loader.py` Changes

Implement `load_from_excel()` with extension-based routing and stable error codes:

```python
def load_from_excel(
    path: str | Path,
    config: ExcelSheetConfig | None = None,
) -> IOModelData:
    """Load IO model from Excel workbook.

    Routes by extension:
      .xlsb, .xlsx -> SG model adapter
      Other -> raises ValueError with SG_UNSUPPORTED_FORMAT reason code

    config parameter reserved for future GASTAT integration.
    """
    p = Path(path)
    ext = p.suffix.lower()

    if ext not in (".xlsb", ".xlsx"):
        raise SGImportError(
            "SG_UNSUPPORTED_FORMAT",
            f"Unsupported file extension '{ext}'. Expected .xlsb or .xlsx.",
        )

    if not p.exists():
        raise SGImportError(
            "SG_FILE_UNREADABLE",
            f"File not found: {p}",
        )

    from src.data.sg_model_adapter import extract_io_model
    return extract_io_model(p)
```

### 2.4 `src/api/models.py` -- SG Import Endpoint

**Route:** `POST /v1/workspaces/{workspace_id}/models/import-sg`

Lives in `models.py` (model lifecycle), consistent with existing route prefix.

**Flow:**
1. Receive multipart/form-data workbook upload
2. `sg_model_adapter.extract_io_model()` -> `IOModelData`
3. `validate_extended_model_artifacts()` -> validated artifacts
4. `ModelStore.register()` -> `ModelVersion`
5. Persist to DB via existing repos (with `sg_provenance` JSON + `provenance_class`)
6. `parity_gate.run_parity_check()` -> `ParityResult`
7. **Parity pass:** set `provenance_class="curated_real"`, persist parity outcome in sg_provenance, return 200
8. **Parity fail + dev bypass allowed (ENVIRONMENT==DEV only):** set `provenance_class="curated_estimated"`, persist bypass metadata in sg_provenance, return 200 with `parity_status: "bypassed"`
9. **Parity fail + no bypass (or staging/prod):** **rollback model row**, return 422 with reason code + metrics

**Dev bypass gating:**
```python
from src.config.settings import get_settings, Environment

def _is_dev_bypass_allowed() -> bool:
    return get_settings().ENVIRONMENT == Environment.DEV
```

`dev_bypass` query parameter only honored when `_is_dev_bypass_allowed()` returns True. In staging/prod, parity failure always means 422 -- no model persisted.

**provenance_class alignment with runtime guard:**

| Outcome | provenance_class | runs.py guard | exports.py guard |
|---------|-----------------|---------------|------------------|
| Parity pass | `curated_real` | Allowed | Allowed |
| Parity fail + dev bypass | `curated_estimated` | BLOCKED | BLOCKED |
| Parity fail + no bypass | No model persisted (rollback) | N/A | N/A |

This integrates seamlessly with the existing D-5.1 `_enforce_model_provenance()` guard.

### 2.5 Migration 013: SG Provenance Column

**Additive column on `model_versions` table:**

```python
# alembic/versions/013_sg_provenance.py
revision = "013_sg_provenance"
down_revision = "012_runseries_columns"

def upgrade() -> None:
    op.add_column("model_versions", sa.Column("sg_provenance", sa.JSON(), nullable=True))

def downgrade() -> None:
    op.drop_column("model_versions", "sg_provenance")
```

**ORM update** -- `ModelVersionRow` in `src/db/tables.py`:
```python
sg_provenance: Mapped[dict | None] = mapped_column(FlexJSON, nullable=True)
```

**Repository update** -- `ModelVersionRepository.create()`:
```python
async def create(
    self, *, model_version_id: UUID, base_year: int,
    source: str, sector_count: int, checksum: str,
    provenance_class: str = "unknown",
    sg_provenance: dict | None = None,
) -> ModelVersionRow:
```

**API response update** -- `ModelVersionResponse`:
```python
sg_provenance: dict | None = None
```

**`_row_to_response()` mapping:**
```python
sg_provenance=getattr(row, "sg_provenance", None),
```

**Persisted sg_provenance JSON structure (full, after parity check):**
```json
{
  "workbook_sha256": "sha256:abc123...",
  "source_filename": "SG_Model_2024Q4.xlsb",
  "import_mode": "sg_workbook",
  "imported_at": "2026-03-04T12:00:00Z",
  "parity_status": "verified",
  "parity_checked_at": "2026-03-04T12:00:01Z",
  "benchmark_id": "sg_3sector_golden_v1",
  "tolerance": 0.001,
  "reason_code": null,
  "dev_bypass": false
}
```

Null for non-SG models. Additive -- no existing rows affected.

### 2.6 Stable Reason Codes

Defined as string constants (or enum). Used across all modules:

| Code | Module | Meaning |
|------|--------|---------|
| `SG_UNSUPPORTED_FORMAT` | io_loader | File extension not .xlsb/.xlsx |
| `SG_FILE_UNREADABLE` | sg_model_adapter | Corrupt, encrypted, zero-byte, not found |
| `SG_LAYOUT_DETECTION_FAILED` | sg_model_adapter | Required sheets/headers not found |
| `SG_PARSE_MATRIX_FAILED` | sg_model_adapter | Z/x extraction failed (corrupt data, wrong dimensions) |
| `SG_PARSE_SECTORS_FAILED` | sg_model_adapter | Sector codes/names extraction failed |
| `SG_PARSE_ARTIFACT_FAILED` | sg_model_adapter | Extended artifact extraction failed |
| `MODEL_*` (native codes) | io_loader | Preserved from `validate_extended_model_artifacts()` (e.g. `MODEL_FINAL_DEMAND_DIMENSION_MISMATCH`, `MODEL_HOUSEHOLD_SHARES_INVALID_SUM`, etc.) |
| `MODEL_REGISTRATION_FAILED` | model_store | Spectral radius, dimensions, non-negativity |
| `PARITY_TOLERANCE_BREACH` | parity_gate | One or more metrics exceed 0.1% |
| `PARITY_MISSING_BASELINE` | parity_gate | No golden benchmark available |
| `PARITY_ENGINE_ERROR` | parity_gate | Engine solve failed during benchmark run |
| `PARITY_METRIC_MISSING` | parity_gate | Benchmark expects metric not emitted by engine |
| `PARITY_BYPASSED_DEV` | api/models | Dev bypass used -- audit trail only |

**Native validator codes are preserved.** When `validate_extended_model_artifacts()` raises `ModelArtifactValidationError`, the endpoint surfaces the original `reason_code` (e.g. `MODEL_COMPENSATION_VECTOR_DIMENSION_MISMATCH`) directly in the 422 response. No collapsing into a generic wrapper.

---

## 3. Error Handling

### 3.1 Error Response Envelope

Matches existing codebase style -- `HTTPException` with dict detail:

```python
raise HTTPException(
    status_code=422,
    detail={
        "reason_code": "PARITY_TOLERANCE_BREACH",
        "message": "Metric total_output exceeded 0.1% tolerance: expected 2847.3, got 2855.1 (0.27%)",
        "metrics": [
            {"metric": "total_output", "expected": 2847.3, "actual": 2855.1, "error_pct": 0.27, "passed": False},
            {"metric": "employment", "expected": 15420.0, "actual": 15418.5, "error_pct": 0.01, "passed": True},
        ],
    },
)
```

`metrics` field only present when `reason_code` starts with `PARITY_`. Parse/validation failures include `reason_code` + `message` only.

### 3.2 Atomicity Guarantee

**Parity failure without bypass leaves NO persisted model row.**

Implementation: the endpoint wraps registration + parity in a single DB transaction. If parity fails and no dev bypass is used, the transaction is rolled back. The model_version_id returned by `ModelStore.register()` is never committed to DB.

This is enforced by an explicit integration test:
```python
def test_parity_failure_rollback_leaves_no_model_row():
    """Parity failure without bypass must leave no model_versions row."""
    # POST import-sg with a model that fails parity
    # Assert 422 response
    # Query DB: assert model_versions table has no row for attempted import
```

---

## 4. Test Strategy

### 4.1 Unit Tests (no DB, no files)

| Test file | What | ~Count |
|-----------|------|--------|
| `tests/data/test_sg_model_adapter.py` | Layout detection, matrix parsing, error reason codes, .xlsx fixture, .xlsb fixture (skip-if pyxlsb unavailable) | ~15 |
| `tests/engine/test_parity_gate.py` | Metric comparison, tolerance math, all reason codes, edge cases (zero expected, missing metric) | ~12 |
| `tests/data/test_io_loader_excel.py` | `load_from_excel()` delegation, extension routing, unsupported format error code, file not found error code | ~6 |

**Fixture files:** Tiny 3-sector `.xlsx` (always available) and `.xlsb` (skip-if `pyxlsb` not installed) committed to `tests/fixtures/`. No real SG production workbooks in repo.

**`.xlsb` path test:** At minimum one smoke test using a `.xlsb` fixture that exercises the `pyxlsb` code path. Marked `pytest.mark.skipif(not HAS_PYXLSB)` so CI without `pyxlsb` doesn't fail, but dual-format support is proven when the dependency is present.

**Parity gate tests** are pure -- construct `LoadedModel` from numpy arrays, run engine solve, compare results. Explicitly test:
- Pass path (within tolerance)
- Fail path (one metric breaches tolerance)
- Missing baseline
- Engine error (singular matrix)
- Missing metric (benchmark expects `gdp_real` but engine doesn't emit it -> `PARITY_METRIC_MISSING`)

### 4.2 Integration Tests (DB)

| Test file | What | ~Count |
|-----------|------|--------|
| `tests/api/test_models_import_sg.py` | Full endpoint: upload -> validate -> register -> parity -> response | ~10 |
| `tests/migration/test_013_sg_provenance_postgres.py` | Migration up/down/re-up + alembic check (Sprint 17 pattern) | ~4 |

**API integration tests cover:**
- Happy path: SG import -> parity pass -> 200 + `provenance_class="curated_real"`
- Each SG_* reason code -> 422
- Native MODEL_* reason code preservation -> 422
- Parity tolerance breach -> 422 with metrics
- Dev bypass in dev env -> 200 + `provenance_class="curated_estimated"`
- Dev bypass rejected in non-dev env -> 422
- **Atomicity: parity failure rollback leaves no model row**
- sg_provenance visible in GET /versions/{id} response

### 4.3 Parity Golden Benchmark

One golden benchmark fixture committed to `tests/fixtures/sg_parity_benchmark_v1.json`:
```json
{
  "benchmark_id": "sg_3sector_golden_v1",
  "description": "3-sector toy model parity check",
  "model": { "Z": [[...]], "x": [...], "sector_codes": [...] },
  "scenario": { "shock_vector": [...] },
  "expected_outputs": {
    "total_output": 2847.3,
    "employment": 15420.0,
    "gdp_basic_price": 1523.7
  },
  "tolerance": 0.001
}
```

Known-answer test: expected outputs computed once from reference implementation and frozen. Any imported model must reproduce within 0.1%.

### 4.4 Postgres Migration Gate

`test_013_sg_provenance_postgres.py`: upgrade/downgrade/re-upgrade/alembic check. Same skip-if pattern as Sprint 17's test_012. Verifies sg_provenance column exists after upgrade and is absent after downgrade.

---

## 5. Locked Design Decisions (Consolidated)

From user across Sections 1-3:

1. **Separate modules:** `sg_template_parser.py` for interventions, `sg_model_adapter.py` for IO model extraction.
2. **Output-level parity:** Gate compares engine run outputs (golden scenarios), not raw IOModelData matrices.
3. **Persistent provenance:** `sg_provenance` JSON column on `model_versions` (migration 013 + ORM + repo + API response). Survives DB round-trip.
4. **Stable fail-closed reason codes:** Defined up front (Section 2.6). Native validator codes preserved, not collapsed.
5. **Unified registration path:** adapter -> `validate_extended_model_artifacts()` -> `ModelStore.register()` -> existing repos.
6. **Route:** `POST /v1/workspaces/{workspace_id}/models/import-sg` in `api/models.py`.
7. **Environment-gated bypass:** `dev_bypass` allowed only when `ENVIRONMENT==DEV`. Staging/prod always fail-closed.
8. **provenance_class alignment:** Parity pass -> `curated_real` (runtime allowed). Fail/bypass -> `curated_estimated` (runtime blocked by existing D-5.1 guard).
9. **Atomicity:** Parity failure without bypass rolls back model row. Explicit test enforces this.
10. **Existing error envelope:** `HTTPException(detail={"reason_code": ..., "message": ..., "metrics": ...})`.
11. **Existing metric names only:** `total_output`, `employment`, `gdp_basic_price`, `gdp_market_price`, `gdp_real`.
12. **`load_from_excel()` extension routing:** Routes by `.xlsb`/`.xlsx`, stable error code for unsupported format.
13. **Dual-format testing:** At least one `.xlsb` smoke test (skip-if `pyxlsb` unavailable).
14. **Missing metric code:** `PARITY_METRIC_MISSING` when benchmark expects a metric not emitted by engine.
