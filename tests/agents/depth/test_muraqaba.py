"""Tests for Step 2: Muraqaba — Bias Register."""

import pytest
from uuid import uuid4

from src.agents.depth.muraqaba import MuraqabaAgent, _detect_biases_heuristically
from src.models.common import DataClassification
from src.models.depth import BiasRegister, DepthStepName, MuraqabaOutput


class TestMuraqabaAgent:
    @pytest.fixture
    def agent(self):
        return MuraqabaAgent()

    @pytest.fixture
    def candidates_context(self):
        return {
            "candidates": [
                {
                    "direction_id": str(uuid4()),
                    "label": "Base case",
                    "source_type": "nafs",
                    "sector_codes": ["SEC01"],
                    "required_levers": [],
                },
                {
                    "direction_id": str(uuid4()),
                    "label": "Import substitution stress",
                    "source_type": "insight",
                    "sector_codes": ["SEC01", "SEC02"],
                    "required_levers": ["IMPORT_SUBSTITUTION"],
                },
                {
                    "direction_id": str(uuid4()),
                    "label": "Local content push",
                    "source_type": "insight",
                    "sector_codes": ["SEC01"],
                    "required_levers": ["LOCAL_CONTENT"],
                },
            ],
        }

    def test_step_name(self, agent):
        assert agent.step_name == DepthStepName.MURAQABA

    def test_produces_bias_register(self, agent, candidates_context):
        result = agent.run(context=candidates_context)
        assert "bias_register" in result
        br = result["bias_register"]
        assert "entries" in br
        assert "overall_bias_risk" in br

    def test_output_validates(self, agent, candidates_context):
        result = agent.run(context=candidates_context)
        output = MuraqabaOutput.model_validate(result)
        assert isinstance(output.bias_register, BiasRegister)

    def test_empty_candidates_returns_empty_register(self, agent):
        result = agent.run(context={"candidates": []})
        assert result["bias_register"]["overall_bias_risk"] == 0.0

    def test_restricted_uses_fallback(self, agent, candidates_context):
        result = agent.run(
            context=candidates_context,
            classification=DataClassification.RESTRICTED,
        )
        assert "bias_register" in result


class TestHeuristicBiasDetection:
    def test_anchoring_with_single_candidate(self):
        candidates = [{"direction_id": str(uuid4()), "label": "Only one"}]
        register = _detect_biases_heuristically(candidates)
        bias_types = {e.bias_type for e in register.entries}
        assert "anchoring" in bias_types
        assert register.overall_bias_risk >= 7.0

    def test_status_quo_all_nafs(self):
        candidates = [
            {"direction_id": str(uuid4()), "label": "Nafs 1", "source_type": "nafs"},
            {"direction_id": str(uuid4()), "label": "Nafs 2", "source_type": "nafs"},
            {"direction_id": str(uuid4()), "label": "Nafs 3", "source_type": "nafs"},
        ]
        register = _detect_biases_heuristically(candidates)
        bias_types = {e.bias_type for e in register.entries}
        assert "status_quo" in bias_types

    def test_optimism_no_stress_scenarios(self):
        candidates = [
            {"direction_id": str(uuid4()), "label": "Growth scenario", "source_type": "insight"},
            {"direction_id": str(uuid4()), "label": "Expansion plan", "source_type": "insight"},
            {"direction_id": str(uuid4()), "label": "New market entry", "source_type": "insight"},
        ]
        register = _detect_biases_heuristically(candidates)
        bias_types = {e.bias_type for e in register.entries}
        assert "optimism" in bias_types

    def test_availability_sector_clustering(self):
        candidates = [
            {"direction_id": str(uuid4()), "label": "A", "source_type": "insight",
             "sector_codes": ["SEC01"]},
            {"direction_id": str(uuid4()), "label": "B", "source_type": "insight",
             "sector_codes": ["SEC01"]},
            {"direction_id": str(uuid4()), "label": "C", "source_type": "insight",
             "sector_codes": ["SEC01"]},
        ]
        register = _detect_biases_heuristically(candidates)
        bias_types = {e.bias_type for e in register.entries}
        assert "availability" in bias_types

    def test_groupthink_same_levers(self):
        candidates = [
            {"direction_id": str(uuid4()), "label": "A", "source_type": "insight",
             "required_levers": ["FINAL_DEMAND_SHOCK"]},
            {"direction_id": str(uuid4()), "label": "B", "source_type": "insight",
             "required_levers": ["FINAL_DEMAND_SHOCK"]},
            {"direction_id": str(uuid4()), "label": "C", "source_type": "insight",
             "required_levers": ["FINAL_DEMAND_SHOCK"]},
        ]
        register = _detect_biases_heuristically(candidates)
        bias_types = {e.bias_type for e in register.entries}
        assert "groupthink" in bias_types

    def test_no_biases_detected(self):
        """Diverse candidates should show minimal bias."""
        candidates = [
            {"direction_id": str(uuid4()), "label": "Base case", "source_type": "nafs",
             "sector_codes": ["SEC01"], "required_levers": []},
            {"direction_id": str(uuid4()), "label": "Import stress test",
             "source_type": "insight",
             "sector_codes": ["SEC02"], "required_levers": ["IMPORT_SUBSTITUTION"]},
            {"direction_id": str(uuid4()), "label": "Capacity constraint",
             "source_type": "insight",
             "sector_codes": ["SEC03"], "required_levers": ["CONSTRAINT_OVERRIDE"]},
        ]
        register = _detect_biases_heuristically(candidates)
        # Should have very few biases
        assert register.overall_bias_risk <= 6.0

    def test_overall_risk_bounded(self):
        """Overall risk should be 0-10."""
        for n_candidates in [0, 1, 3, 10]:
            candidates = [
                {"direction_id": str(uuid4()), "label": f"C{i}", "source_type": "nafs"}
                for i in range(n_candidates)
            ]
            register = _detect_biases_heuristically(candidates)
            assert 0.0 <= register.overall_bias_risk <= 10.0
