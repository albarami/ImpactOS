# MVP-11: Workforce/Saudization Satellite

## Overview

The Workforce Satellite answers the core workforce question for every scenario: **How many jobs? What occupations? How many Saudi jobs? Is this achievable?**

It consumes D-4 curated data (occupation bridge, nationality classifications, Nitaqat targets) and produces range-based workforce assessments with full confidence propagation.

## Architecture

```
SatelliteResult (delta_jobs from engine)
    │
    ▼
┌──────────────────────┐
│  Step 2: Occupation   │  → OccupationImpact per (sector, occupation)
│  Decomposition        │     uses OccupationBridge (D-4)
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│  Step 3: Nationality  │  → NationalitySplit with min/mid/max ranges
│  Feasibility Split    │     uses NationalityClassificationSet (D-4)
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│  Step 4: Nitaqat      │  → 5-state compliance status per sector
│  Compliance Check     │     uses MacroSaudizationTargets (D-4)
└──────────────────────┘
    │
    ▼
WorkforceResult (full result with caveats + provenance)
```

### Key Principle

The Workforce Satellite is **fully deterministic** — no LLM calls. It lives in `src/engine/workforce_satellite/` alongside the existing engine. This maintains the Agent-to-Math Boundary: AI components produce structured JSON (classification overrides), the engine applies them mathematically.

## Package Structure

```
src/engine/workforce_satellite/
├── __init__.py      # Package docstring
├── config.py        # Tier ranges, confidence ranking, worst_confidence()
├── schemas.py       # All Pydantic result models
└── satellite.py     # WorkforceSatellite service (4-step pipeline)
```

## Pipeline Steps

| Step | Input | Output | D-4 Data |
|------|-------|--------|----------|
| 1 (pre) | SatelliteAccounts.compute() | delta_jobs vector | — |
| 2 | delta_jobs + sector_codes | OccupationImpact per pair | OccupationBridge |
| 3 | OccupationImpacts | NationalitySplit (min/mid/max) | NationalityClassificationSet |
| 4 | SectorWorkforceSummaries | Compliance status | MacroSaudizationTargets |

## Amendments Implemented

1. **BaselineSectorWorkforce** — required for meaningful Nitaqat compliance; without it → INSUFFICIENT_DATA
2. **Nitaqat target ranges** — 5-state compliance (COMPLIANT/AT_RISK/NON_COMPLIANT/NO_TARGET/INSUFFICIENT_DATA), target_range_low and target_range_high preserved
3. **Negative jobs** — min/mid/max maintain numeric order for contracting sectors (min ≤ mid ≤ max always)
4. **Provenance** — bridge_version, classification_version, coefficient_provenance populated from `__init__` D-4 objects
5. **Typed models** — TrainingGapEntry and AppliedOverride are Pydantic models, not list[dict]
6. **Normalized confidence** — worst_confidence() and confidence_to_str() normalize ConstraintConfidence, QualityConfidence, and strings
7. **Tier-range policy** — DEFAULT_TIER_RANGES from config, overridable via `tier_ranges` param
8. **Result granularity** — result_granularity metadata field ("section" for v1)
9. **Missing-data defaults** — missing bridge → elementary + ASSUMED, missing classification → EXPAT_RELIANT + ASSUMED
10. **Dynamic caveats** — generated from actual inputs (missing baselines, applied overrides)

## Tier Ranges (Default)

| Tier | Saudi % Low | Saudi % Mid | Saudi % High |
|------|-------------|-------------|--------------|
| SAUDI_READY | 70% | 85% | 100% |
| SAUDI_TRAINABLE | 20% | 40% | 60% |
| EXPAT_RELIANT | 0% | 5% | 20% |

When `current_saudi_pct` is available from D-4 data, it is used as the midpoint with ±10% sensitivity range instead.

## Usage

### Basic: Analyze workforce impacts

```python
from src.engine.workforce_satellite.satellite import WorkforceSatellite
from src.engine.workforce_satellite.schemas import BaselineSectorWorkforce

ws = WorkforceSatellite(
    occupation_bridge=d4_bridge,
    nationality_classifications=d4_classifications,
    nitaqat_targets=d4_nitaqat_targets,
)

result = ws.analyze(
    satellite_result=sat_result,  # from SatelliteAccounts.compute()
    sector_codes=["A", "B", "C", "F"],
    baseline_workforce=baseline,  # for Nitaqat compliance
)

# Key outputs
print(result.total_jobs)                     # Total delta jobs
print(result.total_saudi_jobs_mid)           # Mid-point Saudi estimate
print(result.total_saudi_pct_range)          # (low%, high%)
print(result.sectors_compliant)              # Count meeting Nitaqat
print(result.sectors_non_compliant)          # Count below target
print(result.training_gap_summary)           # Priority training needs
print(result.overall_confidence)             # Worst-case confidence
```

### With Knowledge Flywheel overrides

```python
from src.data.workforce.nationality_classification import ClassificationOverride

overrides = [
    ClassificationOverride(
        sector_code="F", occupation_code="8",
        original_tier=NationalityTier.EXPAT_RELIANT,
        override_tier=NationalityTier.SAUDI_TRAINABLE,
        overridden_by="analyst",
        engagement_id="eng-001",
        rationale="New training program available",
        timestamp="2024-06-01",
    ),
]

result = ws.analyze(
    satellite_result=sat_result,
    sector_codes=["A", "F"],
    overrides=overrides,
)
print(result.overrides_applied)  # Tracked for audit
```

## Known Limitations (v1)

- Occupation bridge at ISIC section level only (20 sectors), not division
- Nationality split uses tier-based ranges, not empirical supply curves
- Nitaqat compliance is macro-sector level, not firm-level or salary-weighted
- All classifications are assumption-heavy in early deployment

## Test Coverage

58 tests across 9 test files:

| File | Tests | Coverage |
|------|-------|----------|
| test_workforce_schemas.py | 12 | Schema validation, all amendments |
| test_workforce_satellite.py | 7 | Full pipeline, provenance, no-target |
| test_occupation_decomposition.py | 6 | Step 2, missing bridge defaults |
| test_nationality_split.py | 7 | Step 3 ranges, negative jobs, custom tiers |
| test_compliance_check.py | 7 | Step 4 Nitaqat, all 5 states |
| test_confidence_propagation.py | 9 | Utility + pipeline confidence |
| test_integration.py | 3 | With SatelliteAccounts + LeontiefSolver |
| test_overrides.py | 4 | Knowledge Flywheel override path |
| conftest.py | — | Shared fixtures |

Total: 2573 tests (2515 existing + 58 new), 0 failures.
