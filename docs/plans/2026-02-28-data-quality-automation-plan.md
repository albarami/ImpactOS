# MVP-13: Data Quality Automation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automate quality assessment across 7 dimensions with composite scoring, configurable thresholds, and actionable warnings.

**Architecture:** New `src/quality/` module with pure scoring functions accepting typed inputs. Quality runs at orchestration layer above BatchRunner. All deterministic, no LLM calls.

**Tech Stack:** Python 3.11+, Pydantic v2, NumPy, pytest

**Design doc:** `docs/plans/2026-02-28-data-quality-automation-design.md`

---

### Task 0: Create worktree and module skeleton

**Files:**
- Create: `src/quality/__init__.py`
- Create: `tests/quality/__init__.py`

**Step 1:** Create git worktree branch

```bash
cd C:/Projects/ImpactOS
git worktree add .claude/worktrees/mvp13-quality -b mvp13-data-quality-automation
```

**Step 2:** Create module directories

```bash
mkdir -p src/quality tests/quality
```

**Step 3:** Create init files

`src/quality/__init__.py`:
```python
"""Data Quality Automation (MVP-13).

Automated quality assessment across 7 dimensions with composite scoring,
configurable thresholds, and actionable warnings.

Deterministic — no LLM calls.
"""
```

`tests/quality/__init__.py`: empty file

**Step 4:** Commit

```bash
git add src/quality/__init__.py tests/quality/__init__.py
git commit -m "[quality] Task 0: create module skeleton"
```

---

### Task 1: Quality enums and config models

**Files:**
- Create: `src/quality/models.py`
- Create: `src/quality/config.py`
- Test: `tests/quality/test_models.py`
- Test: `tests/quality/test_config.py`

**Step 1: Write failing tests for enums**

`tests/quality/test_models.py`:
```python
"""Tests for quality enums and models (MVP-13 Task 1)."""
from __future__ import annotations
import pytest
from src.quality.models import (
    QualitySeverity,
    QualityGrade,
    QualityDimension,
    NowcastStatus,
    PlausibilityStatus,
    SourceUpdateFrequency,
)


class TestQualitySeverity:
    def test_members(self) -> None:
        assert set(QualitySeverity) == {
            QualitySeverity.INFO,
            QualitySeverity.WARNING,
            QualitySeverity.CRITICAL,
            QualitySeverity.WAIVER_REQUIRED,
        }

    def test_is_str(self) -> None:
        for m in QualitySeverity:
            assert isinstance(m, str)


class TestQualityGrade:
    def test_members(self) -> None:
        assert set(QualityGrade) == {
            QualityGrade.A, QualityGrade.B, QualityGrade.C,
            QualityGrade.D, QualityGrade.F,
        }


class TestQualityDimension:
    def test_seven_dimensions(self) -> None:
        assert len(QualityDimension) == 7

    def test_members(self) -> None:
        expected = {"VINTAGE", "MAPPING", "ASSUMPTIONS", "CONSTRAINTS",
                    "WORKFORCE", "PLAUSIBILITY", "FRESHNESS"}
        assert {d.value for d in QualityDimension} == expected


class TestNowcastStatus:
    def test_members(self) -> None:
        assert set(NowcastStatus) == {
            NowcastStatus.DRAFT, NowcastStatus.APPROVED, NowcastStatus.REJECTED,
        }


class TestPlausibilityStatus:
    def test_members(self) -> None:
        assert set(PlausibilityStatus) == {
            PlausibilityStatus.IN_RANGE,
            PlausibilityStatus.ABOVE_RANGE,
            PlausibilityStatus.BELOW_RANGE,
            PlausibilityStatus.NO_BENCHMARK,
        }


class TestSourceUpdateFrequency:
    def test_members(self) -> None:
        expected = {"QUARTERLY", "ANNUAL", "BIENNIAL", "TRIENNIAL",
                    "QUINQUENNIAL", "PER_ENGAGEMENT"}
        assert {f.value for f in SourceUpdateFrequency} == expected
```

**Step 2:** Run tests, verify FAIL (import errors)

```bash
pytest tests/quality/test_models.py -v
```

**Step 3: Implement enums in `src/quality/models.py`**

Create all 6 StrEnums plus QualityWarning, DimensionAssessment, RunQualityAssessment Pydantic models. See design doc for field definitions.

Key points:
- `QualityWarning(ImpactOSBase)` with warning_id, dimension, severity, message, detail, recommendation
- `DimensionAssessment(ImpactOSBase)` with dimension, score, applicable, inputs_used, rules_triggered, warnings (Amendment 9)
- `RunQualityAssessment(ImpactOSBase, frozen=True)` with assessment_id, assessment_version, run_id, dimension_assessments, applicable/assessed/missing dimensions, completeness_pct, composite_score, grade, warnings with severity counts, known_gaps, notes, created_at (Amendments 1, 4, 5)
- `SourceAge` dataclass with source_name, age_days, expected_frequency

**Step 4: Write failing tests for config**

