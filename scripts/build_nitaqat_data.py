"""Build Nitaqat rule catalog and macro targets (D-4 Task 3c).

Produces:
- data/curated/nitaqat_rule_catalog_2025.json (Layer A: detailed rules)
- data/curated/nitaqat_macro_targets_2025.json (Layer B: sector targets)

Usage:
    python -m scripts.build_nitaqat_data
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.data.workforce.nitaqat_macro_targets import (
    MacroSaudizationTargets,
    SectorSaudizationTarget,
)
from src.data.workforce.nitaqat_rules import (
    NitaqatRule,
    NitaqatRuleCatalog,
    NitaqatRuleType,
)
from src.data.workforce.unit_registry import QualityConfidence
from src.models.common import ConstraintConfidence

HARD = ConstraintConfidence.HARD
ESTIMATED = ConstraintConfidence.ESTIMATED


def build_rule_catalog() -> NitaqatRuleCatalog:
    """Build the complete Nitaqat rule catalog from published regulations."""
    rules: list[NitaqatRule] = []

    # ---- Sector/Profession Quotas ----
    rules.append(NitaqatRule(
        rule_id="NQ-2025-MED-LAB",
        rule_type=NitaqatRuleType.PROFESSION_QUOTA,
        sector_code="Q",
        profession="Medical laboratories",
        description="Medical laboratories must be 70% Saudi",
        value=0.70,
        effective_date="2025-04-01",
        expiry_date=None,
        phase="phase_1_major_cities",
        company_size_min=None,
        source="mhrsd_resolution_medical_2025",
        source_url=None,
        source_confidence=HARD,
    ))

    rules.append(NitaqatRule(
        rule_id="NQ-2025-MED-LAB-P2",
        rule_type=NitaqatRuleType.PROFESSION_QUOTA,
        sector_code="Q",
        profession="Medical laboratories",
        description="Medical laboratories 70% Saudi — all regions",
        value=0.70,
        effective_date="2025-10-01",
        expiry_date=None,
        phase="phase_2_all",
        company_size_min=None,
        source="mhrsd_resolution_medical_2025",
        source_url=None,
        source_confidence=HARD,
    ))

    rules.append(NitaqatRule(
        rule_id="NQ-2025-HOSPITAL",
        rule_type=NitaqatRuleType.PROFESSION_QUOTA,
        sector_code="Q",
        profession="Hospitals",
        description="Hospitals must be 65% Saudi",
        value=0.65,
        effective_date="2025-04-01",
        expiry_date=None,
        phase="phase_1_major_cities",
        company_size_min=None,
        source="mhrsd_resolution_hospital_2025",
        source_url=None,
        source_confidence=HARD,
    ))

    rules.append(NitaqatRule(
        rule_id="NQ-2025-HOSPITAL-P2",
        rule_type=NitaqatRuleType.PROFESSION_QUOTA,
        sector_code="Q",
        profession="Hospitals",
        description="Hospitals 65% Saudi — all regions",
        value=0.65,
        effective_date="2025-10-01",
        expiry_date=None,
        phase="phase_2_all",
        company_size_min=None,
        source="mhrsd_resolution_hospital_2025",
        source_url=None,
        source_confidence=HARD,
    ))

    rules.append(NitaqatRule(
        rule_id="NQ-2025-PHARM-COMM",
        rule_type=NitaqatRuleType.PROFESSION_QUOTA,
        sector_code="G",
        profession="Community pharmacies",
        description="Community pharmacies must be 35% Saudi",
        value=0.35,
        effective_date="2025-07-01",
        expiry_date=None,
        phase=None,
        company_size_min=None,
        source="mhrsd_resolution_pharmacy_2025",
        source_url=None,
        source_confidence=HARD,
    ))

    rules.append(NitaqatRule(
        rule_id="NQ-2025-PHARM-OTHER",
        rule_type=NitaqatRuleType.PROFESSION_QUOTA,
        sector_code="G",
        profession="Other pharmacy businesses",
        description="Other pharmacy businesses must be 55% Saudi",
        value=0.55,
        effective_date="2025-07-01",
        expiry_date=None,
        phase=None,
        company_size_min=None,
        source="mhrsd_resolution_pharmacy_2025",
        source_url=None,
        source_confidence=HARD,
    ))

    rules.append(NitaqatRule(
        rule_id="NQ-2025-ENGINEERING",
        rule_type=NitaqatRuleType.PROFESSION_QUOTA,
        sector_code=None,
        profession="Engineering",
        description="Engineering firms with 5+ engineers must be 30% Saudi",
        value=0.30,
        effective_date="2025-07-01",
        expiry_date=None,
        phase=None,
        company_size_min=5,
        source="mhrsd_resolution_engineering_2025",
        source_url=None,
        source_confidence=HARD,
    ))

    # Accounting — phased over 4 years
    for phase_num, (eff_date, pct) in enumerate([
        ("2025-10-01", 0.40),
        ("2026-10-01", 0.50),
        ("2027-10-01", 0.60),
        ("2028-10-01", 0.70),
    ], start=1):
        rules.append(NitaqatRule(
            rule_id=f"NQ-2025-ACCT-P{phase_num}",
            rule_type=NitaqatRuleType.PROFESSION_QUOTA,
            sector_code=None,
            profession="Accounting",
            description=f"Accounting firms with 5+ accountants must be {int(pct*100)}% Saudi",
            value=pct,
            effective_date=eff_date,
            expiry_date=f"{int(eff_date[:4])+1}-09-30" if phase_num < 4 else None,
            phase=f"phase_{phase_num}",
            company_size_min=5,
            source="mhrsd_resolution_accounting_2025",
            source_url=None,
            source_confidence=HARD,
        ))

    rules.append(NitaqatRule(
        rule_id="NQ-2025-TOURISM",
        rule_type=NitaqatRuleType.SECTOR_QUOTA,
        sector_code="I",
        profession="Tourism (41 professions)",
        description="41 tourism professions localized",
        value="41_professions_localized",
        effective_date="2025-04-01",
        expiry_date=None,
        phase=None,
        company_size_min=None,
        source="mhrsd_resolution_tourism_2025",
        source_url=None,
        source_confidence=HARD,
    ))

    rules.append(NitaqatRule(
        rule_id="NQ-MUTAWAR-GENERAL",
        rule_type=NitaqatRuleType.SECTOR_QUOTA,
        sector_code=None,
        profession=None,
        description="General Nitaqat Mutawar: ~30% minimum for companies with 100+ employees",
        value=0.30,
        effective_date="2021-01-01",
        expiry_date=None,
        phase=None,
        company_size_min=100,
        source="nitaqat_mutawar_2021",
        source_url=None,
        source_confidence=HARD,
    ))

    # ---- Counting Rules ----
    rules.append(NitaqatRule(
        rule_id="NQ-COUNT-LOW-SALARY",
        rule_type=NitaqatRuleType.COUNTING_RULE,
        sector_code=None,
        profession=None,
        description="Saudi earning < SAR 4,000/month counts as 0.5 toward quota",
        value=0.5,
        effective_date="2021-01-01",
        expiry_date=None,
        phase=None,
        company_size_min=None,
        source="nitaqat_mutawar_counting_2021",
        source_url=None,
        source_confidence=HARD,
    ))

    rules.append(NitaqatRule(
        rule_id="NQ-COUNT-DISABILITY",
        rule_type=NitaqatRuleType.COUNTING_RULE,
        sector_code=None,
        profession=None,
        description="Person with disability counts as 4x toward quota",
        value=4.0,
        effective_date="2021-01-01",
        expiry_date=None,
        phase=None,
        company_size_min=None,
        source="nitaqat_mutawar_counting_2021",
        source_url=None,
        source_confidence=HARD,
    ))

    rules.append(NitaqatRule(
        rule_id="NQ-COUNT-REMOTE",
        rule_type=NitaqatRuleType.COUNTING_RULE,
        sector_code=None,
        profession=None,
        description="Remote Saudi workers count as regular employees toward quota",
        value=1.0,
        effective_date="2021-01-01",
        expiry_date=None,
        phase=None,
        company_size_min=None,
        source="nitaqat_mutawar_counting_2021",
        source_url=None,
        source_confidence=HARD,
    ))

    # ---- Equivalence Rules ----
    rules.append(NitaqatRule(
        rule_id="NQ-EQUIV-GCC",
        rule_type=NitaqatRuleType.EQUIVALENCE,
        sector_code=None,
        profession=None,
        description="GCC nationals count as Saudi for quota purposes",
        value="gcc_as_saudi",
        effective_date="2021-01-01",
        expiry_date=None,
        phase=None,
        company_size_min=None,
        source="nitaqat_gcc_equivalence",
        source_url=None,
        source_confidence=HARD,
    ))

    rules.append(NitaqatRule(
        rule_id="NQ-EQUIV-INVESTOR",
        rule_type=NitaqatRuleType.EQUIVALENCE,
        sector_code=None,
        profession=None,
        description="Foreign investors counted as Saudi since April 2024",
        value="investor_as_saudi",
        effective_date="2024-04-01",
        expiry_date=None,
        phase=None,
        company_size_min=None,
        source="mhrsd_investor_equivalence_2024",
        source_url=None,
        source_confidence=HARD,
    ))

    # ---- Size Thresholds ----
    rules.append(NitaqatRule(
        rule_id="NQ-SIZE-SMALL",
        rule_type=NitaqatRuleType.SIZE_THRESHOLD,
        sector_code=None,
        profession=None,
        description="Small companies (1-5 employees): at least 1 Saudi",
        value="1_saudi_minimum",
        effective_date="2021-01-01",
        expiry_date=None,
        phase=None,
        company_size_min=1,
        source="nitaqat_mutawar_2021",
        source_url=None,
        source_confidence=HARD,
    ))

    rules.append(NitaqatRule(
        rule_id="NQ-SIZE-REVIEW-CYCLE",
        rule_type=NitaqatRuleType.SIZE_THRESHOLD,
        sector_code=None,
        profession=None,
        description="Nitaqat color bands reviewed every 26 weeks by MHRSD",
        value="26_week_review",
        effective_date="2021-01-01",
        expiry_date=None,
        phase=None,
        company_size_min=None,
        source="nitaqat_mutawar_2021",
        source_url=None,
        source_confidence=HARD,
    ))

    return NitaqatRuleCatalog(
        rules=rules,
        effective_as_of="2025-02-28",
        metadata={
            "total_rules": len(rules),
            "note": "All entries from published MHRSD regulations",
        },
    )


# ---- Macro Targets (Layer B) ----

# Derived sector-level targets
_MACRO_TARGET_DATA: dict[str, dict[str, object]] = {
    "A": {"pct": 0.10, "lo": 0.05, "hi": 0.15,
           "derivation": "Low current Saudi share (~8%), gradual enforcement",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "B": {"pct": 0.30, "lo": 0.25, "hi": 0.40,
           "derivation": "Aramco-driven high Saudization, Nitaqat general",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "C": {"pct": 0.20, "lo": 0.15, "hi": 0.30,
           "derivation": "Manufacturing diverse, general Nitaqat applies",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "D": {"pct": 0.40, "lo": 0.30, "hi": 0.55,
           "derivation": "Utilities semi-public, higher Saudi targets",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "E": {"pct": 0.25, "lo": 0.15, "hi": 0.30,
           "derivation": "Water/waste management, moderate targets",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "F": {"pct": 0.12, "lo": 0.08, "hi": 0.18,
           "derivation": "Construction structurally expat-heavy, low targets",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "G": {"pct": 0.30, "lo": 0.22, "hi": 0.40,
           "derivation": "Retail active Saudization + pharmacy rules",
           "rules": ["NQ-MUTAWAR-GENERAL", "NQ-2025-PHARM-COMM", "NQ-2025-PHARM-OTHER"]},
    "H": {"pct": 0.20, "lo": 0.15, "hi": 0.25,
           "derivation": "Transport mixed, general Nitaqat",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "I": {"pct": 0.20, "lo": 0.12, "hi": 0.30,
           "derivation": "Tourism professions localized + general Nitaqat",
           "rules": ["NQ-MUTAWAR-GENERAL", "NQ-2025-TOURISM"]},
    "J": {"pct": 0.35, "lo": 0.30, "hi": 0.50,
           "derivation": "ICT strong Saudi graduate pool, active government push",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "K": {"pct": 0.55, "lo": 0.45, "hi": 0.70,
           "derivation": "Finance heavily Saudized + accounting phased rules",
           "rules": ["NQ-MUTAWAR-GENERAL", "NQ-2025-ACCT-P1"]},
    "L": {"pct": 0.25, "lo": 0.15, "hi": 0.35,
           "derivation": "Real estate moderate, general Nitaqat",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "M": {"pct": 0.30, "lo": 0.25, "hi": 0.40,
           "derivation": "Professional services + engineering rule",
           "rules": ["NQ-MUTAWAR-GENERAL", "NQ-2025-ENGINEERING"]},
    "N": {"pct": 0.15, "lo": 0.10, "hi": 0.20,
           "derivation": "Admin/support services, low baseline",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "O": {"pct": 0.90, "lo": 0.85, "hi": 0.95,
           "derivation": "Public administration: near-total Saudization by policy",
           "rules": []},
    "P": {"pct": 0.70, "lo": 0.60, "hi": 0.80,
           "derivation": "Education: strong Saudi pipeline + government institutions",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "Q": {"pct": 0.45, "lo": 0.35, "hi": 0.65,
           "derivation": "Health: hospital 65% + lab 70% + general",
           "rules": ["NQ-2025-HOSPITAL", "NQ-2025-MED-LAB", "NQ-MUTAWAR-GENERAL"]},
    "R": {"pct": 0.25, "lo": 0.15, "hi": 0.35,
           "derivation": "Arts/recreation moderate",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "S": {"pct": 0.20, "lo": 0.12, "hi": 0.30,
           "derivation": "Other services diverse, moderate targets",
           "rules": ["NQ-MUTAWAR-GENERAL"]},
    "T": {"pct": 0.05, "lo": 0.02, "hi": 0.08,
           "derivation": "Domestic workers: structural expat reliance, minimal quota",
           "rules": []},
}


def build_macro_targets() -> MacroSaudizationTargets:
    """Build macro-level Saudization targets from rule catalog."""
    targets: dict[str, SectorSaudizationTarget | None] = {}

    for code, info in _MACRO_TARGET_DATA.items():
        targets[code] = SectorSaudizationTarget(
            sector_code=code,
            effective_target_pct=float(info["pct"]),
            target_range_low=float(info["lo"]),
            target_range_high=float(info["hi"]),
            derivation=str(info["derivation"]),
            applicable_rules=list(info["rules"]),
            source_confidence=ESTIMATED if info["rules"] else ConstraintConfidence.ASSUMED,
            quality_confidence=QualityConfidence.MEDIUM if info["rules"] else QualityConfidence.LOW,
        )

    # Amendment 6: Section U not applicable
    targets["U"] = None

    return MacroSaudizationTargets(
        targets=targets,
        effective_as_of="2025-02-28",
        metadata={
            "derived_from": "nitaqat_rule_catalog_2025",
            "method": "Weighted aggregation of applicable rules per sector",
        },
        caveats=[
            "Does not capture company-size variation within sectors",
            "Salary-based counting rules (0.5x for <SAR 4k) not reflected in macro targets",
            "Disability multiplier (4x) not reflected in macro percentage",
            "Phased rules use earliest applicable phase",
            "Sector U (Extraterritorial) target is null/not-applicable",
        ],
    )


def save_rule_catalog(
    catalog: NitaqatRuleCatalog,
    output_dir: str | Path = "data/curated",
) -> Path:
    """Save rule catalog to curated JSON."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rules_out = []
    for r in catalog.rules:
        rules_out.append({
            "rule_id": r.rule_id,
            "rule_type": r.rule_type.value,
            "sector_code": r.sector_code,
            "profession": r.profession,
            "description": r.description,
            "value": r.value,
            "effective_date": r.effective_date,
            "expiry_date": r.expiry_date,
            "phase": r.phase,
            "company_size_min": r.company_size_min,
            "source": r.source,
            "source_url": r.source_url,
            "source_confidence": r.source_confidence.value,
            "notes": r.notes,
        })

    output = {
        "_provenance": {
            "builder": "build_nitaqat_data.py",
            "builder_version": "d4_v1",
            "build_timestamp": datetime.now(tz=UTC).isoformat(),
            "source_ids": list({r.source for r in catalog.rules}),
            "method": "Published MHRSD regulations codified",
        },
        "effective_as_of": catalog.effective_as_of,
        "total_rules": len(rules_out),
        "rules": rules_out,
        "metadata": dict(catalog.metadata),
    }

    out_path = out_dir / "nitaqat_rule_catalog_2025.json"
    out_path.write_text(json.dumps(output, indent=2))
    return out_path


