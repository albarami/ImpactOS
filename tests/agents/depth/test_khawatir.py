"""Tests for Step 1: Khawatir — Candidate Direction Generation."""

import pytest

from src.agents.depth.khawatir import KhawatirAgent, _generate_fallback_candidates
from src.models.common import DataClassification
from src.models.depth import CandidateDirection, DepthStepName, KhawatirOutput


class TestKhawatirAgent:
    @pytest.fixture
    def agent(self):
        return KhawatirAgent()

    @pytest.fixture
    def context(self):
        return {
            "workspace_description": "Saudi mega-project economic impact",
            "sector_codes": ["SEC01", "SEC02", "SEC03"],
            "existing_shocks": [],
            "time_horizon": {"start_year": 2025, "end_year": 2035},
        }

    def test_step_name(self, agent):
        assert agent.step_name == DepthStepName.KHAWATIR

    def test_fallback_produces_candidates(self, agent, context):
        result = agent.run(context=context)
        assert "candidates" in result
        assert len(result["candidates"]) >= 3

    def test_fallback_candidates_have_required_fields(self, agent, context):
        result = agent.run(context=context)
        for c in result["candidates"]:
            assert "label" in c
            assert "description" in c
            assert "source_type" in c
            assert c["source_type"] in ("nafs", "waswas", "insight")
            assert "test_plan" in c
            assert "required_levers" in c
            assert "direction_id" in c

    def test_fallback_includes_nafs_and_insight(self, agent, context):
        result = agent.run(context=context)
        source_types = {c["source_type"] for c in result["candidates"]}
        assert "nafs" in source_types
        assert "insight" in source_types

    def test_fallback_assigns_sector_codes(self, agent, context):
        result = agent.run(context=context)
        # At least some candidates should have sector codes from context
        has_sectors = any(
            len(c.get("sector_codes", [])) > 0
            for c in result["candidates"]
        )
        assert has_sectors

    def test_output_validates_as_khawatir_output(self, agent, context):
        result = agent.run(context=context)
        output = KhawatirOutput.model_validate(result)
        assert len(output.candidates) >= 3
        for c in output.candidates:
            assert isinstance(c, CandidateDirection)

    def test_restricted_classification_uses_fallback(self, agent, context):
        """RESTRICTED workspaces use deterministic fallback."""
        result = agent.run(
            context=context,
            classification=DataClassification.RESTRICTED,
        )
        assert len(result["candidates"]) >= 3

    def test_empty_context_still_produces_candidates(self, agent):
        result = agent.run(context={})
        assert len(result["candidates"]) >= 3

    def test_no_llm_client_uses_fallback(self, agent, context):
        result = agent.run(context=context, llm_client=None)
        assert len(result["candidates"]) >= 3


class TestFallbackCandidateGeneration:
    def test_generates_5_candidates(self):
        candidates = _generate_fallback_candidates({
            "sector_codes": ["A", "B"],
        })
        assert len(candidates) == 5

    def test_candidates_use_context_sectors(self):
        candidates = _generate_fallback_candidates({
            "sector_codes": ["SEC01", "SEC02", "SEC03"],
        })
        for c in candidates:
            assert len(c.sector_codes) <= 3

    def test_required_levers_are_valid_types(self):
        valid_levers = {
            "FINAL_DEMAND_SHOCK",
            "IMPORT_SUBSTITUTION",
            "LOCAL_CONTENT",
            "CONSTRAINT_OVERRIDE",
        }
        candidates = _generate_fallback_candidates({})
        for c in candidates:
            for lever in c.required_levers:
                assert lever in valid_levers, f"Invalid lever: {lever}"

    def test_direction_ids_unique(self):
        candidates = _generate_fallback_candidates({})
        ids = [c.direction_id for c in candidates]
        assert len(set(ids)) == len(ids)