`tests/quality/test_config.py`:
```python
"""Tests for quality scoring config (MVP-13 Task 1)."""
from src.quality.config import QualityScoringConfig


class TestQualityScoringConfig:
    def test_default_weights_sum_to_one(self) -> None:
        cfg = QualityScoringConfig()
        total = sum(cfg.dimension_weights.values())
        assert abs(total - 1.0) < 1e-9

    def test_default_grade_thresholds(self) -> None:
        cfg = QualityScoringConfig()
        assert cfg.grade_thresholds["A"] == 0.85
        assert cfg.grade_thresholds["B"] == 0.70
        assert cfg.grade_thresholds["C"] == 0.55
        assert cfg.grade_thresholds["D"] == 0.40

    def test_default_vintage_thresholds(self) -> None:
        cfg = QualityScoringConfig()
        assert len(cfg.vintage_thresholds) == 4

    def test_default_freshness_ratios(self) -> None:
        cfg = QualityScoringConfig()
        assert len(cfg.freshness_ratio_thresholds) == 4

    def test_custom_weights(self) -> None:
        cfg = QualityScoringConfig(
            dimension_weights={"VINTAGE": 0.5, "MAPPING": 0.5,
                "ASSUMPTIONS": 0.0, "CONSTRAINTS": 0.0,
                "WORKFORCE": 0.0, "PLAUSIBILITY": 0.0, "FRESHNESS": 0.0}
        )
        assert cfg.dimension_weights["VINTAGE"] == 0.5
```

**Step 5: Implement config**

`src/quality/config.py`: QualityScoringConfig(ImpactOSBase) with:
- `dimension_weights: dict[str, float]` (default_factory, Amendment 14)
- `grade_thresholds: dict[str, float]` — A/B/C/D boundaries
- `vintage_thresholds: list[tuple[int, float]]` — [(2, 1.0), (4, 0.7), (7, 0.4), (99, 0.2)]
- `freshness_ratio_thresholds: list[tuple[float, float]]` — [(1.0, 1.0), (1.5, 0.7), (2.0, 0.4), (99, 0.2)]
- `completeness_cap_50: str` = "C" — grade cap if completeness < 50%
- `completeness_cap_30: str` = "D" — grade cap if completeness < 30%
- `mapping_spend_waiver_pct: float` = 5.0
- `mapping_spend_critical_pct: float` = 1.0

**Step 6:** Run all tests, verify PASS

```bash
pytest tests/quality/ -v
```

**Step 7:** Commit

```bash
git add src/quality/models.py src/quality/config.py tests/quality/test_models.py tests/quality/test_config.py
git commit -m "[quality] Task 1: quality enums, models, and config"
```

---

### Task 2: Quality scoring engine — vintage, mapping, assumptions

**Files:**
- Create: `src/quality/scorer.py`
- Test: `tests/quality/test_scorer.py`

**Step 1: Write failing tests for first 3 dimensions**

```python
"""Tests for quality scorer (MVP-13 Task 2)."""
import pytest
from src.quality.scorer import QualityScorer
from src.quality.config import QualityScoringConfig
from src.quality.models import QualityDimension


class TestScoreVintage:
    def test_current_year(self) -> None:
        scorer = QualityScorer()
        da = scorer.score_vintage(base_year=2026, current_year=2026)
        assert da.score == 1.0
        assert da.dimension == QualityDimension.VINTAGE

    def test_two_year_old(self) -> None:
        da = QualityScorer().score_vintage(base_year=2024, current_year=2026)
        assert da.score == 1.0

    def test_four_year_old(self) -> None:
        da = QualityScorer().score_vintage(base_year=2022, current_year=2026)
        assert da.score == 0.7

    def test_seven_year_old(self) -> None:
        da = QualityScorer().score_vintage(base_year=2019, current_year=2026)
        assert da.score == 0.4

    def test_ten_year_old(self) -> None:
        da = QualityScorer().score_vintage(base_year=2016, current_year=2026)
        assert da.score == 0.2

    def test_provenance(self) -> None:
        da = QualityScorer().score_vintage(base_year=2024, current_year=2026)
        assert da.inputs_used["base_year"] == 2024
        assert da.inputs_used["current_year"] == 2026
        assert da.applicable is True


class TestScoreMapping:
    def test_perfect_mapping(self) -> None:
        da = QualityScorer().score_mapping(
            coverage_pct=1.0,
            confidence_dist={"HIGH": 1.0, "MEDIUM": 0.0, "LOW": 0.0},
            residual_pct=0.0,
            unresolved_pct=0.0,
            unresolved_spend_pct=0.0,
        )
        assert da.score == pytest.approx(1.0)

    def test_low_coverage(self) -> None:
        da = QualityScorer().score_mapping(
            coverage_pct=0.5,
            confidence_dist={"HIGH": 0.5, "MEDIUM": 0.3, "LOW": 0.2},
            residual_pct=0.1,
            unresolved_pct=0.1,
            unresolved_spend_pct=0.02,
        )
        assert 0.0 < da.score < 0.8

    def test_materiality_warning(self) -> None:
        da = QualityScorer().score_mapping(
            coverage_pct=0.8,
            confidence_dist={"HIGH": 0.5, "MEDIUM": 0.3, "LOW": 0.2},
            residual_pct=0.05,
            unresolved_pct=0.1,
            unresolved_spend_pct=6.0,
        )
        severities = [w.severity for w in da.warnings]
        assert "WAIVER_REQUIRED" in [s.value for s in severities]


class TestScoreAssumptions:
    def test_perfect(self) -> None:
        da = QualityScorer().score_assumptions(
            ranges_coverage_pct=1.0, approval_rate=1.0,
        )
        assert da.score == pytest.approx(1.0)

    def test_partial(self) -> None:
        da = QualityScorer().score_assumptions(
            ranges_coverage_pct=0.6, approval_rate=0.8,
        )
        assert da.score == pytest.approx(0.7)

    def test_zero(self) -> None:
        da = QualityScorer().score_assumptions(
            ranges_coverage_pct=0.0, approval_rate=0.0,
        )
        assert da.score == pytest.approx(0.0)
```

