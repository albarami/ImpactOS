"""Tests for Step 4: Muhasaba — Self-Accounting Scoring."""

import pytest
from uuid import uuid4

from src.agents.depth.muhasaba import MuhasabaAgent, _score_all_candidates
from src.models.common import DataClassification
from src.models.depth import DepthStepName, MuhasabaOutput, ScoredCandidate


class TestMuhasabaAgent:
    @pytest.fixture
    def agent(self):
        return MuhasabaAgent()

    @pytest.fixture
    def context(self):
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
                    "label": "Import substitution",
                    "source_type": "insight",
                    "sector_codes": ["SEC01", "SEC02"],
                    "required_levers": ["IMPORT_SUBSTITUTION"],
                },
            ],
            "contrarians": [
                {
                    "direction_id": str(uuid4()),
                    "label": "Import surge",
                    "source_type": "insight",
                    "sector_codes": ["SEC01"],
                    "required_levers": ["IMPORT_SUBSTITUTION"],
                    "is_quantifiable": True,
                    "broken_assumption": "Stable import costs",
                },
            ],
        }

    def test_step_name(self, agent):
        assert agent.step_name == DepthStepName.MUHASABA

    def test_produces_scored_candidates(self, agent, context):
        result = agent.run(context=context)
        assert "scored" in result
        # 2 regular + 1 contrarian = 3 scored
        assert len(result["scored"]) == 3

    def test_scored_have_all_scores(self, agent, context):
        result = agent.run(context=context)
        for s in result["scored"]:
            assert "composite_score" in s
            assert "novelty_score" in s
            assert "feasibility_score" in s
            assert "data_availability_score" in s
            assert 0.0 <= s["composite_score"] <= 10.0
            assert 0.0 <= s["novelty_score"] <= 10.0
            assert 0.0 <= s["feasibility_score"] <= 10.0
            assert 0.0 <= s["data_availability_score"] <= 10.0

    def test_scored_are_ranked(self, agent, context):
        result = agent.run(context=context)
        ranks = [s["rank"] for s in result["scored"]]
        assert sorted(ranks) == list(range(1, len(ranks) + 1))

    def test_scored_by_composite_descending(self, agent, context):
        result = agent.run(context=context)
        scores = [s["composite_score"] for s in result["scored"]]
        assert scores == sorted(scores, reverse=True)

    def test_accepted_and_rejected(self, agent, context):
        result = agent.run(context=context)
        for s in result["scored"]:
            assert "accepted" in s
            assert isinstance(s["accepted"], bool)
            if not s["accepted"]:
                assert s.get("rejection_reason") is not None
                assert len(s["rejection_reason"]) > 0

    def test_contrarian_flag_preserved(self, agent, context):
        result = agent.run(context=context)
        contrarian_count = sum(1 for s in result["scored"] if s["is_contrarian"])
        assert contrarian_count == 1  # 1 contrarian from context

    def test_output_validates(self, agent, context):
        result = agent.run(context=context)
        output = MuhasabaOutput.model_validate(result)
        for sc in output.scored:
            assert isinstance(sc, ScoredCandidate)

    def test_restricted_uses_fallback(self, agent, context):
        result = agent.run(
            context=context,
            classification=DataClassification.RESTRICTED,
        )
        assert len(result["scored"]) == 3


class TestDeterministicScoring:
    def test_nafs_lower_novelty_than_insight(self):
        nafs_dir = {
            "direction_id": str(uuid4()),
            "label": "Nafs",
            "source_type": "nafs",
            "sector_codes": ["A"],
            "required_levers": [],
        }
        insight_dir = {
            "direction_id": str(uuid4()),
            "label": "Insight",
            "source_type": "insight",
            "sector_codes": ["A"],
            "required_levers": ["FINAL_DEMAND_SHOCK"],
        }
        scored = _score_all_candidates({
            "candidates": [nafs_dir, insight_dir],
            "contrarians": [],
        })
        nafs_sc = next(s for s in scored if s.label == "Nafs")
        insight_sc = next(s for s in scored if s.label == "Insight")
        assert nafs_sc.novelty_score < insight_sc.novelty_score

    def test_contrarian_gets_novelty_bonus(self):
        regular = {
            "direction_id": str(uuid4()),
            "label": "Regular",
            "source_type": "insight",
            "sector_codes": ["A"],
            "required_levers": ["FINAL_DEMAND_SHOCK"],
        }
        contrarian = {
            "direction_id": str(uuid4()),
            "label": "Contrarian",
            "source_type": "insight",
            "sector_codes": ["A"],
            "required_levers": ["IMPORT_SUBSTITUTION"],
            "is_quantifiable": True,
        }
        scored = _score_all_candidates({
            "candidates": [regular],
            "contrarians": [contrarian],
        })
        reg_sc = next(s for s in scored if s.label == "Regular")
        con_sc = next(s for s in scored if s.label == "Contrarian")
        assert con_sc.novelty_score > reg_sc.novelty_score

    def test_fewer_levers_higher_feasibility(self):
        few_levers = {
            "direction_id": str(uuid4()),
            "label": "Simple",
            "source_type": "insight",
            "sector_codes": ["A"],
            "required_levers": ["FINAL_DEMAND_SHOCK"],
        }
        many_levers = {
            "direction_id": str(uuid4()),
            "label": "Complex",
            "source_type": "insight",
            "sector_codes": ["A"],
            "required_levers": ["FINAL_DEMAND_SHOCK", "IMPORT_SUBSTITUTION", "LOCAL_CONTENT"],
        }
        scored = _score_all_candidates({
            "candidates": [few_levers, many_levers],
            "contrarians": [],
        })
        simple_sc = next(s for s in scored if s.label == "Simple")
        complex_sc = next(s for s in scored if s.label == "Complex")
        assert simple_sc.feasibility_score > complex_sc.feasibility_score

    def test_with_sectors_higher_data_availability(self):
        with_sectors = {
            "direction_id": str(uuid4()),
            "label": "Has sectors",
            "source_type": "insight",
            "sector_codes": ["A", "B"],
            "required_levers": [],
        }
        without_sectors = {
            "direction_id": str(uuid4()),
            "label": "No sectors",
            "source_type": "insight",
            "sector_codes": [],
            "required_levers": [],
        }
        scored = _score_all_candidates({
            "candidates": [with_sectors, without_sectors],
            "contrarians": [],
        })
        ws = next(s for s in scored if s.label == "Has sectors")
        ns = next(s for s in scored if s.label == "No sectors")
        assert ws.data_availability_score > ns.data_availability_score

    def test_waswas_gets_lowest_novelty(self):
        waswas = {
            "direction_id": str(uuid4()),
            "label": "Noise",
            "source_type": "waswas",
            "sector_codes": [],
            "required_levers": [],
        }
        scored = _score_all_candidates({
            "candidates": [waswas],
            "contrarians": [],
        })
        assert scored[0].novelty_score <= 2.0

    def test_empty_candidates(self):
        scored = _score_all_candidates({
            "candidates": [],
            "contrarians": [],
        })
        assert scored == []
