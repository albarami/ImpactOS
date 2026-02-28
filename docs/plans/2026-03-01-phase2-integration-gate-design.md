# MVP-14: Phase 2 Integration + Gate — Design Document

**Date:** 2026-03-01
**Status:** Approved
**Module:** `tests/integration/` + `scripts/`

## Purpose

Prove that all Phase 2 modules work together as an integrated system. MVP-14 produces NO new product modules — it produces tests, regression baselines, and a formal gate report.

## Existing State

### Modules Under Integration

| Module | Location | API Entry Point |
|--------|----------|-----------------|
| D-1 IO Model | `src/data/io_loader.py` | `load_from_json() -> IOModelData` |
| D-2 Taxonomy + Concordance | `src/data/concordance.py` | `ConcordanceService(path, weights_path)` |
| D-2 SG Template Parser | `src/data/sg_template_parser.py` | `SGTemplateParser(concordance).parse()` |
| D-3 Benchmark Validator | `src/data/benchmark_validator.py` | `BenchmarkValidator.validate_multipliers()` |
| D-3 Real IO Loader | `src/data/real_io_loader.py` | `load_real_saudi_io() -> IOModelData` |
| D-4 Workforce Data | `src/data/workforce/` | `OccupationBridge`, `NationalityClassificationSet`, `MacroSaudizationTargets` |
| Core: Leontief | `src/engine/leontief.py` | `LeontiefSolver.solve(model, delta_d) -> SolveResult` |
| Core: Satellite | `src/engine/satellites.py` | `SatelliteAccounts.compute(delta_x, coefficients) -> SatelliteResult` |
| Core: ModelStore | `src/engine/model_store.py` | `ModelStore.register(...) -> ModelVersion` |
| Core: BatchRunner | `src/engine/batch.py` | `BatchRunner.run(request) -> BatchResult` |
| Core: RAS | `src/engine/ras.py` | `RASBalancer.balance() -> RASResult` |
| MVP-8: Compiler | `src/compiler/scenario_compiler.py` | `ScenarioCompiler.compile(CompilationInput) -> ScenarioSpec` |
| MVP-9: Depth Engine | `src/agents/depth/orchestrator.py` | `DepthOrchestrator.run(plan_id, ...)` (async, uses LLM) |
| MVP-10: Constraints | `src/engine/constraints/solver.py` | `FeasibilitySolver.solve(...) -> FeasibilityResult` |
| MVP-11: Workforce | `src/engine/workforce_satellite/satellite.py` | `WorkforceSatellite.analyze(...) -> WorkforceResult` |
| MVP-12: Flywheel | `src/flywheel/publication.py` | `FlywheelPublicationService.publish_new_cycle(...)` |
| MVP-12: Learning | `src/compiler/learning.py` | `LearningLoop.record_override(...)` |
| MVP-13: Quality | `src/quality/service.py` | `QualityAssessmentService.assess(...)` |
| Governance | `src/governance/publication_gate.py` | `PublicationGate.check(claims) -> GateResult` |
| Export | `src/export/orchestrator.py` | `ExportOrchestrator.execute(request, claims) -> ExportRecord` |

### Existing Integration Tests (134 tests)

The xenodochial merge brought API-level integration tests in `tests/integration/`:

- `test_full_pipeline.py` — Register → Run → Feasibility → Workforce → Quality → Export (via HTTP)
- `test_phase2_gate.py` — Phase 2 gate checks via API
- `test_depth_engine.py` — Depth engine plan creation + disclosure tiers
- `test_governance_chain.py` — Governance chain via API
- `test_learning_flywheel.py` — Learning loop + publish cycle via API
- `test_model_cache_fallback.py` — Model cache/fallback
- `test_persistence_audit.py` — Persistence + audit trail

**These test the HTTP API layer.** MVP-14 tests the **Python module layer** directly.

## Architecture

### Testing Strategy: Direct Module Integration

MVP-14 tests call Python classes directly (not via HTTP). This:
- Catches contract violations that serialization may mask
- Runs faster (no HTTP round-trips)
- Produces clearer stack traces for debugging
- Complements existing API-level tests

