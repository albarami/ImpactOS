"""Constraint set persistence — store interface + implementations.

Amendment 8: DB-backed persistence for real app.

- ConstraintSetStore: abstract interface
- InMemoryConstraintSetStore: for tests only
- DB-backed: follows existing repository patterns (when DB layer exists)

Constraint sets are workspace-scoped and versioned. They're captured
in RunSnapshot for reproducibility.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.engine.constraints.schema import ConstraintSet


class ConstraintSetStore(ABC):
    """Abstract interface for constraint set persistence."""

    @abstractmethod
    def save(self, constraint_set: ConstraintSet) -> None:
        """Persist a constraint set."""

    @abstractmethod
    def get(self, constraint_set_id: UUID) -> ConstraintSet | None:
        """Retrieve a constraint set by ID."""

    @abstractmethod
    def get_by_workspace(self, workspace_id: UUID) -> list[ConstraintSet]:
        """Get all constraint sets for a workspace."""

    @abstractmethod
    def list_all(self) -> list[ConstraintSet]:
        """List all constraint sets."""


class InMemoryConstraintSetStore(ConstraintSetStore):
    """In-memory constraint set store for testing.

    NOT for production use. The DB-backed implementation follows
    existing repository patterns (DepthPlanRepository, etc.).
    """

    def __init__(self) -> None:
        self._store: dict[UUID, ConstraintSet] = {}

    def save(self, constraint_set: ConstraintSet) -> None:
        """Persist a constraint set in memory."""
        self._store[constraint_set.constraint_set_id] = constraint_set

    def get(self, constraint_set_id: UUID) -> ConstraintSet | None:
        """Retrieve a constraint set by ID."""
        return self._store.get(constraint_set_id)

    def get_by_workspace(self, workspace_id: UUID) -> list[ConstraintSet]:
        """Get all constraint sets for a workspace."""
        return [
            cs for cs in self._store.values()
            if cs.workspace_id == workspace_id
        ]

    def list_all(self) -> list[ConstraintSet]:
        """List all constraint sets."""
        return list(self._store.values())
