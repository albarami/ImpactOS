# D-5: Data Materialization & Wiring — Design Document

**Date:** 2026-03-01
**Status:** Approved
**Sprint:** D-5 (post-MVP-14)

## Problem Statement

D-1 through D-4 built fetchers, parsers, loaders, and validators. But the data pipeline has critical honesty gaps:

1. `load_real_saudi_io()` silently falls back to synthetic data — no provenance returned
2. `_load_io_ratios()` in satellite_coeff_loader.py prefers synthetic satellites even when curated IO exists
3. Employment coefficients can contain synthetic fallback rows, but nothing classifies this honestly
4. `RunQualityAssessment` has no data-mode fields
5. `QualityAssessmentService.assess()` has no provenance input beyond a plain `model_source` string
6. `ExportOrchestrator.execute()` takes only request and claims — no quality/provenance path
7. No manifest system exists to track curated datasets

## Design Decisions

### 1. DataMode Enum + IODataProvenance

Three explicit modes replace silent fallback:
- `STRICT_REAL` — fail if curated data absent
- `PREFER_REAL` — use curated if present, synthetic otherwise (with honest provenance)
- `SYNTHETIC_ONLY` — always synthetic

IODataProvenance modeled after existing `CoefficientProvenance` in satellite_coeff_loader.py but adapted for IO loading (which differs from coefficient loading). Key fields:
- `data_mode`, `resolved_source`, `used_fallback`, `dataset_id`
- `requested_year`, `resolved_year` (exposes nearest-year resolution)
- `checksum_verified`, `fallback_reason`, `manifest_entry`

### 2. Dataset Classification (not blunt curated_real)

Three honest classifications:
- `curated_real` — directly from published source (IO tables, Nitaqat targets)
- `curated_estimated` — mixed/derived data containing synthetic fallback rows (employment coefficients, occupation bridge)
- `synthetic` — fully synthetic benchmark data

### 3. Manifest as Single Source of Truth

`data/curated/manifest.json` tracks all curated datasets with checksums, classification, and provenance. `src/data/manifest.py` loads and validates it.

### 4. Strict Loader Before Materialization

`load_real_saudi_io_strict()` must exist before `scripts/materialize_curated_data.py` — prevents writing synthetic data labeled as curated. Materialization uses a two-phase flow: build from upstream, then validate with strict loader.

### 5. Satellite Ratio Fix

`_load_io_ratios()` preference order changed to: curated real IO → curated satellites → synthetic fallback.

### 6. Quality Extension (not duplication)

Provenance fields added directly to existing `RunQualityAssessment` model: `data_mode`, `used_synthetic_fallback`, `fallback_reason`, `data_source_id`, `checksum_verified`.

### 7. Export Wiring via Option A

`ExportOrchestrator.execute()` gains optional `quality_assessment: RunQualityAssessment | None = None` parameter. Synthetic fallback in GOVERNED mode triggers WAIVER_REQUIRED. PublicationGate is NOT modified.

### 8. Provenance Badge on RunSnapshot

`RunSnapshot` gains `data_mode`, `data_source_id`, `checksum_verified` fields. Every run permanently records its data path.

## Implementation Order (9 Steps)

| Step | Description | Creates/Modifies |
|------|-------------|-----------------|
| 1 | Curated data manifest | `src/data/manifest.py`, `data/curated/manifest.json` |
| 2 | Strict/provenanced IO loader | `src/data/real_io_loader.py` |
| 3 | Build curated artifacts | `scripts/materialize_curated_data.py`, `data/curated/*.json` |
| 4 | Fix satellite_coeff_loader | `src/data/workforce/satellite_coeff_loader.py` |
| 5 | Extend quality models | `src/quality/models.py`, `src/quality/service.py` |
| 6 | Wire provenance into export | `src/export/orchestrator.py` |
| 7 | Real-data integration tests | `tests/integration/test_real_data_pipeline.py` |
| 8 | Provenance badge + update tests | `src/models/run.py`, existing test files |
| 9 | Update markers + docs | `pyproject.toml`, `docs/d5_data_materialization.md` |

### Ordering Rationale
- Step 2 BEFORE Step 3: strict loader prevents writing synthetic as curated
- Step 3 is two-phase: build from upstream FIRST, then validate
- Step 4 BEFORE Step 7: satellite ratios must prefer real before integration test
- Steps 5-6 BEFORE Step 7: integration test asserts quality.data_mode and export behavior
- Step 7 AFTER Steps 4-6: test verifies the complete wiring end-to-end

## 13 Mandatory Corrections Applied

1. Strict loader BEFORE materialization script
2. Filenames match existing loader expectations (year-suffixed)
3. Reuse CoefficientProvenance vocabulary pattern
4. Fix _load_io_ratios() preference order; test via public API
5. Align benchmark test with actual BenchmarkValidator API
6. Use existing save_employment_coefficients() — correct module path
7. Extend RunQualityAssessment — no parallel model
8. Synthetic-data export in ExportOrchestrator, NOT PublicationGate
9. Register real_data and integration markers (update existing)
10. Update docs after D-5 (data modes, materialization, runtime behavior)
11. Honest dataset classification (curated_real vs curated_estimated vs synthetic)
12. Include requested_year and resolved_year in IO provenance
13. Explicit provenance-to-export wiring path (Option A chosen)

## Constraints

- All ~3,148 existing tests must pass — zero regressions
- Backward compatible — existing `load_real_saudi_io()` wraps new API
- Curated fixtures committed to repo — engine never calls live APIs at runtime
- Provenance is never silent — every load returns explicit data_mode + years
- Python 3.11+, type hints, Pydantic v2
- ~30-40 new tests expected

## Validated Against Codebase

All APIs verified against actual source files on main (commit `8a872ab`):
- `CoefficientProvenance` fields: employment_coeff_year, io_base_year, import_ratio_year, va_ratio_year, fallback_flags, synchronized
- `BenchmarkValidator.validate_multipliers()` returns ValidationReport with total_sectors, sectors_within_tolerance, overall_pass
- `RunQualityAssessment` is ImpactOSBase with frozen=True, has no data_mode fields
- `ExportOrchestrator.execute()` takes request + claims only
- `PublicationGate.check()` is NFF-only
- pyproject.toml already has integration and real_data markers (real_data is "reserved")
