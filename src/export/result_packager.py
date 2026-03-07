"""Result Packager — P5-4 Run Path Completeness.

Converts ResultSet rows from the engine into a structured pack_data dict
suitable for DecisionPackBuilder or direct JSON for UI consumption.

Bridges the gap between the engine's per-metric ResultSet output and the
export pipeline's DecisionPack input format.

Deterministic — no LLM calls.
"""

from __future__ import annotations

from src.models.run import ResultSet


class ResultPackager:
    """Convert ResultSet rows into DecisionPack-compatible pack_data."""

    def package(
        self,
        *,
        result_sets: list[ResultSet],
        scenario_name: str,
        base_year: int,
        currency: str = "SAR",
        run_id: str | None = None,
        model_version_id: str | None = None,
        scenario_version: int = 1,
        assumptions: list[dict] | None = None,
        evidence_ledger: list[dict] | None = None,
    ) -> dict:
        """Package result sets into a dict suitable for export.

        Args:
            result_sets: List of ResultSet objects from engine run.
            scenario_name: Name of the scenario.
            base_year: Base year for the scenario.
            currency: Currency code (default SAR).
            run_id: Optional run ID string.
            model_version_id: Optional model version ID string.
            scenario_version: Scenario version number.
            assumptions: Optional list of assumption dicts.
            evidence_ledger: Optional list of evidence dicts.

        Returns:
            Dict suitable for ExportRequest.pack_data or DecisionPackBuilder.
        """
        # Group cumulative result sets by metric_type
        metrics: dict[str, ResultSet] = {}
        for rs in result_sets:
            # Only take cumulative (non-annual) rows
            if rs.series_kind is None:
                metrics[rs.metric_type] = rs

        # Extract per-sector data
        total_output = metrics.get("total_output")
        direct_effect = metrics.get("direct_effect")
        indirect_effect = metrics.get("indirect_effect")
        employment = metrics.get("employment")
        imports = metrics.get("imports")
        domestic = metrics.get("domestic_output")
        value_added = metrics.get("value_added")

        # Build sector impacts
        sector_impacts: list[dict] = []
        if total_output:
            sector_codes = [
                k for k in total_output.values.keys() if not k.startswith("_")
            ]

            for code in sector_codes:
                total = total_output.values.get(code, 0.0)
                direct = (
                    direct_effect.values.get(code, 0.0)
                    if direct_effect else 0.0
                )
                indirect = (
                    indirect_effect.values.get(code, 0.0)
                    if indirect_effect else 0.0
                )
                imp = imports.values.get(code, 0.0) if imports else 0.0
                dom = domestic.values.get(code, 0.0) if domestic else 0.0

                # Compute derived values
                multiplier = total / direct if direct != 0 else 0.0
                dom_share = dom / total if total != 0 else 0.0
                imp_share = imp / total if total != 0 else 0.0

                sector_impacts.append({
                    "sector_code": code,
                    "sector_name": code,  # Placeholder — real name from taxonomy
                    "direct_impact": direct,
                    "indirect_impact": indirect,
                    "total_impact": total,
                    "multiplier": round(multiplier, 4),
                    "domestic_share": round(dom_share, 4),
                    "import_leakage": round(imp_share, 4),
                })

        # Sort by total impact descending
        sector_impacts.sort(key=lambda si: si["total_impact"], reverse=True)

        # Build employment section
        employment_data: dict[str, float] = {}
        total_jobs = 0.0
        if employment:
            employment_data = {
                k: v for k, v in employment.values.items()
                if not k.startswith("_")
            }
            total_jobs = sum(employment_data.values())

        # Build executive summary
        headline_gdp = 0.0
        gdp_result = metrics.get("gdp_basic_price") or metrics.get("gdp_market_price")
        if gdp_result:
            headline_gdp = gdp_result.values.get("_total", sum(
                v for k, v in gdp_result.values.items() if not k.startswith("_")
            ))
        elif value_added:
            headline_gdp = sum(
                v for k, v in value_added.values.items()
                if not k.startswith("_")
            )

        executive_summary = {
            "headline_gdp": headline_gdp,
            "headline_jobs": int(total_jobs),
            "scenario_name": scenario_name,
            "base_year": base_year,
            "currency": currency,
            "total_sectors": len(sector_impacts),
            "total_direct_impact": sum(si["direct_impact"] for si in sector_impacts),
            "total_indirect_impact": sum(si["indirect_impact"] for si in sector_impacts),
        }

        # Build input vectors (shock vector summary)
        input_vectors: dict[str, float] = {}
        if direct_effect:
            input_vectors = {
                k: v for k, v in direct_effect.values.items()
                if not k.startswith("_") and abs(v) > 0
            }

        return {
            "run_id": run_id or "",
            "scenario_name": scenario_name,
            "base_year": base_year,
            "currency": currency,
            "model_version_id": model_version_id or "",
            "scenario_version": scenario_version,
            "executive_summary": executive_summary,
            "sector_impacts": sector_impacts,
            "employment": employment_data,
            "input_vectors": input_vectors,
            "sensitivity": [],
            "assumptions": assumptions or [],
            "evidence_ledger": evidence_ledger or [],
        }
