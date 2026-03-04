"""Tests for deterministic portfolio optimization engine — Sprint 21."""
# ruff: noqa: S101, ANN201

from uuid import UUID

import pytest

from src.engine.portfolio_optimizer import (
    MAX_CANDIDATES,
    CandidateRun,
    PortfolioConfigError,
    PortfolioInfeasibleError,
    optimize_portfolio,
)


def _uuid(n: int) -> UUID:
    """Deterministic UUID from integer for testing."""
    return UUID(f"00000000-0000-0000-0000-{n:012d}")


class TestHappyPath:
    def test_selects_optimal_pair(self):
        """3 candidates, budget allows 2. Optimal pair is highest objective sum."""
        candidates = [
            CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=50.0),
            CandidateRun(run_id=_uuid(2), objective_value=20.0, cost=40.0),
            CandidateRun(run_id=_uuid(3), objective_value=15.0, cost=30.0),
        ]
        result = optimize_portfolio(candidates, budget=80.0)
        # Best pair: run2 (obj=20, cost=40) + run3 (obj=15, cost=30) = obj=35, cost=70
        assert set(result.selected_run_ids) == {_uuid(2), _uuid(3)}
        assert result.total_objective == pytest.approx(35.0)
        assert result.total_cost == pytest.approx(70.0)

    def test_single_candidate_selected(self):
        candidates = [CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=50.0)]
        result = optimize_portfolio(candidates, budget=100.0)
        assert result.selected_run_ids == [_uuid(1)]
        assert result.total_objective == pytest.approx(10.0)

    def test_all_candidates_selected_when_budget_allows(self):
        candidates = [
            CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=10.0),
            CandidateRun(run_id=_uuid(2), objective_value=20.0, cost=10.0),
        ]
        result = optimize_portfolio(candidates, budget=100.0)
        assert len(result.selected_run_ids) == 2
        assert result.total_objective == pytest.approx(30.0)


class TestDeterminism:
    def test_tiebreak_lexicographic_run_id(self):
        """Two subsets with equal objective — pick lexicographically smaller run_ids."""
        candidates = [
            CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=50.0),
            CandidateRun(run_id=_uuid(2), objective_value=10.0, cost=50.0),
            CandidateRun(run_id=_uuid(3), objective_value=10.0, cost=50.0),
        ]
        # Budget=60 allows exactly 1. All have same objective. Pick smallest run_id.
        result = optimize_portfolio(candidates, budget=60.0)
        assert result.selected_run_ids == [_uuid(1)]

    def test_selected_run_ids_sorted_asc(self):
        candidates = [
            CandidateRun(run_id=_uuid(3), objective_value=10.0, cost=10.0),
            CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=10.0),
            CandidateRun(run_id=_uuid(2), objective_value=10.0, cost=10.0),
        ]
        result = optimize_portfolio(candidates, budget=100.0)
        assert result.selected_run_ids == [_uuid(1), _uuid(2), _uuid(3)]

    def test_solver_method_reported(self):
        candidates = [CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=10.0)]
        result = optimize_portfolio(candidates, budget=100.0)
        assert result.solver_method == "exact_binary_knapsack_v1"

    def test_feasible_count_reported(self):
        candidates = [
            CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=30.0),
            CandidateRun(run_id=_uuid(2), objective_value=20.0, cost=30.0),
        ]
        # Budget=50: {1} fits (30), {2} fits (30), {1,2} doesn't (60). 2 feasible.
        result = optimize_portfolio(candidates, budget=50.0)
        assert result.feasible_count == 2


