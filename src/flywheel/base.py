"""Generic VersionedLibraryManager base class for the Knowledge Flywheel.

All three versioned library managers (Mapping, Assumption, Workforce) inherit
from ``VersionedLibraryManager``. The generic base prevents code duplication
by handling:

- Monotonically increasing version numbers (starting at 1)
- Draft-status validation (REJECTED drafts cannot be published)
- Store delegation (save, get, list, active-version tracking)

Subclasses implement two abstract methods:
- ``_make_version`` -- build a frozen version object from a draft
- ``_get_draft_status`` -- extract the DraftStatus from a draft
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from src.flywheel.models import DraftStatus
from src.flywheel.stores import VersionedLibraryStore

TEntry = TypeVar("TEntry")
TDraft = TypeVar("TDraft")
TVersion = TypeVar("TVersion")


class VersionedLibraryManager(ABC, Generic[TEntry, TDraft, TVersion]):
    """Generic base for all versioned library managers.

    Parameters
    ----------
    store:
        The backing store for persisting published versions.
    """

    def __init__(self, store: VersionedLibraryStore[TVersion]) -> None:
        self._store = store
        self._next_version_number: int = 1

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def get_active_version(self) -> TVersion | None:
        """Return the currently active version, or ``None`` if nothing published."""
        return self._store.get_active()

    def get_version(self, version_id: UUID) -> TVersion | None:
        """Return a specific historical version by id, or ``None``."""
        return self._store.get_version(version_id)

    def list_versions(self) -> list[TVersion]:
        """Return all published versions."""
        return self._store.list_versions()

    # ------------------------------------------------------------------
    # Publish workflow
    # ------------------------------------------------------------------

    def publish(
        self,
        draft: TDraft,
        published_by: UUID,
        quality_gate: dict[str, object] | None = None,
    ) -> TVersion:
        """Validate a draft, create an immutable version, and set it as active.

        Parameters
        ----------
        draft:
            The draft bundle to publish.
        published_by:
            UUID of the user publishing this version.
        quality_gate:
            Optional quality-gate metadata (reserved for future use).

        Returns
        -------
        TVersion
            The newly created, frozen version.

        Raises
        ------
        ValueError
            If the draft status is REJECTED.
        """
        status = self._get_draft_status(draft)
        if status == DraftStatus.REJECTED:
            msg = "Cannot publish a draft with status REJECTED."
            raise ValueError(msg)

        version_number = self._next_version_number
        version = self._make_version(draft, version_number, published_by)

        self._store.save_version(version)
        vid: UUID = getattr(version, "version_id")
        self._store.set_active(vid)

        self._next_version_number += 1
        return version

    # ------------------------------------------------------------------
    # Abstract methods for subclasses
    # ------------------------------------------------------------------

    @abstractmethod
    def _make_version(
        self,
        draft: TDraft,
        version_number: int,
        published_by: UUID,
    ) -> TVersion:
        """Build a frozen version object from the given draft.

        Subclasses create the appropriate domain-specific version model.
        """
        ...

    @abstractmethod
    def _get_draft_status(self, draft: TDraft) -> DraftStatus:
        """Extract the DraftStatus from a draft object."""
        ...
