# MVP-13: Data Quality Automation — Design Document

**Date:** 2026-02-28
**Status:** Approved
**Module:** `src/quality/`

## Purpose

Automate the answer to "How much should I trust this result?" by scoring 7 quality dimensions, computing a composite grade, and generating actionable warnings with calibrated severity levels.

This is **deterministic** — no LLM calls. Pure functions operating on typed inputs.

## Architecture

### Module Structure

```
src/quality/
├── __init__.py
├── models.py          # RunQualityAssessment, QualityWarning, DimensionAssessment, enums
├── config.py          # QualityScoringConfig with thresholds, weights, grade boundaries
├── scorer.py          # QualityScorer — 7 dimension scoring functions + composite
├── warnings.py        # WarningEngine — check functions → QualityWarning lists
├── source_registry.py # SourceFreshnessRegistry + DataSource model
├── plausibility.py    # PlausibilityChecker — multiplier range validation
├── nowcast.py         # NowcastingService — governed RAS workflow (draft/candidate)
└── service.py         # QualityAssessmentService — orchestrator
```

### Key Models

#### Enums

- `QualitySeverity(StrEnum)`: INFO, WARNING, CRITICAL, WAIVER_REQUIRED (Amendment 3)
- `QualityGrade(StrEnum)`: A, B, C, D, F (Amendment 12)
- `QualityDimension(StrEnum)`: VINTAGE, MAPPING, ASSUMPTIONS, CONSTRAINTS, WORKFORCE, PLAUSIBILITY, FRESHNESS
- `NowcastStatus(StrEnum)`: DRAFT, APPROVED, REJECTED (Amendment 8)
- `PlausibilityStatus(StrEnum)`: IN_RANGE, ABOVE_RANGE, BELOW_RANGE, NO_BENCHMARK
- `SourceUpdateFrequency(StrEnum)`: QUARTERLY, ANNUAL, BIENNIAL, TRIENNIAL, QUINQUENNIAL, PER_ENGAGEMENT

#### DimensionAssessment (Amendment 9)

```python
class DimensionAssessment(ImpactOSBase):
    dimension: QualityDimension
    score: float  # 0.0 - 1.0
    applicable: bool
    inputs_used: dict[str, object]  # provenance of what was scored
    rules_triggered: list[str]      # which scoring rules applied
    warnings: list[QualityWarning]  # dimension-specific warnings
```

#### QualityWarning

```python
class QualityWarning(ImpactOSBase):
    warning_id: UUIDv7
    dimension: QualityDimension
    severity: QualitySeverity
    message: str
    detail: str | None
    recommendation: str | None
```

#### RunQualityAssessment (Amendment 4, 5)

```python
class RunQualityAssessment(ImpactOSBase, frozen=True):
    assessment_id: UUIDv7
    assessment_version: int  # monotonic per run_id
    run_id: UUID | None      # None for pre-run assessments

    # Dimension scores
    dimension_assessments: list[DimensionAssessment]

    # Completeness (Amendment 1)
    applicable_dimensions: list[QualityDimension]
    assessed_dimensions: list[QualityDimension]
    missing_dimensions: list[QualityDimension]
    completeness_pct: float

    # Composite
    composite_score: float
    grade: QualityGrade  # capped by completeness

    # Warnings
    warnings: list[QualityWarning]
    waiver_required_count: int
    critical_count: int
    warning_count: int
    info_count: int

    # Metadata
    known_gaps: list[str]
    notes: str | None
    created_at: UTCTimestamp
```

### Scoring Engine

Each dimension scoring function is a **pure function** accepting typed inputs, not module references. This decouples scoring from infrastructure that may not exist yet.

#### Dimension 1: Model Vintage (`score_vintage`)
- Input: `base_year: int, current_year: int`
- Decay curve: 0-2yr → 1.0, 3-4yr → 0.7, 5-7yr → 0.4, 8+yr → 0.2
- Configurable thresholds in QualityScoringConfig

#### Dimension 2: Mapping Confidence (`score_mapping`)
- Input: `coverage_pct, confidence_dist: dict[str, float], residual_pct, unresolved_pct, unresolved_spend_pct`
- Weighted score of coverage, confidence distribution, and residual
- Materiality: spend-share thresholds (Amendment 10)

#### Dimension 3: Assumption Governance (`score_assumptions`)
- Input: `ranges_coverage_pct, approval_rate`
- Weighted: 50% ranges coverage + 50% approval rate

#### Dimension 4: Constraint Confidence (`score_constraints`)
- Input: `confidence_summary: dict[str, int] | None` (HARD/ESTIMATED/ASSUMED counts)
- Score = weighted average: HARD=1.0, ESTIMATED=0.6, ASSUMED=0.3
- None → not applicable

#### Dimension 5: Workforce Confidence (`score_workforce`)
- Input: `overall_confidence: str | None` (HIGH/MEDIUM/LOW)
- HIGH=1.0, MEDIUM=0.6, LOW=0.3
- None → not applicable

#### Dimension 6: Multiplier Plausibility (`score_plausibility`)
- Input: `multipliers_in_range_pct, flagged_count`
- Score = multipliers_in_range_pct / 100.0

#### Dimension 7: Source Freshness (`score_freshness`)
- Input: `source_ages: list[SourceAge]` (source_name, age_days, expected_frequency)
- Cadence-aware (Amendment 2): ratio = actual_age / expected_cadence_days
  - ratio ≤ 1.0 → 1.0
  - ratio ≤ 1.5 → 0.7
  - ratio ≤ 2.0 → 0.4
  - ratio > 2.0 → 0.2