class TestConstraints:
    def test_min_selected_enforced(self):
        candidates = [
            CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=90.0),
            CandidateRun(run_id=_uuid(2), objective_value=5.0, cost=90.0),
        ]
        # Budget=100, min_selected=2: neither pair fits (180>100). Infeasible.
        with pytest.raises(PortfolioInfeasibleError) as exc_info:
            optimize_portfolio(candidates, budget=100.0, min_selected=2)
        assert exc_info.value.reason_code == "PORTFOLIO_INFEASIBLE"

    def test_max_selected_enforced(self):
        candidates = [
            CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=10.0),
            CandidateRun(run_id=_uuid(2), objective_value=20.0, cost=10.0),
            CandidateRun(run_id=_uuid(3), objective_value=15.0, cost=10.0),
        ]
        # Budget=100 allows all 3, but max_selected=1 limits to 1.
        result = optimize_portfolio(candidates, budget=100.0, max_selected=1)
        assert len(result.selected_run_ids) == 1
        assert result.selected_run_ids == [_uuid(2)]  # highest objective

    def test_group_caps_enforced(self):
        candidates = [
            CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=10.0, group_key="A"),
            CandidateRun(run_id=_uuid(2), objective_value=20.0, cost=10.0, group_key="A"),
            CandidateRun(run_id=_uuid(3), objective_value=15.0, cost=10.0, group_key="B"),
        ]
        # group_caps={"A": 1}: can pick at most 1 from group A.
        # Best: run2 (A, obj=20) + run3 (B, obj=15) = 35
        result = optimize_portfolio(candidates, budget=100.0, group_caps={"A": 1})
        assert set(result.selected_run_ids) == {_uuid(2), _uuid(3)}


class TestValidationErrors:
    def test_empty_candidates(self):
        with pytest.raises(PortfolioConfigError) as exc_info:
            optimize_portfolio([], budget=100.0)
        assert exc_info.value.reason_code == "PORTFOLIO_NO_CANDIDATES"

    def test_duplicate_candidates(self):
        candidates = [
            CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=10.0),
            CandidateRun(run_id=_uuid(1), objective_value=20.0, cost=20.0),
        ]
        with pytest.raises(PortfolioConfigError) as exc_info:
            optimize_portfolio(candidates, budget=100.0)
        assert exc_info.value.reason_code == "PORTFOLIO_DUPLICATE_CANDIDATES"

    def test_candidate_limit_exceeded(self):
        candidates = [
            CandidateRun(run_id=_uuid(i), objective_value=1.0, cost=1.0)
            for i in range(MAX_CANDIDATES + 1)
        ]
        with pytest.raises(PortfolioConfigError) as exc_info:
            optimize_portfolio(candidates, budget=100.0)
        assert exc_info.value.reason_code == "PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED"

    def test_invalid_budget(self):
        candidates = [CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=10.0)]
        with pytest.raises(PortfolioConfigError) as exc_info:
            optimize_portfolio(candidates, budget=0.0)
        assert exc_info.value.reason_code == "PORTFOLIO_INVALID_CONFIG"

    def test_min_selected_below_one(self):
        candidates = [CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=10.0)]
        with pytest.raises(PortfolioConfigError) as exc_info:
            optimize_portfolio(candidates, budget=100.0, min_selected=0)
        assert exc_info.value.reason_code == "PORTFOLIO_INVALID_CONFIG"

    def test_max_selected_below_one(self):
        candidates = [CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=10.0)]
        with pytest.raises(PortfolioConfigError) as exc_info:
            optimize_portfolio(candidates, budget=100.0, max_selected=0)
        assert exc_info.value.reason_code == "PORTFOLIO_INVALID_CONFIG"

    def test_max_selected_less_than_min_selected(self):
        candidates = [CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=10.0)]
        with pytest.raises(PortfolioConfigError) as exc_info:
            optimize_portfolio(candidates, budget=100.0, min_selected=3, max_selected=1)
        assert exc_info.value.reason_code == "PORTFOLIO_INVALID_CONFIG"

    def test_group_cap_below_one(self):
        candidates = [
            CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=10.0, group_key="A"),
        ]
        with pytest.raises(PortfolioConfigError) as exc_info:
            optimize_portfolio(candidates, budget=100.0, group_caps={"A": 0})
        assert exc_info.value.reason_code == "PORTFOLIO_INVALID_CONFIG"

    def test_infeasible_no_subset_fits(self):
        candidates = [
            CandidateRun(run_id=_uuid(1), objective_value=10.0, cost=200.0),
        ]
        with pytest.raises(PortfolioInfeasibleError) as exc_info:
            optimize_portfolio(candidates, budget=100.0)
        assert exc_info.value.reason_code == "PORTFOLIO_INFEASIBLE"