**Step 2:** Run tests, verify FAIL

**Step 3: Implement QualityScorer** with `score_vintage`, `score_mapping`, `score_assumptions`. Each returns DimensionAssessment with provenance (inputs_used, rules_triggered). Use config thresholds.

**Step 4:** Run tests, verify PASS

**Step 5:** Commit

```bash
git commit -m "[quality] Task 2: scorer — vintage, mapping, assumptions dimensions"
```

---

### Task 3: Quality scoring engine — constraints, workforce, plausibility, freshness

**Files:**
- Modify: `src/quality/scorer.py`
- Modify: `tests/quality/test_scorer.py`

**Step 1: Write failing tests for remaining 4 dimensions**

```python
class TestScoreConstraints:
    def test_all_hard(self) -> None:
        da = QualityScorer().score_constraints({"HARD": 10, "ESTIMATED": 0, "ASSUMED": 0})
        assert da.score == pytest.approx(1.0)

    def test_mixed(self) -> None:
        da = QualityScorer().score_constraints({"HARD": 5, "ESTIMATED": 3, "ASSUMED": 2})
        assert 0.5 < da.score < 1.0

    def test_none_not_applicable(self) -> None:
        da = QualityScorer().score_constraints(None)
        assert da.applicable is False


class TestScoreWorkforce:
    def test_high(self) -> None:
        da = QualityScorer().score_workforce("HIGH")
        assert da.score == 1.0

    def test_medium(self) -> None:
        da = QualityScorer().score_workforce("MEDIUM")
        assert da.score == 0.6

    def test_low(self) -> None:
        da = QualityScorer().score_workforce("LOW")
        assert da.score == 0.3

    def test_none_not_applicable(self) -> None:
        da = QualityScorer().score_workforce(None)
        assert da.applicable is False


class TestScorePlausibility:
    def test_all_in_range(self) -> None:
        da = QualityScorer().score_plausibility(100.0, 0)
        assert da.score == pytest.approx(1.0)

    def test_partial(self) -> None:
        da = QualityScorer().score_plausibility(75.0, 5)
        assert da.score == pytest.approx(0.75)


class TestScoreFreshness:
    def test_all_fresh(self) -> None:
        from src.quality.models import SourceAge, SourceUpdateFrequency
        ages = [
            SourceAge(source_name="IO Table", age_days=365, expected_frequency=SourceUpdateFrequency.ANNUAL),
        ]
        da = QualityScorer().score_freshness(ages)
        assert da.score == pytest.approx(1.0)

    def test_stale_source(self) -> None:
        from src.quality.models import SourceAge, SourceUpdateFrequency
        ages = [
            SourceAge(source_name="IO Table", age_days=2000, expected_frequency=SourceUpdateFrequency.ANNUAL),
        ]
        da = QualityScorer().score_freshness(ages)
        assert da.score == pytest.approx(0.2)

    def test_per_engagement_excluded(self) -> None:
        from src.quality.models import SourceAge, SourceUpdateFrequency
        ages = [
            SourceAge(source_name="Bridge", age_days=9999, expected_frequency=SourceUpdateFrequency.PER_ENGAGEMENT),
        ]
        da = QualityScorer().score_freshness(ages)
        # PER_ENGAGEMENT excluded from time scoring — no time-scored sources
        assert da.applicable is False

    def test_cadence_aware_ratio(self) -> None:
        from src.quality.models import SourceAge, SourceUpdateFrequency
        # IO table with 5-year cadence, 6 years old → ratio 1.2 → score 0.7
        ages = [
            SourceAge(source_name="IO Table", age_days=365*6,
                      expected_frequency=SourceUpdateFrequency.QUINQUENNIAL),
        ]
        da = QualityScorer().score_freshness(ages)
        assert da.score == pytest.approx(0.7)
```

**Step 2:** Run tests, verify FAIL

**Step 3: Add remaining scoring methods** to QualityScorer. Freshness uses cadence-aware ratio (Amendment 2): map SourceUpdateFrequency to expected days, compute ratio = age_days / expected_days, look up score from freshness_ratio_thresholds.

Frequency-to-days mapping:
- QUARTERLY → 90, ANNUAL → 365, BIENNIAL → 730, TRIENNIAL → 1095, QUINQUENNIAL → 1825, PER_ENGAGEMENT → not time-scored

**Step 4:** Run tests, verify PASS

**Step 5:** Commit

```bash
git commit -m "[quality] Task 3: scorer — constraints, workforce, plausibility, freshness"
```

---

### Task 4: Composite score and grade

**Files:**
- Modify: `src/quality/scorer.py`
- Modify: `tests/quality/test_scorer.py`

**Step 1: Write failing tests for composite**

