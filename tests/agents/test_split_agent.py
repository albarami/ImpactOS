"""Tests for domestic/import split agent (MVP-8).

Covers: split proposal by sector, structured output validation,
library defaults fallback, assumption rationale, sum-to-one constraint.
"""

import pytest
from uuid_extensions import uuid7

from src.agents.split_agent import (
    SplitAgent,
    SplitProposal,
    SplitDefaults,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_defaults() -> list[SplitDefaults]:
    return [
        SplitDefaults(sector_code="F", domestic_share=0.65, import_share=0.35, source="GASTAT 2023"),
        SplitDefaults(sector_code="H", domestic_share=0.80, import_share=0.20, source="GASTAT 2023"),
        SplitDefaults(sector_code="C", domestic_share=0.40, import_share=0.60, source="GASTAT 2023"),
        SplitDefaults(sector_code="J", domestic_share=0.30, import_share=0.70, source="GASTAT 2023"),
    ]


# ===================================================================
# Split proposal using library defaults
# ===================================================================


class TestSplitDefaults:
    """Use sector defaults for domestic/import split."""

    def test_known_sector_uses_default(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        proposal = agent.propose_split(sector_code="F", line_item_text="concrete works")
        assert proposal.domestic_share == pytest.approx(0.65)
        assert proposal.import_share == pytest.approx(0.35)

    def test_unknown_sector_uses_fallback(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        proposal = agent.propose_split(sector_code="Z", line_item_text="unknown item")
        # Should use global fallback
        assert proposal.domestic_share + proposal.import_share == pytest.approx(1.0)

    def test_shares_sum_to_one(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        for sector in ["F", "H", "C", "J"]:
            proposal = agent.propose_split(sector_code=sector, line_item_text="test")
            assert proposal.domestic_share + proposal.import_share == pytest.approx(1.0)


# ===================================================================
# Split proposal validation
# ===================================================================


class TestSplitValidation:
    """Ensure output is structured and valid."""

    def test_proposal_type(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        proposal = agent.propose_split(sector_code="F", line_item_text="concrete")
        assert isinstance(proposal, SplitProposal)

    def test_proposal_has_rationale(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        proposal = agent.propose_split(sector_code="F", line_item_text="concrete")
        assert len(proposal.rationale) > 0

    def test_proposal_has_source(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        proposal = agent.propose_split(sector_code="F", line_item_text="concrete")
        assert len(proposal.source) > 0

    def test_confidence_in_range(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        proposal = agent.propose_split(sector_code="F", line_item_text="concrete")
        assert 0.0 <= proposal.confidence <= 1.0


# ===================================================================
# Batch split proposals
# ===================================================================


class TestBatchSplit:
    """Batch split proposals for multiple items."""

    def test_batch_returns_all(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        items = [
            ("F", "concrete works"),
            ("H", "transport services"),
            ("J", "software development"),
        ]
        proposals = agent.propose_batch(items)
        assert len(proposals) == 3

    def test_batch_preserves_order(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        items = [("F", "concrete"), ("H", "transport")]
        proposals = agent.propose_batch(items)
        assert proposals[0].sector_code == "F"
        assert proposals[1].sector_code == "H"

    def test_empty_batch(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        proposals = agent.propose_batch([])
        assert len(proposals) == 0


# ===================================================================
# LLM prompt for AI-assisted split
# ===================================================================


class TestSplitPrompt:
    """Build prompts for LLM-assisted split estimation."""

    def test_prompt_includes_sector(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        prompt = agent.build_split_prompt(sector_code="F", line_item_text="concrete works")
        assert "F" in prompt

    def test_prompt_includes_item_text(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        prompt = agent.build_split_prompt(sector_code="F", line_item_text="concrete works")
        assert "concrete works" in prompt

    def test_prompt_includes_default_if_available(self) -> None:
        agent = SplitAgent(defaults=_make_defaults())
        prompt = agent.build_split_prompt(sector_code="F", line_item_text="concrete works")
        assert "0.65" in prompt or "65" in prompt


# ===================================================================
# Fallback behavior
# ===================================================================


class TestFallback:
    """Falls back to defaults when LLM unavailable."""

    def test_no_defaults_uses_global_fallback(self) -> None:
        agent = SplitAgent(defaults=[])
        proposal = agent.propose_split(sector_code="F", line_item_text="concrete")
        assert proposal.domestic_share + proposal.import_share == pytest.approx(1.0)
        assert proposal.confidence < 0.5  # Low confidence fallback

    def test_fallback_rationale_mentions_default(self) -> None:
        agent = SplitAgent(defaults=[])
        proposal = agent.propose_split(sector_code="F", line_item_text="concrete")
        assert "default" in proposal.rationale.lower() or "fallback" in proposal.rationale.lower()
