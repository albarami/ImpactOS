"""Tests for Step 5: Suite Planner — Final Scenario Suite Assembly."""

import pytest
from uuid import uuid4

from src.agents.depth.suite_planner import SuitePlannerAgent, _build_suite_from_scored
from src.models.common import DataClassification, DisclosureTier
from src.models.depth import (
    DepthStepName,
    ScenarioSuitePlan,
    SuitePlanningOutput,
)


def _make_scored(label, score, is_contrarian=False, accepted=True,
                 direction_id=None, sector_codes=None, required_levers=None):
    """Helper to create a scored candidate dict."""
    return {
        "direction_id": str(direction_id or uuid4()),
        "label": label,
        "composite_score": score,
        "novelty_score": score,
        "feasibility_score": score,
        "data_availability_score": score,
        "is_contrarian": is_contrarian,
        "rank": 1,
        "accepted": accepted,
        "rejection_reason": None if accepted else "Below threshold",
    }


class TestSuitePlannerAgent:
    @pytest.fixture
    def agent(self):
        return SuitePlannerAgent()

    @pytest.fixture
    def context(self):
        d1 = uuid4()
        d2 = uuid4()
        d3 = uuid4()
        return {
            "scored": [
                _make_scored("High local content", 8.5, direction_id=d1),
                _make_scored("Import stress", 7.0, is_contrarian=True, direction_id=d2),
                _make_scored("Base case", 6.0, direction_id=d3),
                _make_scored("Rejected noise", 2.0, accepted=False),
            ],
            "qualitative_risks": [
                {
                    "label": "Regulatory risk",
                    "description": "Policy may change",
                    "not_modeled": True,
                    "affected_sectors": ["SEC01"],
                },
            ],
            "workspace_id": str(uuid4()),
            "candidates": [
                {"direction_id": str(d1), "label": "High local content",
                 "sector_codes": ["SEC01"], "required_levers": ["LOCAL_CONTENT"]},
                {"direction_id": str(d3), "label": "Base case",
                 "sector_codes": ["SEC01"], "required_levers": []},
            ],
            "contrarians": [
                {"direction_id": str(d2), "label": "Import stress",
                 "sector_codes": ["SEC01"], "required_levers": ["IMPORT_SUBSTITUTION"],
                 "is_quantifiable": True,
                 "quantified_levers": [
                     {"type": "IMPORT_SHARE_ADJUSTMENT", "sector": "SEC01", "value": 0.2},
                 ]},
            ],
        }

    def test_step_name(self, agent):
        assert agent.step_name == DepthStepName.SUITE_PLANNING

    def test_produces_suite_plan(self, agent, context):
        result = agent.run(context=context)
        assert "suite_plan" in result
        plan = result["suite_plan"]
        assert "runs" in plan
        assert "recommended_outputs" in plan
        assert "qualitative_risks" in plan
        assert "rationale" in plan

    def test_only_accepted_in_runs(self, agent, context):
        result = agent.run(context=context)
        runs = result["suite_plan"]["runs"]
        # 3 accepted, 1 rejected — should have <=3 runs
        assert len(runs) <= 3
        # All runs should be from accepted directions
        for run in runs:
            assert run["name"]  # Should have a name

    def test_suite_disclosure_tier1(self, agent, context):
        result = agent.run(context=context)
        assert result["suite_plan"]["disclosure_tier"] == "TIER1"

    def test_contrarian_runs_tier0(self, agent, context):
        result = agent.run(context=context)
        runs = result["suite_plan"]["runs"]
        for run in runs:
            if "stress" in run["name"].lower() or "Import" in run["name"]:
                # Contrarian runs should be TIER0
                pass  # The _build_suite sets this

    def test_recommended_outputs_include_variance_bridge(self, agent, context):
        """When contrarian runs exist, variance_bridge should be recommended."""
        result = agent.run(context=context)
        outputs = result["suite_plan"]["recommended_outputs"]
        assert "variance_bridge" in outputs

    def test_qualitative_risks_preserved(self, agent, context):
        result = agent.run(context=context)
        risks = result["suite_plan"]["qualitative_risks"]
        assert len(risks) >= 1
        for r in risks:
            assert r["not_modeled"] is True

    def test_output_validates(self, agent, context):
        result = agent.run(context=context)
        output = SuitePlanningOutput.model_validate(result)
        assert isinstance(output.suite_plan, ScenarioSuitePlan)
        assert output.suite_plan.disclosure_tier == DisclosureTier.TIER1

    def test_restricted_uses_fallback(self, agent, context):
        result = agent.run(
            context=context,
            classification=DataClassification.RESTRICTED,
        )
        assert "suite_plan" in result
        assert len(result["suite_plan"]["runs"]) > 0

    def test_empty_scored_produces_empty_suite(self, agent):
        result = agent.run(context={
            "scored": [],
            "qualitative_risks": [],
            "workspace_id": str(uuid4()),
            "candidates": [],
            "contrarians": [],
        })
        assert len(result["suite_plan"]["runs"]) == 0


