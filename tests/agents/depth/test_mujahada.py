"""Tests for Step 3: Mujahada — Contrarian Challenge."""

import pytest
from uuid import uuid4

from src.agents.depth.mujahada import MujahadaAgent, _generate_fallback_contrarians
from src.models.common import DataClassification
from src.models.depth import (
    ContrarianDirection,
    DepthStepName,
    MujahadaOutput,
    QualitativeRisk,
)


class TestMujahadaAgent:
    @pytest.fixture
    def agent(self):
        return MujahadaAgent()

    @pytest.fixture
    def context(self):
        return {
            "candidates": [
                {"direction_id": str(uuid4()), "label": "Base case", "source_type": "nafs"},
                {"direction_id": str(uuid4()), "label": "Growth", "source_type": "insight"},
            ],
            "bias_register": {"entries": [], "overall_bias_risk": 2.0},
            "sector_codes": ["SEC01", "SEC02"],
        }

    def test_step_name(self, agent):
        assert agent.step_name == DepthStepName.MUJAHADA

    def test_produces_contrarians_and_risks(self, agent, context):
        result = agent.run(context=context)
        assert "contrarians" in result
        assert "qualitative_risks" in result
        assert len(result["contrarians"]) >= 2
        assert len(result["qualitative_risks"]) >= 1

    def test_contrarians_have_broken_assumption(self, agent, context):
        result = agent.run(context=context)
        for c in result["contrarians"]:
            assert "broken_assumption" in c
            assert len(c["broken_assumption"]) > 0

    def test_contrarians_have_quantifiability(self, agent, context):
        result = agent.run(context=context)
        for c in result["contrarians"]:
            assert "is_quantifiable" in c
            assert isinstance(c["is_quantifiable"], bool)

    def test_quantifiable_contrarians_have_levers(self, agent, context):
        result = agent.run(context=context)
        for c in result["contrarians"]:
            if c["is_quantifiable"]:
                assert c.get("quantified_levers") is not None
                assert len(c["quantified_levers"]) > 0

    def test_qualitative_risks_not_modeled(self, agent, context):
        result = agent.run(context=context)
        for r in result["qualitative_risks"]:
            assert r["not_modeled"] is True

    def test_output_validates(self, agent, context):
        result = agent.run(context=context)
        output = MujahadaOutput.model_validate(result)
        for c in output.contrarians:
            assert isinstance(c, ContrarianDirection)
        for r in output.qualitative_risks:
            assert isinstance(r, QualitativeRisk)
            assert r.not_modeled is True

    def test_restricted_uses_fallback(self, agent, context):
        result = agent.run(
            context=context,
            classification=DataClassification.RESTRICTED,
        )
        assert len(result["contrarians"]) >= 2


class TestFallbackContrarians:
    def test_generates_3_contrarians(self):
        contrarians, risks = _generate_fallback_contrarians(
            {"sector_codes": ["A", "B"]}
        )
        assert len(contrarians) == 3

    def test_generates_2_qualitative_risks(self):
        contrarians, risks = _generate_fallback_contrarians({})
        assert len(risks) == 2

    def test_contrarian_ids_unique(self):
        contrarians, _ = _generate_fallback_contrarians({})
        ids = [c.direction_id for c in contrarians]
        assert len(set(ids)) == len(ids)

    def test_risk_ids_unique(self):
        _, risks = _generate_fallback_contrarians({})
        ids = [r.risk_id for r in risks]
        assert len(set(ids)) == len(ids)

    def test_contrarian_templates_cover_stress_types(self):
        contrarians, _ = _generate_fallback_contrarians({})
        labels = {c.label.lower() for c in contrarians}
        # Should cover import, phasing, and local content stress tests
        assert any("import" in l for l in labels)
        assert any("phasing" in l or "delay" in l for l in labels)
        assert any("local content" in l or "capacity" in l for l in labels)

    def test_uses_context_sectors(self):
        contrarians, risks = _generate_fallback_contrarians(
            {"sector_codes": ["SEC01", "SEC02", "SEC03"]}
        )
        for c in contrarians:
            assert len(c.sector_codes) <= 3
        for r in risks:
            assert len(r.affected_sectors) <= 3