```python
class TestCompositeScore:
    def test_all_perfect(self) -> None:
        scorer = QualityScorer()
        dims = [
            scorer.score_vintage(2026, 2026),
            scorer.score_mapping(1.0, {"HIGH":1,"MEDIUM":0,"LOW":0}, 0, 0, 0),
            scorer.score_assumptions(1.0, 1.0),
            scorer.score_constraints({"HARD":10,"ESTIMATED":0,"ASSUMED":0}),
            scorer.score_workforce("HIGH"),
            scorer.score_plausibility(100.0, 0),
        ]
        from src.quality.models import SourceAge, SourceUpdateFrequency
        dims.append(scorer.score_freshness([
            SourceAge("IO", 100, SourceUpdateFrequency.ANNUAL),
        ]))
        result = scorer.composite_score(dims)
        assert result.composite_score == pytest.approx(1.0)
        assert result.grade.value == "A"

    def test_completeness_cap_at_c(self) -> None:
        """If fewer than 50% dimensions are applicable, cap at C."""
        scorer = QualityScorer()
        dims = [
            scorer.score_vintage(2026, 2026),  # applicable
            scorer.score_constraints(None),  # not applicable
            scorer.score_workforce(None),  # not applicable
        ]
        # Only 1 of 3 applicable → 33% → cap at D
        result = scorer.composite_score(dims)
        assert result.grade.value in ("C", "D")

    def test_grade_b(self) -> None:
        scorer = QualityScorer()
        dims = [
            scorer.score_vintage(2023, 2026),  # 3yr → 0.7
            scorer.score_mapping(0.9, {"HIGH":0.6,"MEDIUM":0.3,"LOW":0.1}, 0.05, 0.05, 0.5),
            scorer.score_assumptions(0.7, 0.8),
            scorer.score_constraints({"HARD":5,"ESTIMATED":3,"ASSUMED":2}),
            scorer.score_workforce("MEDIUM"),
            scorer.score_plausibility(80.0, 2),
        ]
        from src.quality.models import SourceAge, SourceUpdateFrequency
        dims.append(scorer.score_freshness([
            SourceAge("IO", 400, SourceUpdateFrequency.ANNUAL),
        ]))
        result = scorer.composite_score(dims)
        assert result.grade.value in ("B", "C")
```

**Step 2:** Run tests, verify FAIL

**Step 3: Implement composite_score method** that:
1. Filters to applicable dimensions
2. Computes completeness_pct
3. Computes weighted average using config weights
4. Determines grade from thresholds
5. Applies completeness cap (Amendment 1)
6. Returns RunQualityAssessment

**Step 4:** Run tests, verify PASS

**Step 5:** Commit

```bash
git commit -m "[quality] Task 4: composite scoring with grade and completeness cap"
```

---

### Task 5: Warning engine

**Files:**
- Create: `src/quality/warnings.py`
- Test: `tests/quality/test_warnings.py`

**Step 1: Write failing tests**

```python
"""Tests for warning engine (MVP-13 Task 5)."""
import pytest
from src.quality.warnings import WarningEngine
from src.quality.models import QualitySeverity, QualityDimension, DimensionAssessment
from src.quality.scorer import QualityScorer


class TestVintageWarnings:
    def test_no_warning_fresh_model(self) -> None:
        engine = WarningEngine()
        scorer = QualityScorer()
        da = scorer.score_vintage(2024, 2026)
        warnings = engine.check_vintage(da)
        assert len(warnings) == 0

    def test_warning_5yr(self) -> None:
        engine = WarningEngine()
        scorer = QualityScorer()
        da = scorer.score_vintage(2021, 2026)
        warnings = engine.check_vintage(da)
        assert any(w.severity == QualitySeverity.WARNING for w in warnings)

    def test_critical_8yr(self) -> None:
        engine = WarningEngine()
        scorer = QualityScorer()
        da = scorer.score_vintage(2018, 2026)
        warnings = engine.check_vintage(da)
        assert any(w.severity == QualitySeverity.CRITICAL for w in warnings)


class TestMappingWarnings:
    def test_waiver_required_high_spend(self) -> None:
        engine = WarningEngine()
        scorer = QualityScorer()
        da = scorer.score_mapping(0.8, {"HIGH":0.5,"MEDIUM":0.3,"LOW":0.2}, 0.05, 0.1, 6.0)
        warnings = engine.check_mapping(da)
        assert any(w.severity == QualitySeverity.WAIVER_REQUIRED for w in warnings)

    def test_critical_moderate_spend(self) -> None:
        engine = WarningEngine()
        scorer = QualityScorer()
        da = scorer.score_mapping(0.8, {"HIGH":0.5,"MEDIUM":0.3,"LOW":0.2}, 0.05, 0.1, 2.0)
        warnings = engine.check_mapping(da)
        assert any(w.severity == QualitySeverity.CRITICAL for w in warnings)


class TestCheckAll:
    def test_aggregates_all_checks(self) -> None:
        engine = WarningEngine()
        scorer = QualityScorer()
        dims = [
            scorer.score_vintage(2018, 2026),  # should produce CRITICAL
            scorer.score_mapping(1.0, {"HIGH":1,"MEDIUM":0,"LOW":0}, 0, 0, 0),
        ]
        warnings = engine.check_all(dims)
        assert len(warnings) > 0

    def test_counts_by_severity(self) -> None:
        engine = WarningEngine()
        scorer = QualityScorer()
        dims = [scorer.score_vintage(2018, 2026)]
        warnings = engine.check_all(dims)
        counts = engine.count_by_severity(warnings)
        assert "CRITICAL" in counts or "WARNING" in counts
```

**Step 2:** Run tests, verify FAIL

**Step 3: Implement WarningEngine** with check methods per dimension and `check_all()` aggregator. Each check examines DimensionAssessment.inputs_used for threshold comparison. Uses config for thresholds.

**Step 4:** Run tests, verify PASS

**Step 5:** Commit

```bash
git commit -m "[quality] Task 5: warning engine with severity-based checks"
```

---

### Task 6: Source freshness registry

**Files:**
- Create: `src/quality/source_registry.py`
- Test: `tests/quality/test_source_registry.py`

**Step 1: Write failing tests**

