"""Tests for parity benchmark gate (Sprint 18).

Validates that run_parity_check correctly compares a LoadedModel solver
output against golden benchmark values. Pure deterministic -- no DB, no LLM.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from src.engine.model_store import LoadedModel, ModelStore
from src.engine.parity_gate import ParityMetric, run_parity_check

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sg_parity_benchmark_v1.json"


@pytest.fixture()
def benchmark() -> dict:
    """Load the golden benchmark fixture."""
    with FIXTURE_PATH.open() as f:
        return json.load(f)


@pytest.fixture()
def golden_model(benchmark: dict) -> LoadedModel:
    """Register the golden model from benchmark fixture."""
    store = ModelStore()
    m = benchmark["model"]
    mv = store.register(
        Z=np.array(m["Z"]),
        x=np.array(m["x"]),
        sector_codes=m["sector_codes"],
        base_year=m["base_year"],
        source="parity-test",
    )
    return store.get(mv.model_version_id)


class TestIdenticalModelPasses:
    """test_identical_model_passes -- model matching benchmark passes."""

    def test_identical_model_passes(
        self, golden_model: LoadedModel, benchmark: dict
    ) -> None:
        result = run_parity_check(
            model=golden_model,
            benchmark_scenario=benchmark,
        )
        assert result.passed is True
        assert result.reason_code is None


class TestResultStructure:
    """test_result_has_correct_structure -- ParityResult/ParityMetric fields."""

    def test_result_has_correct_structure(
        self, golden_model: LoadedModel, benchmark: dict
    ) -> None:
        result = run_parity_check(
            model=golden_model,
            benchmark_scenario=benchmark,
        )
        # ParityResult fields
        assert isinstance(result.passed, bool)
        assert isinstance(result.benchmark_id, str)
        assert isinstance(result.tolerance, float)
        assert isinstance(result.metrics, list)
        assert isinstance(result.checked_at, datetime)
        assert result.benchmark_id == "sg_3sector_golden_v1"

        # ParityMetric fields
        for m in result.metrics:
            assert isinstance(m, ParityMetric)
            assert isinstance(m.metric_name, str)
            assert isinstance(m.expected, float)
            assert isinstance(m.actual, float)
            assert isinstance(m.relative_error, float)
            assert isinstance(m.tolerance, float)
            assert isinstance(m.passed, bool)


class TestAllMetricsPass:
    """test_all_metrics_pass_within_tolerance -- every metric passes."""

    def test_all_metrics_pass_within_tolerance(
        self, golden_model: LoadedModel, benchmark: dict
    ) -> None:
        result = run_parity_check(
            model=golden_model,
            benchmark_scenario=benchmark,
        )
        assert len(result.metrics) > 0
        for m in result.metrics:
            assert m.passed is True, f"{m.metric_name} failed: re={m.relative_error}"
            assert m.reason_code is None


class TestPerturbedModelFails:
    """test_perturbed_model_fails -- Z[0,0]*1.5 causes failure."""

    def test_perturbed_model_fails(self, benchmark: dict) -> None:
        m = benchmark["model"]
        Z = np.array(m["Z"])
        Z[0, 0] *= 1.5  # perturb

        store = ModelStore()
        mv = store.register(
            Z=Z,
            x=np.array(m["x"]),
            sector_codes=m["sector_codes"],
            base_year=m["base_year"],
            source="parity-test-perturbed",
        )
        perturbed = store.get(mv.model_version_id)

        result = run_parity_check(
            model=perturbed,
            benchmark_scenario=benchmark,
        )
        assert result.passed is False
        assert result.reason_code == "PARITY_TOLERANCE_BREACH"


class TestToleranceBreachReasonCode:
    """test_tolerance_breach_metric_has_reason_code -- failed metrics tagged."""

    def test_tolerance_breach_metric_has_reason_code(
        self, benchmark: dict
    ) -> None:
        m = benchmark["model"]
        Z = np.array(m["Z"])
        Z[0, 0] *= 1.5

        store = ModelStore()
        mv = store.register(
            Z=Z,
            x=np.array(m["x"]),
            sector_codes=m["sector_codes"],
            base_year=m["base_year"],
            source="parity-test-perturbed",
        )
        perturbed = store.get(mv.model_version_id)

        result = run_parity_check(
            model=perturbed,
            benchmark_scenario=benchmark,
        )
        failed_metrics = [met for met in result.metrics if not met.passed]
        assert len(failed_metrics) > 0
        for met in failed_metrics:
            assert met.reason_code == "PARITY_TOLERANCE_BREACH"


class TestMissingBaseline:
    """test_missing_baseline_benchmark -- empty expected_outputs."""

    def test_missing_baseline_empty(
        self, golden_model: LoadedModel, benchmark: dict
    ) -> None:
        bench = {**benchmark, "expected_outputs": {}}
        result = run_parity_check(
            model=golden_model,
            benchmark_scenario=bench,
        )
        assert result.passed is False
        assert result.reason_code == "PARITY_MISSING_BASELINE"

    def test_missing_baseline_key_absent(
        self, golden_model: LoadedModel, benchmark: dict
    ) -> None:
        bench = {k: v for k, v in benchmark.items() if k != "expected_outputs"}
        result = run_parity_check(
            model=golden_model,
            benchmark_scenario=bench,
        )
        assert result.passed is False
        assert result.reason_code == "PARITY_MISSING_BASELINE"


class TestMissingMetric:
    """test_missing_metric_in_engine_output -- benchmark expects metric engine does not emit."""

    def test_missing_metric_in_engine_output(
        self, golden_model: LoadedModel, benchmark: dict
    ) -> None:
        bench = {
            **benchmark,
            "expected_outputs": {
                **benchmark["expected_outputs"],
                "gdp_real": 999.0,
            },
        }
        result = run_parity_check(
            model=golden_model,
            benchmark_scenario=bench,
        )
        assert result.passed is False
        # Find the missing metric
        missing = [m for m in result.metrics if m.metric_name == "gdp_real"]
        assert len(missing) == 1
        assert missing[0].reason_code == "PARITY_METRIC_MISSING"
        assert missing[0].passed is False


class TestEngineError:
    """test_engine_error_wrong_shock_dimension -- solver error captured."""

    def test_engine_error_wrong_shock_dimension(
        self, golden_model: LoadedModel, benchmark: dict
    ) -> None:
        bench = {
            **benchmark,
            "scenario": {
                **benchmark["scenario"],
                "shock_vector": [1.0, 2.0],
            },
        }
        result = run_parity_check(
            model=golden_model,
            benchmark_scenario=bench,
        )
        assert result.passed is False
        assert result.reason_code == "PARITY_ENGINE_ERROR"


class TestCustomTolerance:
    """test_custom_tolerance -- tolerance=0.0001 flows through correctly."""

    def test_custom_tolerance(
        self, golden_model: LoadedModel, benchmark: dict
    ) -> None:
        result = run_parity_check(
            model=golden_model,
            benchmark_scenario=benchmark,
            tolerance=0.0001,
        )
        assert result.tolerance == 0.0001
        for m in result.metrics:
            assert m.tolerance == 0.0001


class TestCheckedAtUTC:
    """test_checked_at_is_utc -- result.checked_at is UTC datetime."""

    def test_checked_at_is_utc(
        self, golden_model: LoadedModel, benchmark: dict
    ) -> None:
        result = run_parity_check(
            model=golden_model,
            benchmark_scenario=benchmark,
        )
        assert result.checked_at.tzinfo is not None
        assert result.checked_at.tzinfo == UTC
