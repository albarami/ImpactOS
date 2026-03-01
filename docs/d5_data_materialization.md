# D-5: Data Materialization

## Overview

D-5 replaces ImpactOS's silent synthetic-data fallback with curated Saudi economic
datasets, explicit provenance tracking, and governance-aware export blocking.
Every engine run now records *where* its data came from and whether checksums verified.

## Curated Data Manifest

`data/curated/manifest.json` is the single source of truth for all curated datasets.

| Field | Purpose |
|---|---|
| `dataset_id` | Unique key (e.g. `saudi_io_kapsarc_2018`) |
| `path` | Relative path from project root |
| `checksum_sha256` | SHA-256 of the artifact file |
| `resolved_source` | Classification: `curated_real` or `curated_estimated` |
| `contains_assumed_components` | `true` if any rows use synthetic fallback |
| `confidence` | `HIGH`, `ESTIMATED`, or `HARD` |
| `vintage_year` | Data reference year |

**Adding a new dataset:** see [Adding New Curated Datasets](#adding-new-curated-datasets) below.

## Dataset Classification

| Classification | Meaning | Examples |
|---|---|---|
| `curated_real` | Derived from published statistical sources; no synthetic rows | IO tables (`saudi_io_kapsarc_2018`), Nitaqat targets, Type I multiplier benchmarks |
| `curated_estimated` | Contains some synthetic fallback rows or analyst estimates | Employment coefficients (regional benchmark rows), occupation bridge matrix |
| `synthetic` | Fully generated for test/dev; never used in governed exports | Synthetic IO model (`saudi_io_synthetic_v1.json`) |

## Three Data Modes

Controlled by the `DataMode` enum in `src/data/real_io_loader.py`:

| Mode | Behavior | Use Case |
|---|---|---|
| `STRICT_REAL` | Raises `FileNotFoundError` if curated data is missing | CI `real_data` tests, production runs |
| `PREFER_REAL` | Uses curated if available, falls back to synthetic with warning | Default development mode |
| `SYNTHETIC_ONLY` | Always loads synthetic model, skips curated lookup | Fast unit tests, offline dev |

## Year Resolution

The loader searches for the closest available vintage year:

1. Exact match on `requested_year`
2. Alternating search: `year-1`, `year+1`, `year-2`, `year+2`, ... up to +/-4
3. If no match within the 9-year window, the mode's fallback rules apply

The provenance record captures both `requested_year` and `resolved_year` so
downstream consumers can detect and report vintage drift.

## Materializing Curated Data

```bash
python -m scripts.materialize_curated_data
```

**What it produces:**

| Artifact | Description |
|---|---|
| `saudi_io_kapsarc_2018.json` | 20-sector Saudi IO model (Z matrix + gross output vector) |
| `saudi_type1_multipliers_benchmark.json` | Type I output multipliers per sector |
| `saudi_employment_coefficients_2019.json` | Employment coefficients (jobs per M SAR) |

**Post-materialization steps:**
- Validates the IO model via `validate_model()` (spectral radius, positive VA)
- Recomputes SHA-256 checksums and updates `manifest.json`
- Runs the strict loader to verify round-trip integrity

**When to re-run:** after editing sector data, adding new vintages, or updating
the employment coefficient builder.

## Provenance Flow

Data provenance flows through four stages:

```
Loader --> Quality Assessment --> Export Governance --> RunSnapshot
```

### 1. Loader

`load_real_saudi_io_strict(mode, year, manifest)` returns `ProvenancedIOData`
containing both `IOModelData` and `IODataProvenance`:

```python
@dataclass(frozen=True)
class IODataProvenance:
    data_mode: DataMode
    resolved_source: str       # "curated_real" | "synthetic_fallback" | ...
    used_fallback: bool
    dataset_id: str | None
    requested_year: int | None
    resolved_year: int | None
    checksum_verified: bool
    fallback_reason: str | None
    manifest_entry: dict | None
```

### 2. Quality Assessment

`QualityAssessmentService.assess(data_provenance=...)` populates provenance
fields on `RunQualityAssessment`:

- `data_mode` -- resolved source classification
- `used_synthetic_fallback` -- boolean flag
- `fallback_reason` -- human-readable explanation
- `data_source_id` -- manifest dataset_id
- `checksum_verified` -- SHA-256 match against manifest

If fallback was used, a `WAIVER_REQUIRED` quality warning is emitted.

### 3. Export Governance

`ExportOrchestrator.execute(quality_assessment=...)` blocks governed exports
when `used_synthetic_fallback` is true. Sandbox exports proceed with watermarks.

### 4. RunSnapshot Badge

`RunSnapshot` records three provenance fields for audit:

| Field | Type | Purpose |
|---|---|---|
| `data_mode` | `str \| None` | Source classification |
| `data_source_id` | `str \| None` | Manifest dataset_id |
| `checksum_verified` | `bool` | SHA-256 match at load time |

## Seed Profiles

Seed profiles map to `DataMode` values for test and CI configurations:

| Profile | DataMode | Purpose |
|---|---|---|
| `synthetic` | `SYNTHETIC_ONLY` | Fast unit tests, no curated data required |
| `curated_real` | `STRICT_REAL` | CI gate tests; fails if curated data is missing |
| `prefer_real` | `PREFER_REAL` | Default; uses curated when available |

## Adding New Curated Datasets

1. **Add the artifact** to `data/curated/` (JSON format matching existing schemas).
2. **Run materialization** if the artifact is generated:
   ```bash
   python -m scripts.materialize_curated_data
   ```
3. **Compute checksum** (done automatically by the script, or manually):
   ```bash
   python -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('data/curated/YOUR_FILE.json').read_bytes()).hexdigest())"
   ```
4. **Update `manifest.json`** -- add a new entry with `dataset_id`, `path`,
   `checksum_sha256`, `resolved_source`, and `confidence`.
5. **Run tests** to verify the new dataset loads correctly:
   ```bash
   python -m pytest tests/ -x -q -m real_data
   ```
