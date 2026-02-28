"""Nitaqat / Saudization rule catalog — Layer A (D-4 Task 3).

Authoritative catalog of published Saudization rules.
All entries have source_confidence = HARD (published regulations).

This is the detailed layer. For simplified macro targets, see
nitaqat_macro_targets.py (Layer B).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from src.models.common import ConstraintConfidence


class NitaqatRuleType(StrEnum):
    """Type of Saudization rule."""

    SECTOR_QUOTA = "sector_quota"
    PROFESSION_QUOTA = "profession_quota"
    COUNTING_RULE = "counting_rule"
    SIZE_THRESHOLD = "size_threshold"
    EQUIVALENCE = "equivalence"


@dataclass(frozen=True)
class NitaqatRule:
    """Individual published Saudization rule."""

    rule_id: str
    rule_type: NitaqatRuleType
    sector_code: str | None
    profession: str | None
    description: str
    value: float | str
    effective_date: str
    expiry_date: str | None
    phase: str | None
    company_size_min: int | None
    source: str
    source_url: str | None
    source_confidence: ConstraintConfidence
    notes: str | None = None


@dataclass(frozen=True)
class NitaqatRuleCatalog:
    """Complete catalog of published Nitaqat/Saudization rules."""

    rules: list[NitaqatRule]
    effective_as_of: str
    metadata: dict[str, object] = field(default_factory=dict)

    def get_rules_by_type(
        self, rule_type: NitaqatRuleType,
    ) -> list[NitaqatRule]:
        """Filter rules by type."""
        return [r for r in self.rules if r.rule_type == rule_type]

    def get_rules_for_sector(self, sector_code: str) -> list[NitaqatRule]:
        """Get all rules applicable to a sector."""
        return [r for r in self.rules if r.sector_code == sector_code]

    def get_rules_for_profession(self, profession: str) -> list[NitaqatRule]:
        """Get all rules applicable to a profession."""
        return [
            r for r in self.rules
            if r.profession and profession.lower() in r.profession.lower()
        ]

    def get_active_rules(self, as_of_date: str) -> list[NitaqatRule]:
        """Get rules active on a given date (ISO format YYYY-MM-DD)."""
        return [
            r for r in self.rules
            if r.effective_date <= as_of_date
            and (r.expiry_date is None or r.expiry_date > as_of_date)
        ]
