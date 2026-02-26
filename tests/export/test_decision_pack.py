"""Tests for Decision Pack generator (MVP-6).

Covers: assembling a complete Decision Pack from a governed run —
executive summary, sector impacts, multipliers, import leakage,
employment impacts, sensitivity, assumptions, evidence ledger.
"""

import pytest
from uuid_extensions import uuid7

from src.export.decision_pack import DecisionPackBuilder, DecisionPack, SectorImpact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = uuid7()
SCENARIO_NAME = "NEOM Logistics Zone"


def _make_sector_impacts() -> list[dict]:
    return [
        {
            "sector_code": "C41",
            "sector_name": "Structural Steel",
            "direct_impact": 500_000_000.0,
            "indirect_impact": 250_000_000.0,
            "total_impact": 750_000_000.0,
            "multiplier": 1.5,
            "domestic_share": 0.65,
            "import_leakage": 0.35,
        },
        {
            "sector_code": "F",
            "sector_name": "Construction",
            "direct_impact": 1_000_000_000.0,
            "indirect_impact": 800_000_000.0,
            "total_impact": 1_800_000_000.0,
            "multiplier": 1.8,
            "domestic_share": 0.70,
            "import_leakage": 0.30,
        },
    ]


def _make_employment() -> dict:
    return {
        "direct_jobs": 12500,
        "indirect_jobs": 8700,
        "total_jobs": 21200,
        "saudization_pct": 0.32,
    }


def _make_sensitivity() -> list[dict]:
    return [
        {"assumption": "Import Share", "low": 3.8e9, "base": 4.2e9, "high": 4.6e9},
        {"assumption": "Phasing", "low": 3.9e9, "base": 4.2e9, "high": 4.4e9},
    ]


def _make_assumptions() -> list[dict]:
    return [
        {
            "name": "Domestic content share",
            "value": 0.65,
            "units": "ratio",
            "range_min": 0.55,
            "range_max": 0.75,
            "status": "APPROVED",
        },
    ]


def _make_evidence() -> list[dict]:
    return [
        {
            "snippet_id": str(uuid7()),
            "source": "SAMA Q3 2024 Report",
            "text": "Steel prices increased 15%",
            "page": 42,
        },
    ]


def _build_pack() -> DecisionPack:
    builder = DecisionPackBuilder()
    return builder.build(
        run_id=RUN_ID,
        scenario_name=SCENARIO_NAME,
        headline_gdp=4_200_000_000.0,
        headline_jobs=21200,
        sector_impacts=_make_sector_impacts(),
        employment=_make_employment(),
        sensitivity=_make_sensitivity(),
        assumptions=_make_assumptions(),
        evidence_ledger=_make_evidence(),
        base_year=2023,
        currency="SAR",
    )


# ===================================================================
# Decision Pack structure
# ===================================================================


class TestDecisionPackStructure:
    """Decision Pack contains all required sections."""

    def test_has_executive_summary(self) -> None:
        pack = _build_pack()
        assert pack.executive_summary is not None
        assert pack.executive_summary["headline_gdp"] == 4_200_000_000.0
        assert pack.executive_summary["headline_jobs"] == 21200

    def test_has_sector_impacts(self) -> None:
        pack = _build_pack()
        assert len(pack.sector_impacts) == 2
        assert isinstance(pack.sector_impacts[0], SectorImpact)

    def test_sector_impact_fields(self) -> None:
        pack = _build_pack()
        si = pack.sector_impacts[0]
        assert si.sector_code == "C41"
        assert si.multiplier == 1.5
        assert si.direct_impact == 500_000_000.0
        assert si.indirect_impact == 250_000_000.0

    def test_has_employment(self) -> None:
        pack = _build_pack()
        assert pack.employment["direct_jobs"] == 12500
        assert pack.employment["total_jobs"] == 21200

    def test_has_sensitivity(self) -> None:
        pack = _build_pack()
        assert len(pack.sensitivity) == 2

    def test_has_assumptions(self) -> None:
        pack = _build_pack()
        assert len(pack.assumptions) >= 1

    def test_has_evidence_ledger(self) -> None:
        pack = _build_pack()
        assert len(pack.evidence_ledger) >= 1

    def test_has_run_metadata(self) -> None:
        pack = _build_pack()
        assert pack.run_id == RUN_ID
        assert pack.scenario_name == SCENARIO_NAME
        assert pack.currency == "SAR"
        assert pack.base_year == 2023


# ===================================================================
# Computed summaries
# ===================================================================


class TestComputedSummaries:
    """Decision Pack computes aggregate summaries."""

    def test_total_gdp_impact(self) -> None:
        pack = _build_pack()
        total = sum(si.total_impact for si in pack.sector_impacts)
        assert total == 2_550_000_000.0

    def test_import_leakage_summary(self) -> None:
        pack = _build_pack()
        assert pack.import_leakage_summary is not None
        assert "total_import_leakage" in pack.import_leakage_summary

    def test_multiplier_range(self) -> None:
        pack = _build_pack()
        multipliers = [si.multiplier for si in pack.sector_impacts]
        assert min(multipliers) == 1.5
        assert max(multipliers) == 1.8


# ===================================================================
# Serialization
# ===================================================================


class TestSerialization:
    """Decision Pack can be serialized for templating."""

    def test_to_dict(self) -> None:
        pack = _build_pack()
        d = pack.to_dict()
        assert isinstance(d, dict)
        assert "executive_summary" in d
        assert "sector_impacts" in d
        assert "employment" in d
        assert "sensitivity" in d
        assert "assumptions" in d
        assert "evidence_ledger" in d
        assert "run_id" in d

    def test_to_dict_sector_impacts_are_dicts(self) -> None:
        pack = _build_pack()
        d = pack.to_dict()
        assert isinstance(d["sector_impacts"][0], dict)
