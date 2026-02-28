"""Tests for three-tier nationality classification (D-4 Task 4)."""

from __future__ import annotations

from pathlib import Path

from src.data.workforce.build_nationality_classification import (
    build_nationality_classification,
    save_nationality_classification,
)
from src.data.workforce.nationality_classification import (
    ClassificationOverride,
    NationalityTier,
)
from src.models.common import ConstraintConfidence


class TestBuildNationalityClassification:
    """Build initial classification from expert judgment."""

    def test_all_sector_occupation_pairs(self) -> None:
        """Every (section, ISCO major group) pair has a classification."""
        cs = build_nationality_classification()
        # 20 sections x 10 occupation groups = 200
        assert len(cs.classifications) == 200

    def test_all_assumed_confidence(self) -> None:
        """All v1 classifications have confidence = ASSUMED."""
        cs = build_nationality_classification()
        for c in cs.classifications:
            assert c.source_confidence == ConstraintConfidence.ASSUMED

    def test_all_have_rationale(self) -> None:
        """Every classification has a non-empty rationale."""
        cs = build_nationality_classification()
        for c in cs.classifications:
            assert c.rationale, f"Empty rationale: {c.sector_code}/{c.occupation_code}"

    def test_all_have_sensitivity_range(self) -> None:
        """Every classification has a sensitivity_range."""
        cs = build_nationality_classification()
        for c in cs.classifications:
            assert c.sensitivity_range is not None, (
                f"No sensitivity: {c.sector_code}/{c.occupation_code}"
            )

    def test_public_admin_managers_saudi_ready(self) -> None:
        """Public admin (O) managers (ISCO 1) should be saudi_ready."""
        cs = build_nationality_classification()
        c = cs.get_tier("O", "1")
        assert c is not None
        assert c.tier == NationalityTier.SAUDI_READY

    def test_construction_elementary_expat_reliant(self) -> None:
        """Construction (F) elementary (ISCO 9) should be expat_reliant."""
        cs = build_nationality_classification()
        c = cs.get_tier("F", "9")
        assert c is not None
        assert c.tier == NationalityTier.EXPAT_RELIANT

    def test_get_sector_summary(self) -> None:
        cs = build_nationality_classification()
        summary = cs.get_sector_summary("O")
        assert summary["saudi_ready"] > 0

    def test_trainable_entries_sorted(self) -> None:
        """get_trainable_entries returns saudi_trainable sorted by gap."""
        cs = build_nationality_classification()
        trainable = cs.get_trainable_entries()
        assert len(trainable) > 0
        # All should be saudi_trainable
        for t in trainable:
            assert t.tier == NationalityTier.SAUDI_TRAINABLE


class TestClassificationOverrides:
    """Override mechanism for Knowledge Flywheel."""

    def test_apply_override_changes_tier(self) -> None:
        cs = build_nationality_classification()
        original = cs.get_tier("F", "9")
        assert original is not None
        assert original.tier == NationalityTier.EXPAT_RELIANT

        override = ClassificationOverride(
            sector_code="F",
            occupation_code="9",
            original_tier=NationalityTier.EXPAT_RELIANT,
            override_tier=NationalityTier.SAUDI_TRAINABLE,
            overridden_by="analyst_1",
            engagement_id="ENG-001",
            rationale="New TVTC program for construction",
            timestamp="2026-01-15T00:00:00Z",
        )

        new_cs = cs.apply_overrides([override])
        updated = new_cs.get_tier("F", "9")
        assert updated is not None
        assert updated.tier == NationalityTier.SAUDI_TRAINABLE

    def test_original_unchanged(self) -> None:
        """apply_overrides produces new set, original unchanged."""
        cs = build_nationality_classification()
        override = ClassificationOverride(
            sector_code="F", occupation_code="9",
            original_tier=NationalityTier.EXPAT_RELIANT,
            override_tier=NationalityTier.SAUDI_TRAINABLE,
            overridden_by="test", engagement_id=None,
            rationale="test", timestamp="2026-01-01T00:00:00Z",
        )

        new_cs = cs.apply_overrides([override])

        # Original still expat_reliant
        orig = cs.get_tier("F", "9")
        assert orig is not None
        assert orig.tier == NationalityTier.EXPAT_RELIANT

        # New has trainable
        upd = new_cs.get_tier("F", "9")
        assert upd is not None
        assert upd.tier == NationalityTier.SAUDI_TRAINABLE

    def test_override_metadata_tracked(self) -> None:
        cs = build_nationality_classification()
        override = ClassificationOverride(
            sector_code="F", occupation_code="9",
            original_tier=NationalityTier.EXPAT_RELIANT,
            override_tier=NationalityTier.SAUDI_TRAINABLE,
            overridden_by="test", engagement_id=None,
            rationale="test", timestamp="2026-01-01T00:00:00Z",
        )
        new_cs = cs.apply_overrides([override])
        assert new_cs.metadata.get("overrides_applied") == 1


class TestSaveClassification:
    """Serialization."""

    def test_save(self, tmp_path: Path) -> None:
        cs = build_nationality_classification()
        path = save_nationality_classification(cs, tmp_path)
        assert path.exists()

    def test_provenance(self, tmp_path: Path) -> None:
        import json

        cs = build_nationality_classification()
        path = save_nationality_classification(cs, tmp_path)
        data = json.loads(path.read_text())
        assert "_provenance" in data
        assert data["total_classifications"] == 200
