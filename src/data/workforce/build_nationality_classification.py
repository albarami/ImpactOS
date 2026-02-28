"""Build three-tier nationality classification (D-4 Task 4b).

Expert-judgment-based initial classification of sector-occupation pairs
as Saudi-ready / Saudi-trainable / Expat-reliant.

Every classification carries:
- confidence: ASSUMED (v1, judgment-based)
- sensitivity_range showing plausible shift
- rationale explaining the judgment

Section (A-T) x ISCO major group (0-9) = 200 cells.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.data.workforce.nationality_classification import (
    NationalityClassification,
    NationalityClassificationSet,
    NationalityTier,
)
from src.data.workforce.unit_registry import QualityConfidence
from src.models.common import ConstraintConfidence

ISIC_SECTIONS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
]

ISCO_MAJOR_GROUPS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]

# Classification rules: (sector, occupation) -> (tier, saudi_pct, rationale)
# None for saudi_pct means unknown.
# Sensitivity shows (could_be_lower, could_be_higher) tier.
_CLASSIFICATION_RULES: dict[
    tuple[str, str],
    tuple[NationalityTier, float | None, str, tuple[str, str]],
] = {}


def _init_rules() -> None:
    """Initialize classification rules from expert judgment."""
    if _CLASSIFICATION_RULES:
        return

    sr = NationalityTier.SAUDI_READY
    st = NationalityTier.SAUDI_TRAINABLE
    er = NationalityTier.EXPAT_RELIANT

    # --- Government/Public (O) ---
    for occ in ISCO_MAJOR_GROUPS:
        if occ == "0":
            _CLASSIFICATION_RULES[("O", "0")] = (
                sr, 0.95, "Armed forces: Saudi by law", (sr.value, sr.value))
        elif occ in ("1", "2", "3", "4"):
            _CLASSIFICATION_RULES[("O", occ)] = (
                sr, 0.90, "Public sector management/professional: high Saudi share",
                (sr.value, sr.value))
        elif occ == "5":
            _CLASSIFICATION_RULES[("O", occ)] = (
                sr, 0.85, "Public sector services: primarily Saudi",
                (st.value, sr.value))
        else:
            _CLASSIFICATION_RULES[("O", occ)] = (
                st, 0.60, "Public sector support roles: mixed nationality",
                (st.value, sr.value))

    # --- Education (P) ---
    for occ in ISCO_MAJOR_GROUPS:
        if occ == "2":
            _CLASSIFICATION_RULES[("P", "2")] = (
                sr, 0.75, "Teachers/professors: large Saudi graduate pool",
                (st.value, sr.value))
        elif occ in ("1", "3"):
            _CLASSIFICATION_RULES[("P", occ)] = (
                sr, 0.70, "Education management/technicians: Saudized",
                (st.value, sr.value))
        elif occ in ("4", "5"):
            _CLASSIFICATION_RULES[("P", occ)] = (
                st, 0.40, "Education support: growing Saudi pipeline",
                (st.value, sr.value))
        else:
            _CLASSIFICATION_RULES[("P", occ)] = (
                er, 0.15, "Education maintenance/elementary: mostly expat",
                (er.value, st.value))

    # --- Finance (K) ---
    for occ in ISCO_MAJOR_GROUPS:
        if occ in ("1", "2", "3", "4"):
            _CLASSIFICATION_RULES[("K", occ)] = (
                sr, 0.75, "Finance professional/clerical: strong Saudi presence",
                (st.value, sr.value))
        elif occ == "5":
            _CLASSIFICATION_RULES[("K", "5")] = (
                st, 0.50, "Finance sales: growing Saudization",
                (st.value, sr.value))
        else:
            _CLASSIFICATION_RULES[("K", occ)] = (
                st, 0.35, "Finance support roles: mixed",
                (er.value, sr.value))

    # --- Construction (F) ---
    for occ in ISCO_MAJOR_GROUPS:
        if occ in ("1", "2"):
            _CLASSIFICATION_RULES[("F", occ)] = (
                st, 0.25, "Construction management/engineering: trainable",
                (st.value, sr.value))
        elif occ == "3":
            _CLASSIFICATION_RULES[("F", "3")] = (
                st, 0.15, "Construction technicians: TVTC pipeline growing",
                (er.value, st.value))
        elif occ in ("7", "8"):
            _CLASSIFICATION_RULES[("F", occ)] = (
                er, 0.05, "Construction trades/operators: structural expat reliance",
                (er.value, st.value))
        elif occ == "9":
            _CLASSIFICATION_RULES[("F", "9")] = (
                er, 0.03, "Construction elementary: deeply expat-reliant",
                (er.value, er.value))
        else:
            _CLASSIFICATION_RULES[("F", occ)] = (
                er, 0.10, "Construction other: predominantly expat",
                (er.value, st.value))

    # --- Wholesale/Retail (G) ---
    for occ in ISCO_MAJOR_GROUPS:
        if occ in ("1", "2"):
            _CLASSIFICATION_RULES[("G", occ)] = (
                sr, 0.55, "Retail management: active Saudization enforcement",
                (st.value, sr.value))
        elif occ == "5":
            _CLASSIFICATION_RULES[("G", "5")] = (
                st, 0.30, "Sales workers: Nitaqat pushing higher Saudi share",
                (st.value, sr.value))
        elif occ == "9":
            _CLASSIFICATION_RULES[("G", "9")] = (
                er, 0.10, "Retail elementary: warehouse/stock workers mostly expat",
                (er.value, st.value))
        else:
            _CLASSIFICATION_RULES[("G", occ)] = (
                st, 0.25, "Retail support roles: mixed, trending Saudi",
                (er.value, sr.value))

    # --- ICT (J) ---
    for occ in ISCO_MAJOR_GROUPS:
        if occ in ("1", "2", "3"):
            _CLASSIFICATION_RULES[("J", occ)] = (
                sr, 0.55, "ICT professionals: large Saudi tech graduate pool",
                (st.value, sr.value))
        elif occ == "4":
            _CLASSIFICATION_RULES[("J", "4")] = (
                sr, 0.50, "ICT clerical/data entry: Saudi preferred",
                (st.value, sr.value))
        else:
            _CLASSIFICATION_RULES[("J", occ)] = (
                st, 0.30, "ICT other roles: mixed nationality",
                (er.value, sr.value))

    # --- Health (Q) ---
    for occ in ISCO_MAJOR_GROUPS:
        if occ == "2":
            _CLASSIFICATION_RULES[("Q", "2")] = (
                st, 0.35, "Healthcare professionals: growing but still expat-heavy",
                (st.value, sr.value))
        elif occ == "3":
            _CLASSIFICATION_RULES[("Q", "3")] = (
                st, 0.30, "Health technicians: active training programs",
                (er.value, sr.value))
        elif occ == "1":
            _CLASSIFICATION_RULES[("Q", "1")] = (
                sr, 0.55, "Hospital managers: Saudi leadership push",
                (st.value, sr.value))
        elif occ == "9":
            _CLASSIFICATION_RULES[("Q", "9")] = (
                er, 0.08, "Health elementary: cleaning/porters mostly expat",
                (er.value, st.value))
        else:
            _CLASSIFICATION_RULES[("Q", occ)] = (
                st, 0.25, "Health support roles: mixed",
                (er.value, sr.value))

    # --- Households as employers (T) ---
    for occ in ISCO_MAJOR_GROUPS:
        _CLASSIFICATION_RULES[("T", occ)] = (
            er, 0.02, "Domestic workers: overwhelmingly expat by structure",
            (er.value, er.value))

    # Fill remaining sector-occupation pairs with heuristics
    for section in ISIC_SECTIONS:
        for occ in ISCO_MAJOR_GROUPS:
            if (section, occ) not in _CLASSIFICATION_RULES:
                _CLASSIFICATION_RULES[(section, occ)] = _default_rule(section, occ)


def _default_rule(
    section: str,
    occ: str,
) -> tuple[NationalityTier, float | None, str, tuple[str, str]]:
    """Default classification for unmapped sector-occupation pairs."""
    sr = NationalityTier.SAUDI_READY
    st = NationalityTier.SAUDI_TRAINABLE
    er = NationalityTier.EXPAT_RELIANT

    # Managers and professionals tend toward Saudi-ready/trainable
    if occ in ("1", "2"):
        return (st, 0.35, f"Default: {section} management/professional — trainable",
                (st.value, sr.value))
    # Technicians, clerical
    if occ in ("3", "4"):
        return (st, 0.25, f"Default: {section} technical/clerical — trainable",
                (er.value, sr.value))
    # Service and sales
    if occ == "5":
        return (st, 0.20, f"Default: {section} service/sales — mixed",
                (er.value, sr.value))
    # Skilled agriculture
    if occ == "6":
        return (er, 0.08, f"Default: {section} skilled agriculture — expat dominated",
                (er.value, st.value))
    # Craft, operators
    if occ in ("7", "8"):
        return (er, 0.10, f"Default: {section} trades/operators — expat dominated",
                (er.value, st.value))
    # Elementary
    if occ == "9":
        return (er, 0.08, f"Default: {section} elementary — expat dominated",
                (er.value, st.value))
    # Armed forces (only relevant for O, handled above)
    if occ == "0":
        return (sr, None, f"Default: {section} armed forces — typically Saudi",
                (sr.value, sr.value))

    return (st, None, f"Default: {section}/{occ} — unclassified",
            (er.value, sr.value))


def build_nationality_classification(
    year: int = 2022,
) -> NationalityClassificationSet:
    """Build the initial three-tier nationality classification.

    All entries are confidence: ASSUMED (expert judgment v1).
    """
    _init_rules()

    classifications: list[NationalityClassification] = []

    for section in ISIC_SECTIONS:
        for occ in ISCO_MAJOR_GROUPS:
            tier, saudi_pct, rationale, sens = _CLASSIFICATION_RULES[(section, occ)]
            classifications.append(NationalityClassification(
                sector_code=section,
                occupation_code=occ,
                tier=tier,
                current_saudi_pct=saudi_pct,
                rationale=rationale,
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.LOW,
                sensitivity_range=sens,
                source="expert_initial_v1",
            ))

    return NationalityClassificationSet(
        year=year,
        classifications=classifications,
        metadata={
            "method": "Expert judgment initial classification",
            "version": "v1",
            "granularity": "section_x_isco_major_group",
            "total_cells": len(classifications),
            "tier_ranges_for_mvp11": {
                "saudi_ready": "0.70-1.00",
                "saudi_trainable": "0.20-0.60",
                "expat_reliant": "0.00-0.20",
            },
            "note": "Tiers are the output, NOT point estimates. "
                    "MVP-11 will convert to ranges for analysis.",
        },
    )


def save_nationality_classification(
    classification_set: NationalityClassificationSet,
    output_dir: str | Path = "data/curated",
) -> Path:
    """Save nationality classification to curated JSON with provenance."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries_out = []
    for c in classification_set.classifications:
        entries_out.append({
            "sector_code": c.sector_code,
            "occupation_code": c.occupation_code,
            "tier": c.tier.value,
            "current_saudi_pct": c.current_saudi_pct,
            "rationale": c.rationale,
            "source_confidence": c.source_confidence.value,
            "quality_confidence": c.quality_confidence.value,
            "sensitivity_range": list(c.sensitivity_range) if c.sensitivity_range else None,
            "source": c.source,
        })

    output = {
        "_provenance": {
            "builder": "build_nationality_classification.py",
            "builder_version": "d4_v1",
            "build_timestamp": datetime.now(tz=UTC).isoformat(),
            "source_ids": ["expert_initial_v1"],
            "method": "Expert judgment with DataSaudi/GOSI calibration",
            "notes": "All v1 entries are ASSUMED confidence",
        },
        "year": classification_set.year,
        "total_classifications": len(entries_out),
        "classifications": entries_out,
        "metadata": dict(classification_set.metadata),
    }

    out_path = out_dir / "saudi_nationality_classification_v1.json"
    out_path.write_text(json.dumps(output, indent=2))
    return out_path