```python
"""Tests for source freshness registry (MVP-13 Task 6)."""
import pytest
from datetime import datetime, timezone, timedelta
from src.quality.source_registry import SourceFreshnessRegistry, DataSource
from src.quality.models import SourceUpdateFrequency


class TestDataSource:
    def test_create(self) -> None:
        src = DataSource(
            name="Saudi IO Table",
            source_type="io_table",
            provider="GASTAT",
            last_updated=datetime(2021, 1, 1, tzinfo=timezone.utc),
            last_checked=datetime(2026, 1, 1, tzinfo=timezone.utc),
            expected_update_frequency=SourceUpdateFrequency.QUINQUENNIAL,
        )
        assert src.name == "Saudi IO Table"
        assert src.provider == "GASTAT"


class TestSourceFreshnessRegistry:
    def test_register_and_get(self) -> None:
        reg = SourceFreshnessRegistry()
        src = DataSource(
            name="WDI", source_type="benchmark", provider="World Bank",
            last_updated=datetime(2025, 6, 1, tzinfo=timezone.utc),
            last_checked=datetime(2026, 1, 1, tzinfo=timezone.utc),
            expected_update_frequency=SourceUpdateFrequency.ANNUAL,
        )
        reg.register(src)
        assert reg.get("WDI") is not None

    def test_get_all(self) -> None:
        reg = SourceFreshnessRegistry()
        reg.register(DataSource(
            name="A", source_type="t", provider="p",
            last_updated=datetime(2025, 1, 1, tzinfo=timezone.utc),
            last_checked=datetime(2026, 1, 1, tzinfo=timezone.utc),
            expected_update_frequency=SourceUpdateFrequency.ANNUAL,
        ))
        assert len(reg.get_all()) == 1

    def test_get_stale_sources(self) -> None:
        reg = SourceFreshnessRegistry()
        reg.register(DataSource(
            name="Old", source_type="t", provider="p",
            last_updated=datetime(2020, 1, 1, tzinfo=timezone.utc),
            last_checked=datetime(2026, 1, 1, tzinfo=timezone.utc),
            expected_update_frequency=SourceUpdateFrequency.ANNUAL,
        ))
        stale = reg.get_stale_sources(as_of=datetime(2026, 2, 28, tzinfo=timezone.utc))
        assert len(stale) == 1

    def test_update_timestamp(self) -> None:
        reg = SourceFreshnessRegistry()
        reg.register(DataSource(
            name="X", source_type="t", provider="p",
            last_updated=datetime(2020, 1, 1, tzinfo=timezone.utc),
            last_checked=datetime(2020, 1, 1, tzinfo=timezone.utc),
            expected_update_frequency=SourceUpdateFrequency.ANNUAL,
        ))
        new_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        reg.update_timestamp("X", new_time)
        assert reg.get("X").last_updated == new_time

    def test_to_source_ages(self) -> None:
        reg = SourceFreshnessRegistry()
        reg.register(DataSource(
            name="IO", source_type="io", provider="GASTAT",
            last_updated=datetime(2021, 1, 1, tzinfo=timezone.utc),
            last_checked=datetime(2026, 1, 1, tzinfo=timezone.utc),
            expected_update_frequency=SourceUpdateFrequency.QUINQUENNIAL,
        ))
        ages = reg.to_source_ages(as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert len(ages) == 1
        assert ages[0].source_name == "IO"
        assert ages[0].age_days == pytest.approx(365 * 5, abs=2)

    def test_seed_defaults(self) -> None:
        reg = SourceFreshnessRegistry.with_seed_defaults()
        assert len(reg.get_all()) >= 6
```

**Step 2:** Run tests, verify FAIL

**Step 3: Implement SourceFreshnessRegistry** with DataSource model, register/get/update/stale methods, `to_source_ages()` converter, and `with_seed_defaults()` class method seeding 8 default sources.

**Step 4:** Run tests, verify PASS

**Step 5:** Commit

```bash
git commit -m "[quality] Task 6: source freshness registry with seed defaults"
```

---

### Task 7: Multiplier plausibility checker

**Files:**
- Create: `src/quality/plausibility.py`
- Test: `tests/quality/test_plausibility.py`

**Step 1: Write failing tests**

```python
"""Tests for multiplier plausibility checker (MVP-13 Task 7)."""
import numpy as np
import pytest
from src.quality.plausibility import PlausibilityChecker, PlausibilityResult, SectorPlausibilityDetail
from src.quality.models import PlausibilityStatus


class TestPlausibilityChecker:
    def test_all_in_range(self) -> None:
        checker = PlausibilityChecker()
        B = np.array([[1.5, 0.3], [0.2, 1.4]])
        benchmarks = {"S1": (1.0, 2.0), "S2": (1.0, 2.0)}
        result = checker.check(B, ["S1", "S2"], benchmarks)
        assert result.multipliers_in_range_pct == pytest.approx(100.0)
        assert len(result.flagged_sectors) == 0

    def test_one_above_range(self) -> None:
        checker = PlausibilityChecker()
        B = np.array([[3.0, 0.3], [0.2, 1.4]])
        benchmarks = {"S1": (1.0, 2.0), "S2": (1.0, 2.0)}
        result = checker.check(B, ["S1", "S2"], benchmarks)
        assert result.multipliers_in_range_pct == pytest.approx(50.0)
        assert "S1" in result.flagged_sectors

    def test_no_benchmark(self) -> None:
        checker = PlausibilityChecker()
        B = np.array([[1.5, 0.3], [0.2, 1.4]])
        benchmarks = {"S1": (1.0, 2.0)}  # S2 has no benchmark
        result = checker.check(B, ["S1", "S2"], benchmarks)
        # S2 excluded from pct calculation
        assert result.multipliers_in_range_pct == pytest.approx(100.0)

    def test_sector_details(self) -> None:
        checker = PlausibilityChecker()
        B = np.array([[1.5, 0.3], [0.2, 1.4]])
        benchmarks = {"S1": (1.0, 2.0), "S2": (1.0, 2.0)}
        result = checker.check(B, ["S1", "S2"], benchmarks)
        assert len(result.sector_details) == 2
        assert result.sector_details[0].status == PlausibilityStatus.IN_RANGE

    def test_below_range(self) -> None:
        checker = PlausibilityChecker()
        B = np.array([[0.5, 0.3], [0.2, 1.4]])
        benchmarks = {"S1": (1.0, 2.0), "S2": (1.0, 2.0)}
        result = checker.check(B, ["S1", "S2"], benchmarks)
        detail = next(d for d in result.sector_details if d.sector_code == "S1")
        assert detail.status == PlausibilityStatus.BELOW_RANGE

    def test_cache_per_model(self) -> None:
        """Amendment 13: cache plausibility results per model."""
        checker = PlausibilityChecker()
        B = np.array([[1.5]])
        benchmarks = {"S1": (1.0, 2.0)}
        r1 = checker.check(B, ["S1"], benchmarks, model_version_id="abc")
        r2 = checker.check(B, ["S1"], benchmarks, model_version_id="abc")
        assert r1 is r2  # same cached object
```

