"""Dashboard data service — MVP-7.

Aggregate metrics across engagements for partner dashboard:
- Scenario throughput trends
- Average cycle time
- NFF compliance rates
- Library growth (mappings, assumptions, patterns)

Return structured data for frontend consumption.
Deterministic — no LLM calls.
"""

from dataclasses import dataclass, field


@dataclass
class DashboardSummary:
    """Aggregated dashboard data."""

    total_engagements: int
    total_scenarios: int
    avg_scenarios_per_engagement: float
    avg_cycle_time_hours: float
    nff_compliance_rate: float
    avg_claim_support_rate: float
    scenario_throughput: list[int]
    library_mappings: int
    library_assumptions: int
    library_patterns: int

    def to_dict(self) -> dict:
        return {
            "total_engagements": self.total_engagements,
            "total_scenarios": self.total_scenarios,
            "avg_scenarios_per_engagement": self.avg_scenarios_per_engagement,
            "avg_cycle_time_hours": self.avg_cycle_time_hours,
            "nff_compliance_rate": self.nff_compliance_rate,
            "avg_claim_support_rate": self.avg_claim_support_rate,
            "scenario_throughput": self.scenario_throughput,
            "library_mappings": self.library_mappings,
            "library_assumptions": self.library_assumptions,
            "library_patterns": self.library_patterns,
        }


class DashboardService:
    """Compute dashboard summary across engagements."""

    def compute_summary(
        self,
        *,
        engagements: list[dict],
        library: dict,
    ) -> DashboardSummary:
        """Aggregate metrics from engagement data."""
        total = len(engagements)

        if total == 0:
            return DashboardSummary(
                total_engagements=0,
                total_scenarios=0,
                avg_scenarios_per_engagement=0.0,
                avg_cycle_time_hours=0.0,
                nff_compliance_rate=0.0,
                avg_claim_support_rate=0.0,
                scenario_throughput=[],
                library_mappings=library.get("mappings_count", 0),
                library_assumptions=library.get("assumptions_count", 0),
                library_patterns=library.get("patterns_count", 0),
            )

        scenarios = [e.get("scenarios_count", 0) for e in engagements]
        total_scenarios = sum(scenarios)
        cycle_times = [e.get("cycle_time_hours", 0.0) for e in engagements]
        nff_passed = sum(1 for e in engagements if e.get("nff_passed", False))

        total_claims = sum(e.get("claims_total", 0) for e in engagements)
        total_supported = sum(e.get("claims_supported", 0) for e in engagements)

        return DashboardSummary(
            total_engagements=total,
            total_scenarios=total_scenarios,
            avg_scenarios_per_engagement=total_scenarios / total,
            avg_cycle_time_hours=sum(cycle_times) / total,
            nff_compliance_rate=nff_passed / total,
            avg_claim_support_rate=total_supported / total_claims if total_claims else 0.0,
            scenario_throughput=scenarios,
            library_mappings=library.get("mappings_count", 0),
            library_assumptions=library.get("assumptions_count", 0),
            library_patterns=library.get("patterns_count", 0),
        )
