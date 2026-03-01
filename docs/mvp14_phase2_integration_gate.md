# MVP-14: Phase 2 Integration + Gate

## Overview

MVP-14 is the final sprint of Phase 2. It produces NO new modules — only integration tests, regression baselines, and a formal gate report proving all Phase 2 modules work together end-to-end.

## Integration Paths Tested

| # | Path | Test File |
|---|------|-----------|
| 1 | Core Engine: Leontief -> Satellite -> Constraints | `test_path_engine.py` |
| 2 | Compiler -> Engine: BoQ -> mapping -> shock -> solve | `test_path_compiler_engine.py` |
| 3 | Engine -> Workforce: delta_jobs -> occupation splits | `test_path_workforce.py` |
| 4 | Quality Assessment: signals -> grade -> warnings | `test_path_quality.py` |
| 5 | Flywheel: override -> patterns -> draft -> publish | `test_path_flywheel.py` |
| 6 | Doc-to-Export: ingestion -> compile -> export | `test_path_doc_to_export.py` |
| 7 | SG Concordance: ISIC -> division mapping | `test_path_sg_concordance.py` |
| 8 | Benchmark Validator: multiplier plausibility | `test_path_benchmark.py` |
| 9 | Depth Engine: mocked LLM -> disclosure tiers | `test_path_depth.py` |

## Golden Scenarios

| # | Scenario | Delta D | Model |
|---|----------|---------|-------|
| 1 | Industrial Zone | [300, 150, 50] | 3-sector F/C/G |
| 2 | Mega Project (Data Gaps) | [200, 100, 100] base_year=2018 | 3-sector F/C/G |
| 3 | Contraction | [-100, -50, -30] | 3-sector F/C/G |

### Tolerances

| Constant | Value | Usage |
|----------|-------|-------|
| `NUMERIC_RTOL` | 1e-6 | General numerical comparison |
| `EMPLOYMENT_ATOL` | 10 | Employment absolute tolerance |
| `GDP_RTOL` | 0.01 | GDP impact relative tolerance |
| `OUTPUT_RTOL` | 0.01 | Total output relative tolerance |

## Gate Criteria (Tech Spec Section 15.5.2)

| # | Criterion | Test Class |
|---|-----------|------------|
| 1 | Compiler >= 60% auto-mapping rate | `TestCompilerAutoMapping` |
| 2 | Feasibility produces dual-output with diagnostics | `TestFeasibilityDualOutput` |
| 3 | Workforce confidence-labeled splits with ranges | `TestWorkforceConfidenceLabeled` |
| 4 | Full pipeline completes end-to-end | `TestGoldenScenario1EndToEnd` |
| 5 | Flywheel captures learning + publish cycle | `TestFlywheelLearning` |
| 6 | Quality assessment produced with actionable warnings | `TestQualityAssessment` |

## Running Tests

```bash
# All integration tests (excludes @slow)
python -m pytest tests/integration/ -v -m "not slow"

# Golden scenario tests only
python -m pytest tests/integration/ -v -m golden

# Gate criteria tests only
python -m pytest tests/integration/ -v -m gate

# Performance benchmarks (reference only)
python -m pytest tests/integration/ -v -m performance

# Regression suite
python -m pytest tests/integration/test_regression.py -v

# Mathematical accuracy
python -m pytest tests/integration/test_mathematical_accuracy.py -v
```

## Updating Golden Snapshots

Golden snapshots are frozen JSON files in `tests/integration/golden_scenarios/snapshots/`. They are NEVER auto-recomputed.

```bash
# Update all golden snapshots
python -m pytest tests/integration/test_e2e_golden.py --update-golden -v

# Verify frozen comparison works
python -m pytest tests/integration/test_e2e_golden.py -v

# Review and commit updated snapshots
git diff tests/integration/golden_scenarios/snapshots/
git add tests/integration/golden_scenarios/snapshots/
git commit -m "Update golden snapshots after [reason]"
```

## Confidence Vocabulary

Five confidence enums exist across the codebase:

| # | Enum | Values | Module |
|---|------|--------|--------|
| 1 | `ConstraintConfidence` | HARD / ESTIMATED / ASSUMED | `src/models/common.py` |
| 2 | `MappingConfidenceBand` | HIGH / MEDIUM / LOW | `src/models/common.py` |
| 3 | `WorkforceConfidenceLevel` | HIGH / MEDIUM / LOW | `src/models/workforce.py` |
| 4 | `QualityConfidence` | high / medium / low (lowercase) | `src/data/workforce/unit_registry.py` |
| 5 | `ConfidenceBand` | HIGH / MEDIUM / LOW | `src/compiler/confidence.py` |

**Normalization:** `confidence_to_str()` in `src/engine/workforce_satellite/config.py` converts any confidence value to uppercase string.

## Generating the Gate Report

```bash
# Install pytest-json-report if needed
pip install pytest-json-report

# Generate JSON test results
python -m pytest tests/integration/ --json-report --json-report-file=report.json -m "not slow"

# Generate markdown gate report
python scripts/generate_phase2_gate_report.py report.json

# View report
cat docs/phase2_gate_report.md
```

## Conventions

- `shared.py` holds constants and helpers; `conftest.py` holds ONLY `@pytest.fixture` definitions
- All test files import from `tests.integration.golden_scenarios.shared`, NEVER from conftest
- The 3-sector toy model (ISIC F/C/G) is used for golden scenarios and mathematical accuracy
- Real 20-sector model accessed via `load_real_saudi_io()` for smoke tests and benchmarks
- All tests are deterministic — Depth Engine LLM is mocked
