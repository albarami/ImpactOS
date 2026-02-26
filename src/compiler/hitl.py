"""HITL bulk operations — MVP-4 Sections 9.5, 11.1.

Bulk-approve, bulk-override, defer, escalate. All operations produce
audit trail entries. Deterministic — no LLM calls.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.compiler.mapping_state import MappingState, MappingStateMachine
from src.models.common import utc_now


@dataclass(frozen=True)
class AuditEntry:
    """Immutable audit record for a HITL operation."""

    line_item_id: UUID
    action: str
    from_state: MappingState
    to_state: MappingState
    actor: UUID
    rationale: str
    timestamp: datetime


class HITLService:
    """Bulk HITL operations on mapping state machines."""

    def bulk_approve(
        self,
        *,
        state_machines: list[MappingStateMachine],
        actor: UUID,
        rationale: str,
    ) -> list[AuditEntry]:
        """Bulk-approve all AI_SUGGESTED items.

        Only transitions items currently in AI_SUGGESTED state.
        Items in other states are skipped silently.
        """
        entries: list[AuditEntry] = []
        for sm in state_machines:
            if sm.state != MappingState.AI_SUGGESTED:
                continue
            from_state = sm.state
            sm.transition(MappingState.APPROVED, actor=actor, rationale=rationale)
            entries.append(AuditEntry(
                line_item_id=sm.line_item_id,
                action="BULK_APPROVE",
                from_state=from_state,
                to_state=MappingState.APPROVED,
                actor=actor,
                rationale=rationale,
                timestamp=utc_now(),
            ))
        return entries

    def bulk_override(
        self,
        *,
        state_machines: list[MappingStateMachine],
        actor: UUID,
        rationale: str,
    ) -> list[AuditEntry]:
        """Bulk-override: transition AI_SUGGESTED items to OVERRIDDEN."""
        entries: list[AuditEntry] = []
        for sm in state_machines:
            if sm.state != MappingState.AI_SUGGESTED:
                continue
            from_state = sm.state
            sm.transition(MappingState.OVERRIDDEN, actor=actor, rationale=rationale)
            entries.append(AuditEntry(
                line_item_id=sm.line_item_id,
                action="BULK_OVERRIDE",
                from_state=from_state,
                to_state=MappingState.OVERRIDDEN,
                actor=actor,
                rationale=rationale,
                timestamp=utc_now(),
            ))
        return entries

    def escalate(
        self,
        *,
        state_machines: list[MappingStateMachine],
        actor: UUID,
        rationale: str,
    ) -> list[AuditEntry]:
        """Escalate items to MANAGER_REVIEW."""
        entries: list[AuditEntry] = []
        for sm in state_machines:
            if sm.state not in (MappingState.AI_SUGGESTED, MappingState.OVERRIDDEN):
                continue
            from_state = sm.state
            sm.transition(MappingState.MANAGER_REVIEW, actor=actor, rationale=rationale)
            entries.append(AuditEntry(
                line_item_id=sm.line_item_id,
                action="ESCALATE",
                from_state=from_state,
                to_state=MappingState.MANAGER_REVIEW,
                actor=actor,
                rationale=rationale,
                timestamp=utc_now(),
            ))
        return entries

    @staticmethod
    def count_unresolved(state_machines: list[MappingStateMachine]) -> int:
        """Count items not yet in a resolved state (APPROVED/OVERRIDDEN/LOCKED)."""
        resolved_states = {MappingState.APPROVED, MappingState.OVERRIDDEN, MappingState.LOCKED}
        return sum(1 for sm in state_machines if sm.state not in resolved_states)
