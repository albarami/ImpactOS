"""Tests for occupation bridge matrix (D-4 Task 2)."""

from __future__ import annotations

from pathlib import Path

from src.data.workforce.build_occupation_bridge import (
    build_occupation_bridge,
    load_occupation_bridge,
    save_occupation_bridge,
)
from src.data.workforce.occupation_bridge import (
    ISCO08_MAJOR_GROUPS,
    OccupationBridge,
    OccupationBridgeEntry,
)


class TestOccupationBridgeModel:
    """OccupationBridge dataclass and validation."""

    def test_shares_sum_to_one(self) -> None:
        """Validate() catches sectors where shares don't sum to 1.0."""
        entries = [
            OccupationBridgeEntry(
                sector_code="F", occupation_code="7", share=0.5,
                source="test",
                source_confidence="ASSUMED",  # type: ignore[arg-type]
                quality_confidence="low",  # type: ignore[arg-type]
            ),
            OccupationBridgeEntry(
                sector_code="F", occupation_code="9", share=0.3,
                source="test",
                source_confidence="ASSUMED",  # type: ignore[arg-type]
                quality_confidence="low",  # type: ignore[arg-type]
            ),
        ]
        bridge = OccupationBridge(year=2022, entries=entries, metadata={})
        errors = bridge.validate()
        assert any("sum to" in e for e in errors)

    def test_valid_bridge_passes(self) -> None:
        """A properly constructed bridge passes validation."""
        bridge = build_occupation_bridge()
        errors = bridge.validate()
        assert errors == [], f"Validation errors: {errors}"

    def test_invalid_occupation_code(self) -> None:
        entries = [
            OccupationBridgeEntry(
                sector_code="F", occupation_code="X", share=1.0,
                source="test",
                source_confidence="ASSUMED",  # type: ignore[arg-type]
                quality_confidence="low",  # type: ignore[arg-type]
            ),
        ]
        bridge = OccupationBridge(year=2022, entries=entries, metadata={})
        errors = bridge.validate()
        assert any("Invalid ISCO-08" in e for e in errors)


class TestBuildOccupationBridge:
    """Build the bridge from structural patterns."""

    def test_all_sections_covered(self) -> None:
        bridge = build_occupation_bridge()
        sectors = bridge.get_sectors()
        assert len(sectors) == 20

    def test_construction_heavy_on_trades(self) -> None:
        """Construction (F) heavy on ISCO 7/8/9 (> 60% combined)."""
        bridge = build_occupation_bridge()
        shares = bridge.get_occupation_shares("F")
        trades = shares.get("7", 0) + shares.get("8", 0) + shares.get("9", 0)
        assert trades > 0.60

    def test_finance_heavy_on_professional(self) -> None:
        """Finance (K) heavy on ISCO 1/2/3/4 (> 70% combined)."""
        bridge = build_occupation_bridge()
        shares = bridge.get_occupation_shares("K")
        professional = (
            shares.get("1", 0) + shares.get("2", 0)
            + shares.get("3", 0) + shares.get("4", 0)
        )
        assert professional > 0.70

    def test_all_occupation_codes_valid(self) -> None:
        """All entries use valid ISCO-08 major group codes."""
        bridge = build_occupation_bridge()
        for e in bridge.entries:
            assert e.occupation_code in ISCO08_MAJOR_GROUPS

    def test_section_level_only(self) -> None:
        """Bridge operates at section level (A-T), not division level."""
        bridge = build_occupation_bridge()
        for e in bridge.entries:
            assert len(e.sector_code) == 1  # Single letter = section


class TestSaveLoadBridge:
    """Round-trip serialization."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        bridge = build_occupation_bridge()
        path = save_occupation_bridge(bridge, tmp_path)
        assert path.exists()

        loaded = load_occupation_bridge(path)
        assert loaded.year == bridge.year
        # Non-zero entries should be preserved
        assert len(loaded.entries) > 0

    def test_provenance_in_output(self, tmp_path: Path) -> None:
        import json

        bridge = build_occupation_bridge()
        path = save_occupation_bridge(bridge, tmp_path)
        data = json.loads(path.read_text())
        assert "_provenance" in data
        assert data["granularity"] == "section"
