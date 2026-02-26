"""Tests for ScenarioSpec versioning (MVP-4).

Covers: new version on mapping change, lock for governed runs,
unlock creates new version.
"""

import pytest
from uuid_extensions import uuid7

from src.compiler.mapping_state import MappingState, MappingStateMachine
from src.compiler.versioning import ScenarioVersioningService
from src.models.scenario import ScenarioSpec, TimeHorizon


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACTOR_ID = uuid7()


def _make_scenario_spec(**overrides: object) -> ScenarioSpec:
    defaults: dict[str, object] = {
        "name": "NEOM Test",
        "workspace_id": uuid7(),
        "base_model_version_id": uuid7(),
        "base_year": 2023,
        "time_horizon": TimeHorizon(start_year=2026, end_year=2030),
    }
    defaults.update(overrides)
    return ScenarioSpec(**defaults)  # type: ignore[arg-type]


def _make_approved_sm() -> MappingStateMachine:
    sm = MappingStateMachine(line_item_id=uuid7())
    sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="AI")
    sm.transition(MappingState.APPROVED, actor=ACTOR_ID, rationale="Approved")
    return sm


# ===================================================================
# Version on mapping change
# ===================================================================


class TestVersionOnChange:
    """Every mapping/assumption change creates new version."""

    def test_record_change_creates_new_version(self) -> None:
        spec = _make_scenario_spec()
        svc = ScenarioVersioningService()
        svc.register(spec)

        new_spec = svc.record_change(
            scenario_spec_id=spec.scenario_spec_id,
            change_description="Updated mapping for C41",
            actor=ACTOR_ID,
        )
        assert new_spec.version == 2
        assert new_spec.scenario_spec_id == spec.scenario_spec_id

    def test_multiple_changes_increment(self) -> None:
        spec = _make_scenario_spec()
        svc = ScenarioVersioningService()
        svc.register(spec)

        v2 = svc.record_change(spec.scenario_spec_id, "change 1", ACTOR_ID)
        v3 = svc.record_change(spec.scenario_spec_id, "change 2", ACTOR_ID)
        assert v3.version == 3

    def test_change_updates_timestamp(self) -> None:
        spec = _make_scenario_spec()
        svc = ScenarioVersioningService()
        svc.register(spec)

        new_spec = svc.record_change(spec.scenario_spec_id, "change", ACTOR_ID)
        assert new_spec.updated_at >= spec.updated_at

    def test_change_preserves_identity(self) -> None:
        spec = _make_scenario_spec()
        svc = ScenarioVersioningService()
        svc.register(spec)

        new_spec = svc.record_change(spec.scenario_spec_id, "change", ACTOR_ID)
        assert new_spec.scenario_spec_id == spec.scenario_spec_id
        assert new_spec.name == spec.name
        assert new_spec.workspace_id == spec.workspace_id


# ===================================================================
# Lock for governed run
# ===================================================================


class TestLockForGovernedRun:
    """Lock mappings for a governed run snapshot."""

    def test_lock_transitions_mappings(self) -> None:
        spec = _make_scenario_spec()
        machines = [_make_approved_sm() for _ in range(3)]
        svc = ScenarioVersioningService()
        svc.register(spec)

        locked_spec = svc.lock(
            scenario_spec_id=spec.scenario_spec_id,
            state_machines=machines,
            actor=ACTOR_ID,
        )
        for sm in machines:
            assert sm.state == MappingState.LOCKED
        assert locked_spec.version == 2

    def test_lock_fails_with_unresolved(self) -> None:
        """Cannot lock if any items are still UNMAPPED."""
        spec = _make_scenario_spec()
        machines = [
            _make_approved_sm(),
            MappingStateMachine(line_item_id=uuid7()),  # UNMAPPED
        ]
        svc = ScenarioVersioningService()
        svc.register(spec)

        with pytest.raises(ValueError, match="unresolved"):
            svc.lock(
                scenario_spec_id=spec.scenario_spec_id,
                state_machines=machines,
                actor=ACTOR_ID,
            )

    def test_lock_fails_with_ai_suggested(self) -> None:
        spec = _make_scenario_spec()
        sm = MappingStateMachine(line_item_id=uuid7())
        sm.transition(MappingState.AI_SUGGESTED, actor=ACTOR_ID, rationale="AI")
        svc = ScenarioVersioningService()
        svc.register(spec)

        with pytest.raises(ValueError, match="unresolved"):
            svc.lock(
                scenario_spec_id=spec.scenario_spec_id,
                state_machines=[sm],
                actor=ACTOR_ID,
            )


# ===================================================================
# Unlock creates new version
# ===================================================================


class TestUnlock:
    """Unlocking creates new ScenarioSpec version."""

    def test_unlock_creates_new_version(self) -> None:
        spec = _make_scenario_spec()
        machines = [_make_approved_sm()]
        svc = ScenarioVersioningService()
        svc.register(spec)

        locked = svc.lock(
            scenario_spec_id=spec.scenario_spec_id,
            state_machines=machines,
            actor=ACTOR_ID,
        )
        assert locked.version == 2

        unlocked = svc.unlock(
            scenario_spec_id=spec.scenario_spec_id,
            state_machines=machines,
            actor=ACTOR_ID,
        )
        assert unlocked.version == 3
        for sm in machines:
            assert sm.state in (MappingState.APPROVED, MappingState.OVERRIDDEN)

    def test_unlock_transitions_to_approved(self) -> None:
        spec = _make_scenario_spec()
        machines = [_make_approved_sm()]
        svc = ScenarioVersioningService()
        svc.register(spec)

        svc.lock(spec.scenario_spec_id, machines, ACTOR_ID)
        svc.unlock(spec.scenario_spec_id, machines, ACTOR_ID)
        for sm in machines:
            assert sm.state == MappingState.APPROVED


# ===================================================================
# Version history
# ===================================================================


class TestVersionHistory:
    """Service tracks all versions."""

    def test_get_versions(self) -> None:
        spec = _make_scenario_spec()
        svc = ScenarioVersioningService()
        svc.register(spec)
        svc.record_change(spec.scenario_spec_id, "change 1", ACTOR_ID)
        svc.record_change(spec.scenario_spec_id, "change 2", ACTOR_ID)

        versions = svc.get_versions(spec.scenario_spec_id)
        assert len(versions) == 3
        assert versions[0].version == 1
        assert versions[-1].version == 3

    def test_get_latest(self) -> None:
        spec = _make_scenario_spec()
        svc = ScenarioVersioningService()
        svc.register(spec)
        svc.record_change(spec.scenario_spec_id, "change", ACTOR_ID)

        latest = svc.get_latest(spec.scenario_spec_id)
        assert latest.version == 2

    def test_get_nonexistent_raises(self) -> None:
        svc = ScenarioVersioningService()
        with pytest.raises(KeyError):
            svc.get_latest(uuid7())
