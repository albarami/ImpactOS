"""Tests for assumption drafting agent (MVP-8).

Covers: draft assumptions for residual buckets, ambiguous mappings,
structured output with value/range/units/justification, DRAFT status
only — human must approve.
"""

import pytest
from uuid_extensions import uuid7

from src.agents.assumption_agent import (
    AssumptionDraft,
    AssumptionDraftAgent,
    ResidualContext,
)
from src.models.common import AssumptionStatus, AssumptionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_residual_context() -> ResidualContext:
    return ResidualContext(
        sector_code="F",
        description="Uncovered construction spend from BoQ gap",
        total_value=5_000_000.0,
        currency="SAR",
        coverage_pct=0.75,
    )


# ===================================================================
# Draft assumptions for residual buckets
# ===================================================================


class TestResidualAssumption:
    """Draft assumptions for residual/uncovered spend buckets."""

    def test_draft_import_share(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_import_share(
            context=_make_residual_context(),
            default_domestic=0.65,
        )
        assert isinstance(draft, AssumptionDraft)
        assert draft.assumption_type == AssumptionType.IMPORT_SHARE

    def test_draft_has_value(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_import_share(
            context=_make_residual_context(),
            default_domestic=0.65,
        )
        assert draft.value == pytest.approx(0.35)  # 1 - 0.65

    def test_draft_has_range(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_import_share(
            context=_make_residual_context(),
            default_domestic=0.65,
        )
        assert draft.range_min is not None
        assert draft.range_max is not None
        assert draft.range_min <= draft.value <= draft.range_max

    def test_draft_has_justification(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_import_share(
            context=_make_residual_context(),
            default_domestic=0.65,
        )
        assert len(draft.justification) > 0

    def test_draft_status_is_draft(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_import_share(
            context=_make_residual_context(),
            default_domestic=0.65,
        )
        assert draft.status == AssumptionStatus.DRAFT


# ===================================================================
# Draft phasing assumptions
# ===================================================================


class TestPhasingAssumption:
    """Draft phasing assumptions for multi-year scenarios."""

    def test_draft_phasing(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_phasing(
            context=_make_residual_context(),
            years=[2026, 2027, 2028, 2029, 2030],
        )
        assert draft.assumption_type == AssumptionType.PHASING
        assert draft.units == "profile"

    def test_phasing_has_value(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_phasing(
            context=_make_residual_context(),
            years=[2026, 2027, 2028],
        )
        # Value represents the number of years
        assert draft.value > 0

    def test_phasing_has_justification(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_phasing(
            context=_make_residual_context(),
            years=[2026, 2027, 2028],
        )
        assert "phas" in draft.justification.lower()


# ===================================================================
# Generic assumption drafting
# ===================================================================


class TestGenericDraft:
    """Draft generic assumptions from context."""

    def test_draft_generic(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_generic(
            assumption_type=AssumptionType.WAGE_PROXY,
            value=45000.0,
            units="SAR/year",
            justification="Average wage proxy for construction sector.",
        )
        assert draft.assumption_type == AssumptionType.WAGE_PROXY
        assert draft.value == 45000.0
        assert draft.status == AssumptionStatus.DRAFT

    def test_draft_generic_has_range(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_generic(
            assumption_type=AssumptionType.WAGE_PROXY,
            value=45000.0,
            units="SAR/year",
            justification="Average wage proxy.",
            range_pct=0.20,
        )
        assert draft.range_min == pytest.approx(36000.0)
        assert draft.range_max == pytest.approx(54000.0)


# ===================================================================
# Convert to governance Assumption
# ===================================================================


class TestConvertToAssumption:
    """Convert draft to governed Assumption model."""

    def test_to_assumption(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_import_share(
            context=_make_residual_context(),
            default_domestic=0.65,
        )
        assumption = draft.to_assumption()
        assert assumption.status == AssumptionStatus.DRAFT
        assert assumption.type == AssumptionType.IMPORT_SHARE
        assert assumption.value == draft.value

    def test_to_assumption_preserves_justification(self) -> None:
        agent = AssumptionDraftAgent()
        draft = agent.draft_import_share(
            context=_make_residual_context(),
            default_domestic=0.65,
        )
        assumption = draft.to_assumption()
        assert assumption.justification == draft.justification


# ===================================================================
# LLM prompt for AI-assisted drafting
# ===================================================================


class TestAssumptionPrompt:
    """Build prompts for LLM-assisted assumption drafting."""

    def test_prompt_includes_context(self) -> None:
        agent = AssumptionDraftAgent()
        context = _make_residual_context()
        prompt = agent.build_assumption_prompt(context)
        assert "F" in prompt
        assert "construction" in prompt.lower() or "uncovered" in prompt.lower()

    def test_prompt_includes_coverage(self) -> None:
        agent = AssumptionDraftAgent()
        context = _make_residual_context()
        prompt = agent.build_assumption_prompt(context)
        assert "75" in prompt or "0.75" in prompt
