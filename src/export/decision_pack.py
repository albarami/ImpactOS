"""Decision Pack generator — MVP-6 Section 14.

Assemble a complete Decision Pack from a governed run:
executive summary, sector impact tables, multipliers, direct/indirect
decomposition, import leakage, employment impacts, sensitivity envelope,
assumption register, evidence ledger.

Output as structured data ready for templating into Excel/PPTX/PDF.
Deterministic — no LLM calls.
"""

from dataclasses import asdict, dataclass, field
from uuid import UUID


@dataclass
class SectorImpact:
    """Single sector impact row in the Decision Pack."""

    sector_code: str
    sector_name: str
    direct_impact: float
    indirect_impact: float
    total_impact: float
    multiplier: float
    domestic_share: float
    import_leakage: float


@dataclass
class DecisionPack:
    """Complete Decision Pack — structured data for templating."""

    run_id: UUID
    scenario_name: str
    base_year: int
    currency: str

    executive_summary: dict
    sector_impacts: list[SectorImpact]
    employment: dict
    sensitivity: list[dict]
    assumptions: list[dict]
    evidence_ledger: list[dict]
    import_leakage_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for JSON / template rendering."""
        return {
            "run_id": str(self.run_id),
            "scenario_name": self.scenario_name,
            "base_year": self.base_year,
            "currency": self.currency,
            "executive_summary": self.executive_summary,
            "sector_impacts": [asdict(si) for si in self.sector_impacts],
            "employment": self.employment,
            "sensitivity": self.sensitivity,
            "assumptions": self.assumptions,
            "evidence_ledger": self.evidence_ledger,
            "import_leakage_summary": self.import_leakage_summary,
        }


class DecisionPackBuilder:
    """Build a Decision Pack from run outputs."""

    def build(
        self,
        *,
        run_id: UUID,
        scenario_name: str,
        headline_gdp: float,
        headline_jobs: int,
        sector_impacts: list[dict],
        employment: dict,
        sensitivity: list[dict],
        assumptions: list[dict],
        evidence_ledger: list[dict],
        base_year: int,
        currency: str = "SAR",
    ) -> DecisionPack:
        """Assemble the complete Decision Pack."""
        # Build sector impact objects
        si_objects = [
            SectorImpact(
                sector_code=si["sector_code"],
                sector_name=si["sector_name"],
                direct_impact=si["direct_impact"],
                indirect_impact=si["indirect_impact"],
                total_impact=si["total_impact"],
                multiplier=si["multiplier"],
                domestic_share=si["domestic_share"],
                import_leakage=si["import_leakage"],
            )
            for si in sector_impacts
        ]

        # Compute import leakage summary
        total_direct = sum(si.direct_impact for si in si_objects)
        total_indirect = sum(si.indirect_impact for si in si_objects)
        total_impact = sum(si.total_impact for si in si_objects)
        total_import_leakage = sum(
            si.total_impact * si.import_leakage for si in si_objects
        )
        total_domestic = sum(
            si.total_impact * si.domestic_share for si in si_objects
        )

        import_leakage_summary = {
            "total_import_leakage": total_import_leakage,
            "total_domestic_value": total_domestic,
            "total_impact": total_impact,
            "weighted_import_share": total_import_leakage / total_impact if total_impact else 0.0,
        }

        # Build executive summary
        executive_summary = {
            "headline_gdp": headline_gdp,
            "headline_jobs": headline_jobs,
            "scenario_name": scenario_name,
            "base_year": base_year,
            "currency": currency,
            "total_sectors": len(si_objects),
            "total_direct_impact": total_direct,
            "total_indirect_impact": total_indirect,
        }

        return DecisionPack(
            run_id=run_id,
            scenario_name=scenario_name,
            base_year=base_year,
            currency=currency,
            executive_summary=executive_summary,
            sector_impacts=si_objects,
            employment=employment,
            sensitivity=sensitivity,
            assumptions=assumptions,
            evidence_ledger=evidence_ledger,
            import_leakage_summary=import_leakage_summary,
        )
