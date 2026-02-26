"""Assumption registry — MVP-5 Section 3.6.3.

Create/approve/reject assumptions, enforce range requirement on approval,
link assumptions to scenarios and runs, track approval workflow.

Deterministic — no LLM calls.
"""

from collections import Counter
from uuid import UUID

from src.models.common import AssumptionStatus, utc_now
from src.models.governance import Assumption, AssumptionRange


class AssumptionRegistry:
    """In-memory assumption register with approval workflow.

    Production replaces with PostgreSQL-backed store.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, Assumption] = {}
        self._scenario_links: dict[UUID, set[UUID]] = {}  # assumption_id → {scenario_ids}
        self._run_links: dict[UUID, set[UUID]] = {}  # assumption_id → {run_ids}

    # ----- CRUD -----

    def register(self, assumption: Assumption) -> None:
        """Register a new assumption (must be unique)."""
        if assumption.assumption_id in self._store:
            msg = f"Assumption {assumption.assumption_id} already registered."
            raise ValueError(msg)
        self._store[assumption.assumption_id] = assumption

    def get(self, assumption_id: UUID) -> Assumption:
        """Get an assumption by ID. Raises KeyError if not found."""
        try:
            return self._store[assumption_id]
        except KeyError:
            msg = f"Assumption {assumption_id} not found."
            raise KeyError(msg) from None

    def list_all(self) -> list[Assumption]:
        """List all registered assumptions."""
        return list(self._store.values())

    def list_by_status(self, status: AssumptionStatus) -> list[Assumption]:
        """List assumptions filtered by status."""
        return [a for a in self._store.values() if a.status == status]

    def count_by_status(self) -> dict[AssumptionStatus, int]:
        """Count assumptions by status."""
        counts: Counter[AssumptionStatus] = Counter()
        for a in self._store.values():
            counts[a.status] += 1
        return dict(counts)

    # ----- Approval workflow -----

    def approve(
        self,
        assumption_id: UUID,
        range_: AssumptionRange | None,
        actor: UUID,
    ) -> Assumption:
        """Approve an assumption — requires a sensitivity range.

        Raises:
            ValueError: If range is None or assumption is not DRAFT.
        """
        assumption = self.get(assumption_id)

        if assumption.status != AssumptionStatus.DRAFT:
            msg = f"Cannot approve: assumption {assumption_id} is not DRAFT (currently {assumption.status})."
            raise ValueError(msg)

        if range_ is None:
            msg = "Approved assumptions must include a sensitivity range."
            raise ValueError(msg)

        now = utc_now()
        updated = assumption.model_copy(
            update={
                "status": AssumptionStatus.APPROVED,
                "range": range_,
                "approved_by": actor,
                "approved_at": now,
                "updated_at": now,
            }
        )
        self._store[assumption_id] = updated
        return updated

    def reject(self, assumption_id: UUID, actor: UUID) -> Assumption:
        """Reject an assumption.

        Raises:
            ValueError: If assumption is not DRAFT.
        """
        assumption = self.get(assumption_id)

        if assumption.status != AssumptionStatus.DRAFT:
            msg = f"Cannot reject: assumption {assumption_id} is not DRAFT (currently {assumption.status})."
            raise ValueError(msg)

        now = utc_now()
        updated = assumption.model_copy(
            update={
                "status": AssumptionStatus.REJECTED,
                "updated_at": now,
            }
        )
        self._store[assumption_id] = updated
        return updated

    # ----- Linking -----

    def link_to_scenario(self, assumption_id: UUID, scenario_id: UUID) -> None:
        """Link an assumption to a scenario."""
        self.get(assumption_id)  # Validate existence
        self._scenario_links.setdefault(assumption_id, set()).add(scenario_id)

    def link_to_run(self, assumption_id: UUID, run_id: UUID) -> None:
        """Link an assumption to a run."""
        self.get(assumption_id)  # Validate existence
        self._run_links.setdefault(assumption_id, set()).add(run_id)

    def get_scenario_links(self, assumption_id: UUID) -> set[UUID]:
        """Get all scenario IDs linked to an assumption."""
        return self._scenario_links.get(assumption_id, set())

    def get_run_links(self, assumption_id: UUID) -> set[UUID]:
        """Get all run IDs linked to an assumption."""
        return self._run_links.get(assumption_id, set())

    def get_by_scenario(self, scenario_id: UUID) -> list[Assumption]:
        """Get all assumptions linked to a scenario."""
        result: list[Assumption] = []
        for aid, scenarios in self._scenario_links.items():
            if scenario_id in scenarios:
                result.append(self._store[aid])
        return result
