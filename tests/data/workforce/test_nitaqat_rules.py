"""Tests for Nitaqat rule catalog (D-4 Task 3 Layer A)."""

from __future__ import annotations

from pathlib import Path

from scripts.build_nitaqat_data import build_rule_catalog, save_rule_catalog
from src.data.workforce.nitaqat_rules import NitaqatRuleType
from src.models.common import ConstraintConfidence


class TestNitaqatRuleCatalog:
    """Rule catalog model and lookups."""

    def test_all_rules_present(self) -> None:
        catalog = build_rule_catalog()
        assert len(catalog.rules) >= 15

    def test_all_rules_hard_confidence(self) -> None:
        """All catalog entries have confidence = HARD (published regulations)."""
        catalog = build_rule_catalog()
        for rule in catalog.rules:
            assert rule.source_confidence == ConstraintConfidence.HARD

    def test_get_rules_by_type(self) -> None:
        catalog = build_rule_catalog()
        quotas = catalog.get_rules_by_type(NitaqatRuleType.SECTOR_QUOTA)
        assert len(quotas) >= 2

    def test_get_rules_for_sector(self) -> None:
        catalog = build_rule_catalog()
        q_rules = catalog.get_rules_for_sector("Q")
        assert len(q_rules) >= 2  # Hospital + lab rules

    def test_get_rules_for_profession(self) -> None:
        catalog = build_rule_catalog()
        acct_rules = catalog.get_rules_for_profession("Accounting")
        assert len(acct_rules) >= 4  # 4 phased rules

    def test_active_rules_respect_dates(self) -> None:
        """get_active_rules respects effective_date / expiry_date."""
        catalog = build_rule_catalog()
        # Before any 2025 rules take effect
        early = catalog.get_active_rules("2024-01-01")
        # After most 2025 rules take effect
        late = catalog.get_active_rules("2025-11-01")
        assert len(late) > len(early)

    def test_phased_accounting_rules(self) -> None:
        """Accounting: Oct 2025 = 40%, Oct 2026 = 50%."""
        catalog = build_rule_catalog()
        acct_rules = catalog.get_rules_for_profession("Accounting")

        # Find phase 1 (40%)
        p1 = [r for r in acct_rules if r.phase == "phase_1"]
        assert len(p1) == 1
        assert p1[0].value == 0.40

        # Find phase 2 (50%)
        p2 = [r for r in acct_rules if r.phase == "phase_2"]
        assert len(p2) == 1
        assert p2[0].value == 0.50

    def test_counting_rules(self) -> None:
        """Disability = 4x, low-salary = 0.5x."""
        catalog = build_rule_catalog()
        counting = catalog.get_rules_by_type(NitaqatRuleType.COUNTING_RULE)

        disability = [r for r in counting if "disability" in r.description.lower()]
        assert len(disability) >= 1
        assert disability[0].value == 4.0

        low_salary = [r for r in counting if "4,000" in r.description]
        assert len(low_salary) >= 1
        assert low_salary[0].value == 0.5

    def test_equivalence_rules(self) -> None:
        catalog = build_rule_catalog()
        equiv = catalog.get_rules_by_type(NitaqatRuleType.EQUIVALENCE)
        assert len(equiv) >= 2  # GCC + investor

    def test_save_catalog(self, tmp_path: Path) -> None:
        catalog = build_rule_catalog()
        path = save_rule_catalog(catalog, tmp_path)
        assert path.exists()
        assert path.stat().st_size > 100
