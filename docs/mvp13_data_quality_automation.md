# MVP-13: Data Quality Automation

## Overview

MVP-13 automates the answer to "How much should I trust this result?" by scoring 7 quality dimensions, computing a composite grade, and generating actionable warnings with calibrated severity levels.

All computation is **deterministic** — no LLM calls.

## Module Structure

```
src/quality/
├── __init__.py           # Package docstring
├── models.py             # Enums, QualityWarning, DimensionAssessment, RunQualityAssessment
├── config.py             # QualityScoringConfig with all thresholds and weights
├── scorer.py             # QualityScorer — 7 dimension scoring + composite
├── warnings.py           # WarningEngine — severity-based warning checks
├── source_registry.py    # SourceFreshnessRegistry + DataSource + seed defaults
├── plausibility.py       # PlausibilityChecker — multiplier range validation
├── nowcast.py            # NowcastingService — governed RAS workflow
└── service.py            # QualityAssessmentService — orchestrator
```

## Quality Dimensions

| # | Dimension | Input | Scoring Logic |
|---|-----------|-------|---------------|
| 1 | **Vintage** | base_year, current_year | Decay: 0-2yr→1.0, 3-4yr→0.7, 5-7yr→0.4, 8+yr→0.2 |
| 2 | **Mapping** | coverage, confidence dist, residual, spend | Weighted: 40% coverage + 30% HIGH confidence + 20% low residual + 10% resolved |
| 3 | **Assumptions** | ranges coverage, approval rate | 50/50 blend of sensitivity ranges and approval |
| 4 | **Constraints** | HARD/ESTIMATED/ASSUMED counts | Weighted: HARD=1.0, ESTIMATED=0.6, ASSUMED=0.3 |
| 5 | **Workforce** | overall confidence | HIGH=1.0, MEDIUM=0.6, LOW=0.3 |
| 6 | **Plausibility** | multipliers in range % | Direct percentage conversion |
| 7 | **Freshness** | source ages vs expected cadence | Cadence-aware ratio scoring |

## Composite Score and Grade

Weighted average of applicable dimensions (configurable weights, default sum to 1.0).

| Grade | Threshold |
|-------|-----------|
| A | ≥ 0.85 |
| B | ≥ 0.70 |
| C | ≥ 0.55 |
| D | ≥ 0.40 |
| F | < 0.40 |

**Completeness cap:** If fewer than 50% of dimensions are applicable, grade capped at C. If fewer than 30%, capped at D.

## Warning Severity Levels

| Severity | Meaning |
|----------|---------|
| INFO | Informational (e.g., model is a nowcast) |
| WARNING | Potential quality concern |
| CRITICAL | Significant quality issue |
| WAIVER_REQUIRED | Advisory block — requires explicit acknowledgment |

Quality warnings are **advisory**. The NFF governance gate remains the hard block for publication.

## Source Freshness Registry

Tracks 8 seed data sources with their expected update frequencies:

- Saudi IO Table (GASTAT, quinquennial)
- KAPSARC Multiplier Benchmarks (annual)
- World Development Indicators (World Bank, annual)
- ILOSTAT Employment Data (ILO, annual)
- SAMA Inflation Data (quarterly)
- Employment Coefficients D-4 (GOSI, annual)
- Occupation Bridge (expert, per engagement)
- Nationality Classifications (expert, per engagement)

Freshness scoring is cadence-aware: a 6-year-old IO table (5-year cadence) scores 0.7, not 0.2.

## Multiplier Plausibility

Validates Leontief output multipliers (B matrix diagonal) against benchmark ranges. Results cached per ModelVersion for efficiency.

## Governed Nowcasting

RAS matrix balancing wrapped with governance:
1. `create_nowcast()` → produces DRAFT candidate (not published)
2. `approve_nowcast()` → publishes to ModelStore
3. `reject_nowcast()` → marks as rejected

Each nowcast carries rich provenance per target total.

## Integration

Quality assessment runs at the **orchestration layer** above BatchRunner. `SingleRunResult` carries an optional `quality_assessment_id` linking to the assessment.

## Usage

```python
from src.quality.service import QualityAssessmentService

svc = QualityAssessmentService()
assessment = svc.assess(
    base_year=2024,
    current_year=2026,
    mapping_coverage_pct=0.95,
    mapping_confidence_dist={"HIGH": 0.7, "MEDIUM": 0.2, "LOW": 0.1},
    mapping_residual_pct=0.03,
    mapping_unresolved_pct=0.02,
    mapping_unresolved_spend_pct=0.5,
    assumption_ranges_coverage_pct=0.8,
    assumption_approval_rate=0.9,
    constraint_confidence_summary={"HARD": 8, "ESTIMATED": 2, "ASSUMED": 0},
    workforce_overall_confidence="HIGH",
    plausibility_in_range_pct=95.0,
    plausibility_flagged_count=1,
    source_ages=registry.to_source_ages(as_of=now),
    run_id=run_id,
)
print(f"Grade: {assessment.grade}, Score: {assessment.composite_score:.2f}")
```

## Amendments Applied

All 14 amendments (9 mandatory + 5 nice-to-have) implemented:

1. Dimension applicability + completeness cap
2. Source-cadence-aware freshness scoring
3. WAIVER_REQUIRED replaces BLOCKER
4. Renamed to RunQualityAssessment
5. Append-only versioned assessments
6. Single source registry (no duplication)
7. Assessment above BatchRunner
8. Nowcasting draft/candidate lifecycle
9. Per-dimension provenance (DimensionAssessment)
10. Materiality thresholds for mapping warnings
11. Typed models (nice-to-have)
12. QualityGrade enum (nice-to-have)
13. Plausibility cache per model (nice-to-have)
14. Field(default_factory) for config (nice-to-have)

## Test Coverage

249+ new tests across 9 test files covering all components, edge cases, and end-to-end flows.
