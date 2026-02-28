"""Tests for CalibrationNote model and CalibrationNoteStore (Task 10)."""

from __future__ import annotations

from uuid import UUID

from src.flywheel.calibration import CalibrationNote, CalibrationNoteStore
from src.flywheel.models import PromotionStatus, ReuseScopeLevel
from src.models.common import new_uuid7


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_note(
    sector_code: str | None = "F",
    engagement_id: UUID | None = None,
    observation: str = "Construction multiplier overstated employment",
    likely_cause: str = "Outdated labour coefficients",
    recommended_adjustment: str | None = "Reduce by 15%",
    metric_affected: str = "employment",
    direction: str = "overstate",
    magnitude_estimate: float | None = 0.15,
    validated: bool = False,
    workspace_id: UUID | None = None,
) -> CalibrationNote:
    return CalibrationNote(
        sector_code=sector_code,
        engagement_id=engagement_id,
        observation=observation,
        likely_cause=likely_cause,
        recommended_adjustment=recommended_adjustment,
        metric_affected=metric_affected,
        direction=direction,
        magnitude_estimate=magnitude_estimate,
        created_by=new_uuid7(),
        validated=validated,
        workspace_id=workspace_id or new_uuid7(),
    )


# ---------------------------------------------------------------------------
# CalibrationNote model tests
# ---------------------------------------------------------------------------


class TestCalibrationNoteModel:
    """CalibrationNote has all required fields including promotion path."""

    def test_has_all_fields_including_promotion_path(self) -> None:
        note = _make_note()
        # Core fields
        assert isinstance(note.note_id, UUID)
        assert note.sector_code == "F"
        assert note.observation == "Construction multiplier overstated employment"
        assert note.likely_cause == "Outdated labour coefficients"
        assert note.recommended_adjustment == "Reduce by 15%"
        assert note.metric_affected == "employment"
        assert note.direction == "overstate"
        assert note.magnitude_estimate == 0.15
        assert isinstance(note.created_by, UUID)
        assert note.created_at is not None
        assert note.validated is False
        # Promotion path (Amendment 8)
        assert note.promoted_to is None
        assert note.promotion_status == PromotionStatus.RAW

    def test_has_scope_fields(self) -> None:
        ws_id = new_uuid7()
        eng_id = new_uuid7()
        note = CalibrationNote(
            observation="Test observation",
            likely_cause="Test cause",
            metric_affected="output_multiplier",
            direction="understate",
            created_by=new_uuid7(),
            workspace_id=ws_id,
            source_engagement_id=eng_id,
            reuse_scope=ReuseScopeLevel.SANITIZED_GLOBAL,
            sanitized_for_promotion=True,
        )
        assert note.workspace_id == ws_id
        assert note.source_engagement_id == eng_id
        assert note.reuse_scope == ReuseScopeLevel.SANITIZED_GLOBAL
        assert note.sanitized_for_promotion is True

    def test_promotion_status_defaults_to_raw(self) -> None:
        note = _make_note()
        assert note.promotion_status == PromotionStatus.RAW

    def test_scope_defaults(self) -> None:
        note = _make_note()
        assert note.reuse_scope == ReuseScopeLevel.WORKSPACE_ONLY
        assert note.sanitized_for_promotion is False
        assert note.source_engagement_id is None

    def test_optional_fields_can_be_none(self) -> None:
        note = CalibrationNote(
            observation="Minimal note",
            likely_cause="Unknown",
            metric_affected="import_ratio",
            direction="overstate",
            created_by=new_uuid7(),
            workspace_id=new_uuid7(),
        )
        assert note.sector_code is None
        assert note.engagement_id is None
        assert note.recommended_adjustment is None
        assert note.magnitude_estimate is None


# ---------------------------------------------------------------------------
# CalibrationNoteStore tests
# ---------------------------------------------------------------------------


class TestCalibrationNoteStore:
    """CalibrationNoteStore is append-only with search methods."""

    def test_append_and_get_by_id(self) -> None:
        store = CalibrationNoteStore()
        note = _make_note()
        store.append(note)
        retrieved = store.get(note.note_id)
        assert retrieved is note

    def test_find_by_sector_returns_matching(self) -> None:
        store = CalibrationNoteStore()
        note_f = _make_note(sector_code="F")
        note_c = _make_note(sector_code="C")
        store.append(note_f)
        store.append(note_c)

        result = store.find_by_sector("F")
        assert len(result) == 1
        assert result[0].sector_code == "F"

    def test_find_by_metric_returns_matching(self) -> None:
        store = CalibrationNoteStore()
        note_emp = _make_note(metric_affected="employment")
        note_out = _make_note(metric_affected="output_multiplier")
        store.append(note_emp)
        store.append(note_out)

        result = store.find_by_metric("employment")
        assert len(result) == 1
        assert result[0].metric_affected == "employment"

    def test_find_by_engagement_returns_matching(self) -> None:
        store = CalibrationNoteStore()
        eng_id = new_uuid7()
        note_with = _make_note(engagement_id=eng_id)
        note_without = _make_note(engagement_id=new_uuid7())
        store.append(note_with)
        store.append(note_without)

        result = store.find_by_engagement(eng_id)
        assert len(result) == 1
        assert result[0].engagement_id == eng_id

    def test_find_validated_returns_only_validated(self) -> None:
        store = CalibrationNoteStore()
        validated_note = _make_note(validated=True)
        unvalidated_note = _make_note(validated=False)
        store.append(validated_note)
        store.append(unvalidated_note)

        result = store.find_validated()
        assert len(result) == 1
        assert result[0].validated is True

    def test_find_unvalidated_returns_only_unvalidated(self) -> None:
        store = CalibrationNoteStore()
        validated_note = _make_note(validated=True)
        unvalidated_note = _make_note(validated=False)
        store.append(validated_note)
        store.append(unvalidated_note)

        result = store.find_unvalidated()
        assert len(result) == 1
        assert result[0].validated is False

    def test_list_all_returns_all_notes(self) -> None:
        store = CalibrationNoteStore()
        notes = [_make_note(sector_code=f"S{i}") for i in range(5)]
        for n in notes:
            store.append(n)

        result = store.list_all()
        assert len(result) == 5

    def test_get_nonexistent_returns_none(self) -> None:
        store = CalibrationNoteStore()
        result = store.get(new_uuid7())
        assert result is None
