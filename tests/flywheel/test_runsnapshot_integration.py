"""Tests for RunSnapshot integration with workforce version references (Task 15).

Validates Amendment 5: three new optional UUID fields on RunSnapshot
for occupation bridge, nationality classification, and Nitaqat targets.
"""

from uuid import uuid4

import pytest

from src.models.run import RunSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_base_kwargs() -> dict:
    """Return the minimum kwargs to construct a valid RunSnapshot."""
    return {
        "run_id": uuid4(),
        "model_version_id": uuid4(),
        "taxonomy_version_id": uuid4(),
        "concordance_version_id": uuid4(),
        "mapping_library_version_id": uuid4(),
        "assumption_library_version_id": uuid4(),
        "prompt_pack_version_id": uuid4(),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunSnapshotWorkforceFields:
    """RunSnapshot must accept optional workforce version references."""

    def test_existing_creation_without_new_fields(self) -> None:
        """Existing code that creates RunSnapshot without new fields must work."""
        snap = RunSnapshot(**_make_base_kwargs())
        assert snap.run_id is not None
        assert snap.model_version_id is not None

    def test_default_values_are_none(self) -> None:
        """New workforce fields default to None for backward compatibility."""
        snap = RunSnapshot(**_make_base_kwargs())
        assert snap.occupation_bridge_version_id is None
        assert snap.nationality_classification_version_id is None
        assert snap.nitaqat_target_version_id is None

    def test_all_three_new_fields_can_be_set(self) -> None:
        """All 3 new fields accept UUID values."""
        occ_id = uuid4()
        nat_id = uuid4()
        nit_id = uuid4()
        snap = RunSnapshot(
            **_make_base_kwargs(),
            occupation_bridge_version_id=occ_id,
            nationality_classification_version_id=nat_id,
            nitaqat_target_version_id=nit_id,
        )
        assert snap.occupation_bridge_version_id == occ_id
        assert snap.nationality_classification_version_id == nat_id
        assert snap.nitaqat_target_version_id == nit_id

    def test_partial_new_fields(self) -> None:
        """Setting only some new fields leaves the rest as None."""
        occ_id = uuid4()
        snap = RunSnapshot(
            **_make_base_kwargs(),
            occupation_bridge_version_id=occ_id,
        )
        assert snap.occupation_bridge_version_id == occ_id
        assert snap.nationality_classification_version_id is None
        assert snap.nitaqat_target_version_id is None

    def test_runsnapshot_is_still_frozen(self) -> None:
        """RunSnapshot must remain frozen=True (immutable)."""
        snap = RunSnapshot(**_make_base_kwargs())
        with pytest.raises(Exception):
            snap.run_id = uuid4()  # type: ignore[misc]

    def test_constraint_set_still_optional(self) -> None:
        """The existing constraint_set_version_id field is still optional."""
        snap = RunSnapshot(**_make_base_kwargs())
        assert snap.constraint_set_version_id is None

        cid = uuid4()
        snap2 = RunSnapshot(**_make_base_kwargs(), constraint_set_version_id=cid)
        assert snap2.constraint_set_version_id == cid