### Integration Paths

```
Path 1: Core Engine
  IOModelData → ModelStore.register → LoadedModel →
  LeontiefSolver.solve → SolveResult (delta_x) →
  SatelliteAccounts.compute → SatelliteResult →
  FeasibilitySolver.solve → FeasibilityResult

Path 2: Compiler → Engine
  BoQ line items + MappingDecisions →
  ScenarioCompiler.compile → ScenarioSpec →
  Extract delta_d → LeontiefSolver.solve

Path 3: Engine → Workforce
  SatelliteResult (delta_jobs) →
  WorkforceSatellite.analyze → WorkforceResult
  (occupation decomposition → nationality splits → Nitaqat)

Path 4: Depth Engine (upstream, Amendment 2)
  DepthOrchestrator.run → DepthPlan + artifacts
  (produces suite plans; does NOT consume engine results as primary mode)
  Mock LLM for deterministic testing.

Path 5: Flywheel Learning Loop
  Analyst override → LearningLoop.record_override →
  extract_new_patterns → MappingLibraryManager.build_draft →
  FlywheelPublicationService.publish_new_cycle → new versions

Path 6: Quality Assessment
  Module signals (mapping confidence, constraint summary,
  workforce confidence, source ages, plausibility) →
  QualityAssessmentService.assess → RunQualityAssessment

Path 7: Doc → Export (Amendment 3)
  Pre-extracted BoQ → ScenarioCompiler → Engine → Constraints →
  Workforce → Quality → PublicationGate.check → ExportOrchestrator.execute
```

### File Structure

```
tests/integration/
├── conftest.py                      # Extended with module-level fixtures
├── golden_scenarios/
│   ├── __init__.py
│   ├── industrial_zone.py           # Golden Scenario 1: full happy path
│   ├── mega_project_gaps.py         # Golden Scenario 2: data gaps
│   ├── contraction.py               # Golden Scenario 3: negative shocks
│   └── snapshots/                   # Toleranced JSON golden values
│       ├── industrial_zone_outputs.json
│       ├── mega_project_gaps_outputs.json
│       └── contraction_outputs.json
├── test_path_engine.py              # Path 1: Leontief → Satellite → Constraints
├── test_path_compiler_engine.py     # Path 2: Compiler → Engine
├── test_path_workforce.py           # Path 3: Engine → Workforce
├── test_path_depth.py               # Path 4: Depth Engine (Amendment 2)
├── test_path_flywheel.py            # Path 5: Flywheel learning loop
├── test_path_quality.py             # Path 6: Quality assessment
├── test_path_doc_to_export.py       # Path 7: Doc → Export (Amendment 3)
├── test_e2e_golden.py               # End-to-end golden tests
├── test_mathematical_accuracy.py    # Algebraic verification
├── test_performance.py              # Performance benchmarks (Amendment 6)
├── test_phase2_gate_formal.py       # Formal gate criteria (Amendment 4)
├── test_regression.py               # Toleranced snapshots (Amendment 7)
├── test_api_schema.py               # Pydantic serialization
├── test_cross_module_consistency.py  # Shared vocabulary (Amendment 8)
│
├── # Existing files (untouched):
├── test_full_pipeline.py
├── test_phase2_gate.py
├── test_depth_engine.py
├── test_governance_chain.py
├── test_learning_flywheel.py
├── test_model_cache_fallback.py
└── test_persistence_audit.py

scripts/
└── generate_phase2_gate_report.py   # Gate report generator (Amendment 1)

docs/
├── mvp14_phase2_integration_gate.md # Technical documentation
└── phase2_gate_report.md            # Formal gate report
```

## Golden Test Scenarios

### Scenario 1: Industrial Zone CAPEX (Full Happy Path)

A small but complete IO model with known, hand-verified values.

- **IO Model:** 3-sector synthetic model (Construction, Manufacturing, Services)
  - Z matrix, x vector, sector codes — small enough for hand calculation
  - Known A matrix coefficients, known B = (I-A)^-1