**Step 2:** Run tests, verify FAIL

**Step 3: Implement PlausibilityChecker** with `check()` method extracting diagonal of B as output multipliers, comparing against benchmark ranges, returning PlausibilityResult. Cache by model_version_id (Amendment 13).

**Step 4:** Run tests, verify PASS

**Step 5:** Commit

```bash
git commit -m "[quality] Task 7: multiplier plausibility checker with caching"
```

---

### Task 8: Nowcasting service (governed RAS workflow)

**Files:**
- Create: `src/quality/nowcast.py`
- Test: `tests/quality/test_nowcast.py`

**Step 1: Write failing tests**

```python
"""Tests for nowcasting service (MVP-13 Task 8)."""
import numpy as np
import pytest
from src.quality.nowcast import NowcastingService, NowcastResult, TargetTotalProvenance
from src.quality.models import NowcastStatus
from src.engine.model_store import ModelStore


class TestNowcastingService:
    def _make_model_store(self):
        store = ModelStore()
        Z = np.array([[10.0, 5.0], [3.0, 8.0]])
        x = np.array([30.0, 20.0])
        mv = store.register(Z=Z, x=x, sector_codes=["S1","S2"], base_year=2021, source="test")
        return store, mv

    def test_create_nowcast(self) -> None:
        store, base_mv = self._make_model_store()
        svc = NowcastingService(model_store=store)
        provenance = [
            TargetTotalProvenance(sector_code="S1", target_value=35.0, source="GASTAT", evidence_refs=["doc1"]),
            TargetTotalProvenance(sector_code="S2", target_value=25.0, source="GASTAT", evidence_refs=["doc1"]),
        ]
        result = svc.create_nowcast(
            base_model_version_id=base_mv.model_version_id,
            target_row_totals=np.array([35.0, 25.0]),
            target_col_totals=np.array([35.0, 25.0]),
            target_year=2025,
            provenance=provenance,
        )
        assert result.candidate_status == NowcastStatus.DRAFT
        assert result.converged is True

    def test_approve_nowcast(self) -> None:
        store, base_mv = self._make_model_store()
        svc = NowcastingService(model_store=store)
        provenance = [
            TargetTotalProvenance(sector_code="S1", target_value=35.0, source="GASTAT", evidence_refs=[]),
            TargetTotalProvenance(sector_code="S2", target_value=25.0, source="GASTAT", evidence_refs=[]),
        ]
        result = svc.create_nowcast(
            base_model_version_id=base_mv.model_version_id,
            target_row_totals=np.array([35.0, 25.0]),
            target_col_totals=np.array([35.0, 25.0]),
            target_year=2025,
            provenance=provenance,
        )
        mv = svc.approve_nowcast(result.nowcast_id)
        assert mv is not None
        assert store.get(mv.model_version_id) is not None

    def test_reject_nowcast(self) -> None:
        store, base_mv = self._make_model_store()
        svc = NowcastingService(model_store=store)
        provenance = [
            TargetTotalProvenance(sector_code="S1", target_value=35.0, source="GASTAT", evidence_refs=[]),
            TargetTotalProvenance(sector_code="S2", target_value=25.0, source="GASTAT", evidence_refs=[]),
        ]
        result = svc.create_nowcast(
            base_model_version_id=base_mv.model_version_id,
            target_row_totals=np.array([35.0, 25.0]),
            target_col_totals=np.array([35.0, 25.0]),
            target_year=2025,
            provenance=provenance,
        )
        svc.reject_nowcast(result.nowcast_id)
        # Verify status changed
        status = svc.get_status(result.nowcast_id)
        assert status == NowcastStatus.REJECTED

    def test_double_approve_raises(self) -> None:
        store, base_mv = self._make_model_store()
        svc = NowcastingService(model_store=store)
        provenance = [
            TargetTotalProvenance(sector_code="S1", target_value=35.0, source="G", evidence_refs=[]),
            TargetTotalProvenance(sector_code="S2", target_value=25.0, source="G", evidence_refs=[]),
        ]
        result = svc.create_nowcast(
            base_model_version_id=base_mv.model_version_id,
            target_row_totals=np.array([35.0, 25.0]),
            target_col_totals=np.array([35.0, 25.0]),
            target_year=2025,
            provenance=provenance,
        )
        svc.approve_nowcast(result.nowcast_id)
        with pytest.raises(ValueError, match="already"):
            svc.approve_nowcast(result.nowcast_id)
```

