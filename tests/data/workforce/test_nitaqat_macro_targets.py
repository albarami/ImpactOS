"""Tests for Nitaqat macro targets (D-4 Task 3 Layer B)."""

from __future__ import annotations

from pathlib import Path

from scripts.build_nitaqat_data import build_macro_targets, save_macro_targets

ISIC_SECTIONS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
]


class TestMacroSaudizationTargets:
    """Macro targets model and validation."""

    def test_all_sections_accounted_for(self) -> None:
        """Every ISIC section is present (Amendment 6: null for N/A)."""
        targets = build_macro_targets()
        for section in ISIC_SECTIONS:
            assert section in targets.targets

    def test_section_u_is_null(self) -> None:
        """Section U (extraterritorial) is null/not-applicable (Amendment 6)."""
        targets = build_macro_targets()
        assert targets.get_target("U") is None

    def test_target_range_consistent(self) -> None:
        """target_range_low <= effective_target_pct <= target_range_high."""
        targets = build_macro_targets()
        for code, t in targets.targets.items():
            if t is not None:
                assert t.target_range_low <= t.effective_target_pct, (
                    f"{code}: low > effective"
                )
                assert t.effective_target_pct <= t.target_range_high, (
                    f"{code}: effective > high"
                )

    def test_derivation_non_empty(self) -> None:
        """All targets have non-empty derivation."""
        targets = build_macro_targets()
        for t in targets.get_all_applicable().values():
            assert t.derivation, f"Empty derivation for {t.sector_code}"

    def test_caveats_non_empty(self) -> None:
        """Macro targets always have caveats."""
        targets = build_macro_targets()
        assert len(targets.caveats) >= 1

    def test_applicable_rules_reference_valid_ids(self) -> None:
        """applicable_rules reference valid rule_ids from catalog."""
        from scripts.build_nitaqat_data import build_rule_catalog

        catalog = build_rule_catalog()
        rule_ids = {r.rule_id for r in catalog.rules}

        targets = build_macro_targets()
        for t in targets.get_all_applicable().values():
            for rule_id in t.applicable_rules:
                assert rule_id in rule_ids, (
                    f"Sector {t.sector_code}: unknown rule {rule_id}"
                )

    def test_save_targets(self, tmp_path: Path) -> None:
        targets = build_macro_targets()
        path = save_macro_targets(targets, tmp_path)
        assert path.exists()

    def test_provenance_in_output(self, tmp_path: Path) -> None:
        import json

        targets = build_macro_targets()
        path = save_macro_targets(targets, tmp_path)
        data = json.loads(path.read_text())
        assert "_provenance" in data