- **BoQ:** 15-20 line items across 3 sectors with HIGH confidence mappings
- **Phasing:** 3-year CAPEX schedule (40%/35%/25%)
- **Constraints:** Capacity + labor constraints, at least one binding
- **Workforce:** Full occupation bridge, nationality classifications
- **Expected outputs:** Hand-verified delta_x, GDP, employment, binding constraints
- **Quality:** Grade A or B (all data present, recent model)
- **Tolerances:** rtol=1e-6 for floats, abs=10 for jobs

### Scenario 2: Mega-Project with Data Gaps

Same 3-sector model but with intentional gaps:
- Model vintage: 6+ years old → vintage WARNING
- Some LOW confidence mappings → mapping WARNING
- No occupation bridge for 1 sector → workforce null with caveats
- Constraints mostly ASSUMED → constraint WARNING
- Expected quality grade: C or D (not A!)

### Scenario 3: Contraction Scenario

Negative demand shocks through the full pipeline:
- Negative delta_d → negative delta_x → negative jobs
- Nationality min/mid/max must stay in numeric order (Amendment 3 of MVP-11)
- No binding capacity constraints (contraction doesn't hit capacity)
- Quality assessment handles negative impacts correctly

### Golden Snapshot Format (Amendment 7)

```json
{
  "scenario": "industrial_zone",
  "computed_at": "2026-03-01T00:00:00Z",
  "tolerances": {"rtol": 1e-6, "employment_atol": 10, "gdp_rtol": 0.01},
  "total_output_impact": 1234.567,
  "gdp_impact": 456.789,
  "employment_total": 150,
  "sector_outputs": {"Construction": 500.0, "Manufacturing": 400.0, "Services": 334.567},
  "binding_constraints": ["labor_construction"],
  "quality_grade": "B"
}
```

Compared with `numpy.testing.assert_allclose` and `pytest.approx`, not hash-based.

## Compiler Gate Metric (Amendment 4)

The labeled BoQ fixture defines ground-truth sector mappings:

```python
LABELED_BOQ = [
    {"text": "reinforced concrete foundation", "ground_truth_sector": "Construction", "value": 5_000_000},
    {"text": "structural steel supply", "ground_truth_sector": "Manufacturing", "value": 3_000_000},
    # ... 30 items total
]
```

Gate metric:
- **Auto-suggestion coverage:** % of items where compiler proposes a mapping
- **Accuracy:** % of auto-mapped items matching ground truth
- **Threshold:** >= 60% coverage with >= 80% accuracy on suggested items
- Denominator: line item count (not spend-weighted)

## Mathematical Accuracy Tests

Small 2-3 sector matrices where hand calculation is feasible:
1. Leontief identity: x = A.x + d → delta_x = B.delta_d
2. Output multiplier = column sum of B
3. GDP = value_added_coefficients . delta_x
4. Employment = employment_coefficients . delta_x
5. Feasibility: feasible_delta_x <= unconstrained_delta_x per sector
6. IO accounting identity: row sums of Z + final demand = gross output
7. Import leakage: higher import share → lower domestic multiplier
8. Numerical stability: 10 serial computations, drift < 1e-10

## Performance Benchmarks (Amendment 6)

Marked `@pytest.mark.performance` and `@pytest.mark.slow`. Skipped by default.

Reference measurements (not hard gates):
- Single scenario: < 2s (20-sector)
- Batch 10 scenarios: < 10s
- Batch 50 scenarios: < 60s
- Full pipeline (all modules): < 5s per scenario
- Quality assessment: < 1s
- Flywheel publish cycle: < 2s

Gate report includes measured times as informational, not as pass/fail criteria.

## Phase 2 Gate Criteria

From tech spec Section 15.5.2, verified programmatically:

| # | Criterion | Evidence |
|---|-----------|----------|
| 1 | Compiler >= 60% auto-mapping (Amendment 4) | Labeled BoQ fixture |
| 2 | Feasibility dual-output with diagnostics | FeasibilityResult assertions |
| 3 | Workforce confidence-labeled splits with ranges | WorkforceResult assertions |
| 4 | Full pipeline completes | Golden Scenario 1 end-to-end |
| 5 | Flywheel captures learning | Override → publish cycle test |
| 6 | Quality assessment produced | RunQualityAssessment assertions |

Performance results reported separately (Amendment 6).

## Concordance Tests (Amendment 8)

The sector code consistency test accounts for the actual hierarchy:
- D-1: 20 sections
- D-2: 84 divisions
- Compiler/SG parser: may work at division-level
- Workforce bridge: section-level

Tests verify concordance contracts, not code equality:
- Every D-1 section has at least one D-2 division mapping
- No orphan codes in compiler output
- Division-level results aggregate to section-level within tolerance
- Bidirectional concordance consistency

## RunSnapshot Fields (Amendment 10)

Verify existing fields only. RunSnapshot already has:
- `model_version_id`, `taxonomy_version_id`, `concordance_version_id`
- `mapping_library_version_id`, `assumption_library_version_id`
- `constraint_set_version_id` (optional)
- `occupation_bridge_version_id`, `nationality_classification_version_id` (optional)
- `nitaqat_target_version_id` (optional)

Do NOT add new fields. Log any missing fields as Phase 3 enhancement.

## Depth Engine Tests (Amendment 2)

Depth Engine is primarily UPSTREAM — produces structured reasoning artifacts.

Tests verify:
- DepthOrchestrator produces valid plan + artifacts (mocked LLM)
- Artifacts preserve disclosure tiers
- Suite plans can be transformed into executable scenarios
- Depth outputs do NOT mutate deterministic engine results
- If post-run interpretive mode exists, test that too (secondary)

LLM calls are mocked with deterministic responses for reproducibility.

## Gate Report (Amendment 1)

`scripts/generate_phase2_gate_report.py` reads pytest JSON output and produces:

```python
@dataclass
class GateResult:
    gate_passed: bool
    criteria_results: list[GateCriterionResult]
    total_tests: int
    total_failures: int
    performance_results: list[PerformanceMetric]  # Informational only
    summary: str
    timestamp: str
```

Performance metrics are informational, not part of `gate_passed` logic.

## Pytest Markers (Amendment 12)

Added to `pyproject.toml`:

```
markers = [
    "benchmark: performance benchmark tests",
    "integration: Integration tests across module boundaries",
    "golden: Golden scenario end-to-end tests",
    "performance: Performance benchmark tests (skip in CI by default)",
    "slow: Tests that take >5s",
    "regression: Regression baseline tests",
    "gate: Phase 2 gate criteria verification",
    "real_data: Tests using sanitized real data fixtures",
]
```

## Constraints

- Zero new product modules in `src/` (except utility scripts in `scripts/`)
- All ~3,049 existing tests continue passing
- Deterministic: no LLM calls (mock DepthOrchestrator's LLM client)
- Numerical tolerances explicit and documented
- Golden baselines frozen once computed
- Python 3.11+, type hints, docstrings
- Minimum 80+ new integration tests
- Fix wiring bugs found during integration (backward compatible)

## Amendments Applied

| # | Amendment | Status |
|---|-----------|--------|
| 1 | Gate report not in src/ | Applied: `scripts/generate_phase2_gate_report.py` |
| 2 | Depth Engine upstream direction | Applied: tests verify artifact production, not result consumption |
| 3 | Doc → Export path added | Applied: `test_path_doc_to_export.py` |
| 4 | Compiler gate metric precision | Applied: labeled BoQ fixture with ground-truth mappings |
| 5 | One sanitized real-data fixture | Applied: D-1/D-3 real IO model + sanitized BoQ, marked `@pytest.mark.real_data` |
| 6 | Performance = reference, not gate | Applied: `@pytest.mark.slow`, skip by default, informational in report |
| 7 | Toleranced snapshots, not hashes | Applied: JSON snapshots + `assert_allclose` |
| 8 | Concordance contracts, not code equality | Applied: bidirectional concordance tests |
| 9 | Normalize file paths | Applied: verified all paths against actual repo |
| 10 | Verify RunSnapshot fields, don't expand | Applied: assert existing fields only |
| 11 | Shared fixture layer | Applied: extended `conftest.py` with module-level fixtures |
| 12 | Pytest markers | Applied: 7 markers registered in `pyproject.toml` |