**Step 2:** Run tests, verify FAIL

**Step 3: Implement NowcastingService** wrapping RASBalancer with draft/candidate lifecycle (Amendment 8). Store candidates in-memory dict. `create_nowcast` runs RAS but doesn't publish. `approve_nowcast` registers with ModelStore. `reject_nowcast` marks as rejected.

**Step 4:** Run tests, verify PASS

**Step 5:** Commit

```bash
git commit -m "[quality] Task 8: governed nowcasting with draft/approve/reject lifecycle"
```

---

### Task 9: Quality assessment service (orchestrator)

**Files:**
- Create: `src/quality/service.py`
- Test: `tests/quality/test_service.py`

**Step 1: Write failing tests**

```python
"""Tests for quality assessment service (MVP-13 Task 9)."""
import pytest
from src.quality.service import QualityAssessmentService
from src.quality.models import QualityGrade, QualityDimension


class TestQualityAssessmentService:
    def test_full_assessment(self) -> None:
        svc = QualityAssessmentService()
        result = svc.assess(
            base_year=2024, current_year=2026,
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
            source_ages=[],
            run_id=None,
        )
        assert result.composite_score > 0.0
        assert result.grade in QualityGrade
        assert len(result.dimension_assessments) == 7

    def test_minimal_assessment(self) -> None:
        """Only vintage is assessable."""
        svc = QualityAssessmentService()
        result = svc.assess(
            base_year=2024, current_year=2026,
            mapping_coverage_pct=None,
            mapping_confidence_dist=None,
            mapping_residual_pct=None,
            mapping_unresolved_pct=None,
            mapping_unresolved_spend_pct=None,
            assumption_ranges_coverage_pct=None,
            assumption_approval_rate=None,
            constraint_confidence_summary=None,
            workforce_overall_confidence=None,
            plausibility_in_range_pct=None,
            plausibility_flagged_count=None,
            source_ages=None,
            run_id=None,
        )
        assert result.completeness_pct < 50.0
        assert len(result.assessed_dimensions) == 1
        assert QualityDimension.VINTAGE in result.assessed_dimensions

    def test_versioned_assessment(self) -> None:
        """Amendment 5: append-only versioned assessments."""
        from uuid_extensions import uuid7
        svc = QualityAssessmentService()
        run_id = uuid7()
        r1 = svc.assess(base_year=2024, current_year=2026,
            run_id=run_id,
            mapping_coverage_pct=0.9,
            mapping_confidence_dist={"HIGH":0.7,"MEDIUM":0.2,"LOW":0.1},
            mapping_residual_pct=0.03, mapping_unresolved_pct=0.02,
            mapping_unresolved_spend_pct=0.5,
            assumption_ranges_coverage_pct=0.8, assumption_approval_rate=0.9,
            constraint_confidence_summary=None,
            workforce_overall_confidence=None,
            plausibility_in_range_pct=None, plausibility_flagged_count=None,
            source_ages=None)
        r2 = svc.assess(base_year=2024, current_year=2026,
            run_id=run_id,
            mapping_coverage_pct=0.95,
            mapping_confidence_dist={"HIGH":0.8,"MEDIUM":0.1,"LOW":0.1},
            mapping_residual_pct=0.02, mapping_unresolved_pct=0.01,
            mapping_unresolved_spend_pct=0.3,
            assumption_ranges_coverage_pct=0.9, assumption_approval_rate=0.95,
            constraint_confidence_summary=None,
            workforce_overall_confidence=None,
            plausibility_in_range_pct=None, plausibility_flagged_count=None,
            source_ages=None)
        assert r2.assessment_version == r1.assessment_version + 1

    def test_warnings_included(self) -> None:
        svc = QualityAssessmentService()
        result = svc.assess(
            base_year=2016, current_year=2026,  # 10yr old → CRITICAL
            mapping_coverage_pct=None, mapping_confidence_dist=None,
            mapping_residual_pct=None, mapping_unresolved_pct=None,
            mapping_unresolved_spend_pct=None,
            assumption_ranges_coverage_pct=None, assumption_approval_rate=None,
            constraint_confidence_summary=None,
            workforce_overall_confidence=None,
            plausibility_in_range_pct=None, plausibility_flagged_count=None,
            source_ages=None, run_id=None,
        )
        assert result.critical_count > 0 or result.warning_count > 0
```

**Step 2:** Run tests, verify FAIL

**Step 3: Implement QualityAssessmentService** that:
1. Creates QualityScorer and WarningEngine
2. Calls scoring functions for each applicable dimension (None inputs → not applicable)
3. Calls composite_score
4. Runs WarningEngine.check_all
5. Tracks assessment versions per run_id (Amendment 5)
6. Returns RunQualityAssessment

**Step 4:** Run tests, verify PASS

**Step 5:** Commit

```bash
git commit -m "[quality] Task 9: quality assessment orchestrator service"
```

---

### Task 10: Integration with existing pipeline

**Files:**
- Modify: `src/engine/batch.py` (add optional quality_assessment_id to SingleRunResult)
- Test: `tests/quality/test_integration.py`

**Step 1: Write failing tests**

