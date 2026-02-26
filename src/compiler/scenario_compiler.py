"""Scenario compilation service — MVP-4 Section 9.

Takes BoQLineItems + MappingDecisions, aggregates into sector-year shock
vectors (Δd), applies domestic/import splits, phasing, and deflation.
Produces a complete ScenarioSpec with DataQualitySummary.

Deterministic — no LLM calls.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from src.models.document import BoQLineItem
from src.models.mapping import DecisionType, MappingDecision
from src.models.scenario import (
    DataQualitySummary,
    FinalDemandShock,
    MappingConfidence,
    ScenarioSpec,
    ShockItem,
    TimeHorizon,
)


@dataclass
class CompilationInput:
    """All inputs needed for scenario compilation."""

    workspace_id: UUID
    scenario_name: str
    base_model_version_id: UUID
    base_year: int
    time_horizon: TimeHorizon
    line_items: list[BoQLineItem]
    decisions: list[MappingDecision]
    default_domestic_share: float = 0.65
    default_import_share: float = 0.35
    phasing: dict[int, float] = field(default_factory=dict)
    deflators: dict[int, float] = field(default_factory=dict)


class ScenarioCompiler:
    """Deterministic scenario compilation: BoQ → ScenarioSpec."""

    def compile(self, inp: CompilationInput) -> ScenarioSpec:
        """Compile line items and mapping decisions into a ScenarioSpec.

        Steps per Section 9.3:
        1. Match decisions to line items
        2. Filter to resolved (APPROVED/OVERRIDDEN) decisions
        3. Aggregate by sector
        4. Apply phasing across years
        5. Apply domestic/import splits
        6. Generate DataQualitySummary
        """
        # Build decision lookup: line_item_id → MappingDecision
        decision_map: dict[UUID, MappingDecision] = {
            d.line_item_id: d for d in inp.decisions
        }

        # Classify items
        resolved_spend: dict[str, float] = defaultdict(float)  # sector → total value
        total_spend = 0.0
        mapped_spend = 0.0
        unresolved_count = 0
        confidence_values: list[float] = []

        for li in inp.line_items:
            value = li.total_value or 0.0
            total_spend += value

            decision = decision_map.get(li.line_item_id)
            if decision is None:
                unresolved_count += 1
                continue

            if decision.suggested_confidence is not None:
                confidence_values.append(decision.suggested_confidence)

            if decision.decision_type in (DecisionType.APPROVED, DecisionType.OVERRIDDEN):
                if decision.final_sector_code:
                    resolved_spend[decision.final_sector_code] += value
                    mapped_spend += value
                else:
                    unresolved_count += 1
            else:
                # DEFERRED or EXCLUDED → residual bucket
                unresolved_count += 1

        # Build shock items: sector × year
        shock_items: list[ShockItem] = []
        for sector_code, sector_total in resolved_spend.items():
            for year, share in inp.phasing.items():
                amount = sector_total * share

                # Apply deflation if present
                deflator = inp.deflators.get(year, 1.0)
                amount_real = amount / deflator

                shock = FinalDemandShock(
                    sector_code=sector_code,
                    year=year,
                    amount_real_base_year=amount_real,
                    domestic_share=inp.default_domestic_share,
                    import_share=inp.default_import_share,
                )
                shock_items.append(shock)

        # DataQualitySummary
        coverage = mapped_spend / total_spend if total_spend > 0 else 0.0
        confidence_summary = self._compute_confidence_histogram(confidence_values)

        dqs = DataQualitySummary(
            base_table_vintage_years=0,
            boq_coverage_pct=coverage,
            mapping_confidence=confidence_summary,
            unresolved_items_count=unresolved_count,
            assumptions_count=0,
        )

        return ScenarioSpec(
            name=inp.scenario_name,
            workspace_id=inp.workspace_id,
            base_model_version_id=inp.base_model_version_id,
            base_year=inp.base_year,
            time_horizon=inp.time_horizon,
            shock_items=shock_items,
            data_quality_summary=dqs,
        )

    @staticmethod
    def _compute_confidence_histogram(
        values: list[float],
    ) -> MappingConfidence:
        """Classify confidences into HIGH/MEDIUM/LOW bands (Section 9.5)."""
        if not values:
            return MappingConfidence(high_pct=0.0, medium_pct=0.0, low_pct=0.0)

        total = len(values)
        high = sum(1 for v in values if v >= 0.85)
        medium = sum(1 for v in values if 0.60 <= v < 0.85)
        low = sum(1 for v in values if v < 0.60)

        return MappingConfidence(
            high_pct=high / total,
            medium_pct=medium / total,
            low_pct=low / total,
        )