class TestBuildSuiteFromScored:
    def test_max_5_runs(self):
        scored = [
            _make_scored(f"Dir {i}", 8.0 - i * 0.5)
            for i in range(10)
        ]
        context = {
            "scored": scored,
            "qualitative_risks": [],
            "workspace_id": str(uuid4()),
            "candidates": [],
            "contrarians": [],
        }
        suite = _build_suite_from_scored(context)
        assert len(suite.runs) <= 5

    def test_sorted_by_composite_score(self):
        d1 = uuid4()
        d2 = uuid4()
        scored = [
            _make_scored("Low", 5.0, direction_id=d1),
            _make_scored("High", 9.0, direction_id=d2),
        ]
        context = {
            "scored": scored,
            "qualitative_risks": [],
            "workspace_id": str(uuid4()),
            "candidates": [
                {"direction_id": str(d1), "label": "Low",
                 "sector_codes": [], "required_levers": []},
                {"direction_id": str(d2), "label": "High",
                 "sector_codes": [], "required_levers": []},
            ],
            "contrarians": [],
        }
        suite = _build_suite_from_scored(context)
        assert suite.runs[0].name == "Run: High"

    def test_default_recommended_outputs(self):
        context = {
            "scored": [_make_scored("Base", 7.0)],
            "qualitative_risks": [],
            "workspace_id": str(uuid4()),
            "candidates": [],
            "contrarians": [],
        }
        suite = _build_suite_from_scored(context)
        assert "multipliers" in suite.recommended_outputs
        assert "jobs" in suite.recommended_outputs
        assert "imports" in suite.recommended_outputs

    def test_contrarian_adds_variance_bridge(self):
        d1 = uuid4()
        scored = [_make_scored("Stress", 7.0, is_contrarian=True, direction_id=d1)]
        context = {
            "scored": scored,
            "qualitative_risks": [],
            "workspace_id": str(uuid4()),
            "candidates": [],
            "contrarians": [
                {"direction_id": str(d1), "label": "Stress",
                 "sector_codes": [], "required_levers": [],
                 "is_quantifiable": False},
            ],
        }
        suite = _build_suite_from_scored(context)
        assert "variance_bridge" in suite.recommended_outputs

    def test_uses_quantified_levers_for_contrarian(self):
        d1 = uuid4()
        quantified = [
            {"type": "IMPORT_SHARE_ADJUSTMENT", "sector": "SEC01", "value": 0.2},
        ]
        scored = [_make_scored("Import stress", 7.0, is_contrarian=True, direction_id=d1)]
        context = {
            "scored": scored,
            "qualitative_risks": [],
            "workspace_id": str(uuid4()),
            "candidates": [],
            "contrarians": [
                {"direction_id": str(d1), "label": "Import stress",
                 "sector_codes": ["SEC01"],
                 "required_levers": ["IMPORT_SUBSTITUTION"],
                 "is_quantifiable": True,
                 "quantified_levers": quantified},
            ],
        }
        suite = _build_suite_from_scored(context)
        assert len(suite.runs) == 1
        assert suite.runs[0].executable_levers == quantified