```python
"""Integration tests for quality automation (MVP-13 Task 10)."""
import numpy as np
import pytest
from uuid_extensions import uuid7
from src.quality.service import QualityAssessmentService
from src.quality.source_registry import SourceFreshnessRegistry
from src.quality.plausibility import PlausibilityChecker
from src.quality.nowcast import NowcastingService
from src.engine.model_store import ModelStore
from src.engine.batch import SingleRunResult


class TestSingleRunResultQualityField:
    def test_default_none(self) -> None:
        """quality_assessment_id defaults to None for backward compat."""
        from src.models.run import RunSnapshot, ResultSet
        snap = RunSnapshot(
            run_id=uuid7(), model_version_id=uuid7(),
            taxonomy_version_id=uuid7(), concordance_version_id=uuid7(),
            mapping_library_version_id=uuid7(),
            assumption_library_version_id=uuid7(),
            prompt_pack_version_id=uuid7(),
        )
        sr = SingleRunResult(snapshot=snap, result_sets=[])
        assert sr.quality_assessment_id is None


class TestEndToEnd:
    def test_full_pipeline(self) -> None:
        """E2E: model → plausibility → assessment."""
        store = ModelStore()
        Z = np.array([[10, 5], [3, 8]], dtype=float)
        x = np.array([30, 20], dtype=float)
        mv = store.register(Z=Z, x=x, sector_codes=["S1","S2"],
                            base_year=2024, source="test")
        loaded = store.get(mv.model_version_id)

        # Plausibility
        checker = PlausibilityChecker()
        p_result = checker.check(loaded.B, ["S1","S2"],
                                 {"S1": (1.0, 3.0), "S2": (1.0, 3.0)})

        # Source freshness
        registry = SourceFreshnessRegistry.with_seed_defaults()
        from datetime import datetime, timezone
        ages = registry.to_source_ages(as_of=datetime(2026, 2, 28, tzinfo=timezone.utc))

        # Quality assessment
        svc = QualityAssessmentService()
        result = svc.assess(
            base_year=2024, current_year=2026,
            mapping_coverage_pct=0.9,
            mapping_confidence_dist={"HIGH": 0.6, "MEDIUM": 0.3, "LOW": 0.1},
            mapping_residual_pct=0.05, mapping_unresolved_pct=0.03,
            mapping_unresolved_spend_pct=1.0,
            assumption_ranges_coverage_pct=0.7, assumption_approval_rate=0.85,
            constraint_confidence_summary={"HARD": 5, "ESTIMATED": 3, "ASSUMED": 2},
            workforce_overall_confidence="MEDIUM",
            plausibility_in_range_pct=p_result.multipliers_in_range_pct,
            plausibility_flagged_count=len(p_result.flagged_sectors),
            source_ages=ages,
            run_id=uuid7(),
        )
        assert result.composite_score > 0.0
        assert len(result.dimension_assessments) == 7
        assert all(da.applicable for da in result.dimension_assessments)


class TestNowcastIntegration:
    def test_nowcast_then_assess(self) -> None:
        store = ModelStore()
        Z = np.array([[10, 5], [3, 8]], dtype=float)
        x = np.array([30, 20], dtype=float)
        mv = store.register(Z=Z, x=x, sector_codes=["S1","S2"],
                            base_year=2021, source="gastat-2021")
        from src.quality.nowcast import TargetTotalProvenance
        svc = NowcastingService(model_store=store)
        provenance = [
            TargetTotalProvenance(sector_code="S1", target_value=35, source="GASTAT", evidence_refs=[]),
            TargetTotalProvenance(sector_code="S2", target_value=25, source="GASTAT", evidence_refs=[]),
        ]
        nc = svc.create_nowcast(
            base_model_version_id=mv.model_version_id,
            target_row_totals=np.array([35, 25], dtype=float),
            target_col_totals=np.array([35, 25], dtype=float),
            target_year=2025,
            provenance=provenance,
        )
        approved_mv = svc.approve_nowcast(nc.nowcast_id)
        # Now assess with nowcast model
        qa_svc = QualityAssessmentService()
        result = qa_svc.assess(
            base_year=2025, current_year=2026,
            mapping_coverage_pct=None, mapping_confidence_dist=None,
            mapping_residual_pct=None, mapping_unresolved_pct=None,
            mapping_unresolved_spend_pct=None,
            assumption_ranges_coverage_pct=None, assumption_approval_rate=None,
            constraint_confidence_summary=None,
            workforce_overall_confidence=None,
            plausibility_in_range_pct=None, plausibility_flagged_count=None,
            source_ages=None, run_id=None,
        )
        assert result.composite_score > 0.0
```

**Step 2:** Run tests, verify FAIL

**Step 3: Add quality_assessment_id to SingleRunResult** (optional UUID, default None). Implement integration glue.

**Step 4:** Run tests, verify PASS

**Step 5:** Run full test suite

```bash
pytest -x -q
```

**Step 6:** Commit

```bash
git commit -m "[quality] Task 10: integration with pipeline and end-to-end tests"
```

---

### Task 11: Documentation and final verification

**Files:**
- Create: `docs/mvp13_data_quality_automation.md`

**Step 1:** Run full test suite, verify all pass

```bash
pytest -x -q
```

**Step 2:** Write documentation covering: overview, module structure, 7 dimensions, composite scoring, warning taxonomy, source registry, plausibility checks, nowcasting governance, integration points, configuration.

**Step 3:** Commit

```bash
git add docs/mvp13_data_quality_automation.md
git commit -m "[quality] Task 11: MVP-13 documentation"
```

**Step 4:** Run final verification

```bash
pytest -x -q  # all tests pass
pytest tests/quality/ -v  # all quality tests detailed
```