- PER_ENGAGEMENT sources not time-scored
- Average across all time-scored sources

#### Composite Score
- Weighted average of applicable dimension scores
- Weights configurable (defaults: vintage=0.15, mapping=0.25, assumptions=0.15, constraints=0.10, workforce=0.10, plausibility=0.15, freshness=0.10)
- Grade thresholds: A≥0.85, B≥0.70, C≥0.55, D≥0.40, F<0.40
- Completeness cap (Amendment 1): if completeness < 50% → cap at C, if < 30% → cap at D

### Warning Engine

Each check function produces zero or more `QualityWarning` instances.

Warning checks:
1. **Vintage**: CRITICAL if 8+ years, WARNING if 5+ years
2. **Mapping coverage**: materiality-based (Amendment 10)
   - >5% unresolved spend → WAIVER_REQUIRED
   - >1% unresolved spend → CRITICAL
   - any unresolved but immaterial → WARNING
3. **Multiplier plausibility**: WARNING/CRITICAL per flagged sector count
4. **Source freshness**: WARNING/CRITICAL per stale source count
5. **Constraint confidence**: WARNING if >50% ASSUMED
6. **Assumption governance**: WARNING if ranges_coverage < 50%
7. **Nowcast labeling**: INFO if model is nowcast/balanced

### Source Freshness Registry

```python
class DataSource(ImpactOSBase):
    source_id: UUIDv7
    name: str
    source_type: str
    provider: str
    last_updated: UTCTimestamp
    last_checked: UTCTimestamp
    expected_update_frequency: SourceUpdateFrequency
    url: str | None
    notes: str | None
```

Seed sources: Saudi IO Table, KAPSARC Benchmarks, WDI, ILOSTAT, SAMA Inflation, Employment Coefficients, Occupation Bridge, Nationality Classifications.

### Multiplier Plausibility

```python
class PlausibilityChecker:
    check(B_matrix, sector_codes, benchmarks) → PlausibilityResult

class PlausibilityResult:
    multipliers_in_range_pct: float
    flagged_sectors: list[str]
    sector_details: list[SectorPlausibilityDetail]
```

Wraps future BenchmarkValidator. For now, accepts benchmark ranges as `dict[str, tuple[float, float]]`.

### Nowcasting Service (Amendment 8)

```python
class NowcastingService:
    create_nowcast(base_model, target_totals, provenance) → NowcastResult
    approve_nowcast(nowcast_id) → ModelVersion
    reject_nowcast(nowcast_id) → None

class NowcastResult:
    nowcast_id: UUIDv7
    candidate_model_version_id: UUID  # DRAFT, not published
    candidate_status: NowcastStatus
    base_model_version_id: UUID
    target_year: int
    converged: bool
    iterations: int
    final_error: float
    structural_change_magnitude: float
    target_provenance: list[TargetTotalProvenance]
    quality_warnings: list[QualityWarning]

class TargetTotalProvenance(ImpactOSBase):
    sector_code: str
    target_value: float
    source: str
    evidence_refs: list[str]
```

### Integration (Amendment 7)

Quality runs at the **orchestration layer**, not inside BatchRunner:
1. `SingleRunResult` gets optional `quality_assessment_id: UUID | None`
2. Orchestration code calls `QualityAssessmentService.assess()` after batch run
3. Export gate: advisory warning if `waiver_required_count > 0`

### Existing Infrastructure Reuse (Amendment 6)

- `src/observability/quality.py` QualityMetrics → inputs for mapping confidence distribution, sensitivity coverage
- `src/engine/ras.py` RASBalancer → wrapped by NowcastingService
- `src/engine/model_store.py` ModelStore → for nowcast candidate registration
- `src/models/common.py` enums → ConstraintConfidence, MappingConfidenceBand reused
- No new source registry duplication — `src/quality/source_registry.py` is the single registry

## Amendments Applied

| # | Amendment | Status |
|---|-----------|--------|
| 1 | Dimension applicability + completeness cap | ✅ Applied |
| 2 | Source-cadence-aware freshness scoring | ✅ Applied |
| 3 | WAIVER_REQUIRED replaces BLOCKER | ✅ Applied |
| 4 | Rename to RunQualityAssessment | ✅ Applied |
| 5 | Append-only versioned assessments | ✅ Applied |
| 6 | Extend existing source registry | ✅ Applied (new registry, no duplication) |
| 7 | Assessment above BatchRunner | ✅ Applied |
| 8 | Nowcasting draft/candidate | ✅ Applied |
| 9 | Per-dimension provenance | ✅ Applied |
| 10 | Materiality thresholds | ✅ Applied |
| 11 | Typed models for nested dicts | ✅ Applied (nice-to-have) |
| 12 | QualityGrade enum | ✅ Applied (nice-to-have) |
| 13 | Cache plausibility per model | ✅ Applied (nice-to-have) |
| 14 | Field(default_factory) for config weights | ✅ Applied (nice-to-have) |

## Constraints

- **Deterministic**: Zero LLM calls
- **Backward compatible**: 909 existing tests unaffected
- **Graceful degradation**: Missing dimensions scored as N/A, composite recalculated
- **Configurable**: All thresholds and weights in QualityScoringConfig
- **Python 3.11+**: Type hints, StrEnum, `X | None` syntax
