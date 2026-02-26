"""ScenarioSpec versioning — MVP-4.

Every mapping change or assumption update creates a new ScenarioSpec version.
Lock mappings for governed runs. Unlock creates new version.

Deterministic — no LLM calls.
"""

from uuid import UUID

from src.compiler.mapping_state import MappingState, MappingStateMachine
from src.models.scenario import ScenarioSpec


# States that count as "resolved" — eligible for locking
_LOCKABLE_STATES = frozenset({MappingState.APPROVED, MappingState.OVERRIDDEN})


class ScenarioVersioningService:
    """Manages ScenarioSpec version history and lock/unlock lifecycle."""

    def __init__(self) -> None:
        # scenario_spec_id → ordered list of versions
        self._versions: dict[UUID, list[ScenarioSpec]] = {}

    def register(self, spec: ScenarioSpec) -> None:
        """Register an initial ScenarioSpec (version 1)."""
        self._versions.setdefault(spec.scenario_spec_id, []).append(spec)

    def get_versions(self, scenario_spec_id: UUID) -> list[ScenarioSpec]:
        """Get all versions of a ScenarioSpec, ordered by version number.

        Raises:
            KeyError: If scenario not found.
        """
        versions = self._versions.get(scenario_spec_id)
        if versions is None:
            msg = f"ScenarioSpec {scenario_spec_id} not found."
            raise KeyError(msg)
        return list(versions)

    def get_latest(self, scenario_spec_id: UUID) -> ScenarioSpec:
        """Get the latest version.

        Raises:
            KeyError: If scenario not found.
        """
        versions = self.get_versions(scenario_spec_id)
        return versions[-1]

    def record_change(
        self,
        scenario_spec_id: UUID,
        change_description: str,
        actor: UUID,
    ) -> ScenarioSpec:
        """Record a mapping or assumption change → new version.

        Returns:
            The new ScenarioSpec version.
        """
        latest = self.get_latest(scenario_spec_id)
        new_spec = latest.next_version()
        self._versions[scenario_spec_id].append(new_spec)
        return new_spec

    def lock(
        self,
        scenario_spec_id: UUID,
        state_machines: list[MappingStateMachine],
        actor: UUID,
    ) -> ScenarioSpec:
        """Lock all mappings for a governed run.

        All state machines must be in APPROVED or OVERRIDDEN state.
        Transitions them to LOCKED and creates a new ScenarioSpec version.

        Raises:
            ValueError: If any mappings are unresolved.
        """
        # Check all are in lockable state
        for sm in state_machines:
            if sm.state not in _LOCKABLE_STATES:
                msg = (
                    f"Cannot lock: {len([s for s in state_machines if s.state not in _LOCKABLE_STATES])} "
                    f"unresolved mapping(s). All must be APPROVED or OVERRIDDEN."
                )
                raise ValueError(msg)

        # Transition all to LOCKED
        for sm in state_machines:
            sm.transition(MappingState.LOCKED, actor=actor, rationale="Locked for governed run")

        return self.record_change(scenario_spec_id, "Locked for governed run", actor)

    def unlock(
        self,
        scenario_spec_id: UUID,
        state_machines: list[MappingStateMachine],
        actor: UUID,
    ) -> ScenarioSpec:
        """Unlock mappings — creates a new ScenarioSpec version.

        Transitions LOCKED items back to APPROVED.
        """
        for sm in state_machines:
            if sm.state == MappingState.LOCKED:
                sm.transition(MappingState.APPROVED, actor=actor, rationale="Unlocked for editing")

        return self.record_change(scenario_spec_id, "Unlocked for editing", actor)