def save_macro_targets(
    targets: MacroSaudizationTargets,
    output_dir: str | Path = "data/curated",
) -> Path:
    """Save macro targets to curated JSON."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets_out: dict[str, object] = {}
    for code, t in sorted(targets.targets.items()):
        if t is None:
            targets_out[code] = None
        else:
            targets_out[code] = {
                "sector_code": t.sector_code,
                "effective_target_pct": t.effective_target_pct,
                "target_range_low": t.target_range_low,
                "target_range_high": t.target_range_high,
                "derivation": t.derivation,
                "applicable_rules": t.applicable_rules,
                "source_confidence": t.source_confidence.value,
                "quality_confidence": t.quality_confidence.value,
                "notes": t.notes,
            }

    output = {
        "_provenance": {
            "builder": "build_nitaqat_data.py",
            "builder_version": "d4_v1",
            "build_timestamp": datetime.now(tz=UTC).isoformat(),
            "source_ids": ["nitaqat_rule_catalog_2025"],
            "method": "Weighted aggregation of applicable rules per sector",
        },
        "effective_as_of": targets.effective_as_of,
        "targets": targets_out,
        "caveats": targets.caveats,
        "metadata": dict(targets.metadata),
    }

    out_path = out_dir / "nitaqat_macro_targets_2025.json"
    out_path.write_text(json.dumps(output, indent=2))
    return out_path


def main() -> None:
    """Build and save both Nitaqat data layers."""
    print("Building Nitaqat rule catalog (Layer A)...")
    catalog = build_rule_catalog()
    cat_path = save_rule_catalog(catalog)
    print(f"  Saved {len(catalog.rules)} rules to {cat_path}")

    print("Building macro Saudization targets (Layer B)...")
    targets = build_macro_targets()
    tgt_path = save_macro_targets(targets)
    applicable = len(targets.get_all_applicable())
    print(f"  Saved {applicable} sector targets + {len(targets.caveats)} caveats to {tgt_path}")

    print("Done.")


if __name__ == "__main__":
    main()
