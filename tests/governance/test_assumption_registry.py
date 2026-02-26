"""Tests for assumption registry (MVP-5).

Covers: create/approve/reject assumptions, enforce range on approval,
link to scenarios and runs, track approval workflow.
"""

import pytest
from uuid_extensions import uuid7

from src.governance.assumption_registry import AssumptionRegistry
from src.models.common import AssumptionStatus, AssumptionType
from src.models.governance import Assumption, AssumptionRange


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACTOR_ID = uuid7()
SCENARIO_ID = uuid7()
RUN_ID = uuid7()


def _make_draft_assumption(**overrides: object) -> Assumption:
    defaults: dict[str, object] = {
        "type": AssumptionType.IMPORT_SHARE,
        "value": 0.35,
        "units": "ratio",
        "justification": "Based on historical trade data for Saudi construction sector.",
    }
    defaults.update(overrides)
    return Assumption(**defaults)  # type: ignore[arg-type]


# ===================================================================
# Create assumptions
# ===================================================================


class TestCreateAssumption:
    """Register new assumptions."""

    def test_create_stores_assumption(self) -> None:
        registry = AssumptionRegistry()
        assumption = _make_draft_assumption()
        registry.register(assumption)
        retrieved = registry.get(assumption.assumption_id)
        assert retrieved.assumption_id == assumption.assumption_id

    def test_create_default_status_draft(self) -> None:
        registry = AssumptionRegistry()
        assumption = _make_draft_assumption()
        registry.register(assumption)
        assert registry.get(assumption.assumption_id).status == AssumptionStatus.DRAFT

    def test_create_duplicate_raises(self) -> None:
        registry = AssumptionRegistry()
        assumption = _make_draft_assumption()
        registry.register(assumption)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(assumption)

    def test_get_nonexistent_raises(self) -> None:
        registry = AssumptionRegistry()
        with pytest.raises(KeyError):
            registry.get(uuid7())


# ===================================================================
# Approve assumptions
# ===================================================================


class TestApproveAssumption:
    """Approve with range requirement."""

    def test_approve_with_range(self) -> None:
        registry = AssumptionRegistry()
        assumption = _make_draft_assumption()
        registry.register(assumption)
        approved = registry.approve(
            assumption_id=assumption.assumption_id,
            range_=AssumptionRange(min=0.25, max=0.45),
            actor=ACTOR_ID,
        )
        assert approved.status == AssumptionStatus.APPROVED
        assert approved.range is not None
        assert approved.range.min == 0.25
        assert approved.range.max == 0.45

    def test_approve_records_actor(self) -> None:
        registry = AssumptionRegistry()
        assumption = _make_draft_assumption()
        registry.register(assumption)
        approved = registry.approve(
            assumption_id=assumption.assumption_id,
            range_=AssumptionRange(min=0.25, max=0.45),
            actor=ACTOR_ID,
        )
        assert approved.approved_by == ACTOR_ID
        assert approved.approved_at is not None

    def test_approve_without_range_raises(self) -> None:
        registry = AssumptionRegistry()
        assumption = _make_draft_assumption()
        registry.register(assumption)
        with pytest.raises(ValueError, match="range"):
            registry.approve(
                assumption_id=assumption.assumption_id,
                range_=None,
                actor=ACTOR_ID,
            )

    def test_approve_already_approved_raises(self) -> None:
        registry = AssumptionRegistry()
        assumption = _make_draft_assumption()
        registry.register(assumption)
        registry.approve(
            assumption_id=assumption.assumption_id,
            range_=AssumptionRange(min=0.2, max=0.5),
            actor=ACTOR_ID,
        )
        with pytest.raises(ValueError, match="not DRAFT"):
            registry.approve(
                assumption_id=assumption.assumption_id,
                range_=AssumptionRange(min=0.2, max=0.5),
                actor=ACTOR_ID,
            )


# ===================================================================
# Reject assumptions
# ===================================================================


class TestRejectAssumption:
    """Reject assumptions."""

    def test_reject_draft(self) -> None:
        registry = AssumptionRegistry()
        assumption = _make_draft_assumption()
        registry.register(assumption)
        rejected = registry.reject(
            assumption_id=assumption.assumption_id,
            actor=ACTOR_ID,
        )
        assert rejected.status == AssumptionStatus.REJECTED

    def test_reject_already_rejected_raises(self) -> None:
        registry = AssumptionRegistry()
        assumption = _make_draft_assumption()
        registry.register(assumption)
        registry.reject(assumption_id=assumption.assumption_id, actor=ACTOR_ID)
        with pytest.raises(ValueError, match="not DRAFT"):
            registry.reject(assumption_id=assumption.assumption_id, actor=ACTOR_ID)


# ===================================================================
# Link to scenarios and runs
# ===================================================================


class TestLinkAssumptions:
    """Link assumptions to scenarios and runs."""

    def test_link_to_scenario(self) -> None:
        registry = AssumptionRegistry()
        assumption = _make_draft_assumption()
        registry.register(assumption)
        registry.link_to_scenario(assumption.assumption_id, SCENARIO_ID)
        links = registry.get_scenario_links(assumption.assumption_id)
        assert SCENARIO_ID in links

    def test_link_to_run(self) -> None:
        registry = AssumptionRegistry()
        assumption = _make_draft_assumption()
        registry.register(assumption)
        registry.link_to_run(assumption.assumption_id, RUN_ID)
        links = registry.get_run_links(assumption.assumption_id)
        assert RUN_ID in links

    def test_get_assumptions_for_scenario(self) -> None:
        registry = AssumptionRegistry()
        a1 = _make_draft_assumption()
        a2 = _make_draft_assumption()
        registry.register(a1)
        registry.register(a2)
        registry.link_to_scenario(a1.assumption_id, SCENARIO_ID)
        registry.link_to_scenario(a2.assumption_id, SCENARIO_ID)
        assumptions = registry.get_by_scenario(SCENARIO_ID)
        assert len(assumptions) == 2


# ===================================================================
# List and filter
# ===================================================================


class TestListAndFilter:
    """List all assumptions, filter by status."""

    def test_list_all(self) -> None:
        registry = AssumptionRegistry()
        a1 = _make_draft_assumption()
        a2 = _make_draft_assumption()
        registry.register(a1)
        registry.register(a2)
        assert len(registry.list_all()) == 2

    def test_filter_by_status(self) -> None:
        registry = AssumptionRegistry()
        a1 = _make_draft_assumption()
        a2 = _make_draft_assumption()
        registry.register(a1)
        registry.register(a2)
        registry.approve(
            a1.assumption_id,
            range_=AssumptionRange(min=0.2, max=0.5),
            actor=ACTOR_ID,
        )
        approved = registry.list_by_status(AssumptionStatus.APPROVED)
        assert len(approved) == 1
        assert approved[0].assumption_id == a1.assumption_id

    def test_count_by_status(self) -> None:
        registry = AssumptionRegistry()
        a1 = _make_draft_assumption()
        a2 = _make_draft_assumption()
        a3 = _make_draft_assumption()
        registry.register(a1)
        registry.register(a2)
        registry.register(a3)
        registry.approve(
            a1.assumption_id,
            range_=AssumptionRange(min=0.2, max=0.5),
            actor=ACTOR_ID,
        )
        registry.reject(a2.assumption_id, actor=ACTOR_ID)
        counts = registry.count_by_status()
        assert counts[AssumptionStatus.APPROVED] == 1
        assert counts[AssumptionStatus.REJECTED] == 1
        assert counts[AssumptionStatus.DRAFT] == 1
