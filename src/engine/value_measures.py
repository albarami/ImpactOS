"""Value Measures satellite — Sprint 16 (Section 7.11).

Deterministic computation of 8 macroeconomic indicators from engine outputs
and model artifacts. Pure math — no LLM calls.

Formulas:
  GDP basic    = Σ(va_ratio_i · Δx_i)
  GDP market   = GDP_basic + Σ(tax_ratio_i · Δx_i)
  GDP real     = GDP_market / deflator(base_year)
  GDP intensity = GDP_market / Σ(Δx)
  BoT          = Σ(export_ratio_i · Δx_i) - Σ(import_ratio_i · Δx_i)
  Non-oil exports = Σ(export_ratio_i · Δx_i) for i ∉ oil
  Gov non-oil rev = Σ(tax_ratio_i · Δx_i) for i ∉ oil
  Gov rev/spend  = gov_revenue / gov_spending_effect
"""

from dataclasses import dataclass

import numpy as np

from src.engine.model_store import LoadedModel
from src.engine.satellites import SatelliteResult
from src.engine.value_measures_validation import (
    validate_value_measures_prerequisites,
)


@dataclass(frozen=True)
class ValueMeasuresResult:
    """Immutable result of value-measures computation."""

    gdp_basic_price: float
    gdp_market_price: float
    gdp_real: float
    gdp_intensity: float
    balance_of_trade: float
    non_oil_exports: float
    government_non_oil_revenue: float
    government_revenue_spending_ratio: float
    # Per-sector breakdowns for ResultSet emission
    gdp_basic_by_sector: np.ndarray
    tax_effect_by_sector: np.ndarray
    export_effect_by_sector: np.ndarray


class ValueMeasuresComputer:
    """Deterministic value-measures calculator (Section 7.11)."""

    def compute(
        self,
        *,
        delta_x: np.ndarray,
        sat_result: SatelliteResult,
        loaded_model: LoadedModel,
        base_year: int,
        oil_sector_codes: frozenset[str] = frozenset(),
    ) -> ValueMeasuresResult:
        """Compute all 8 value measures.

        Args:
            delta_x: Total output change vector (n).
            sat_result: Satellite result (provides delta_va, delta_imports).
            loaded_model: Model with value-measures artifacts.
            base_year: Base year for deflator lookup.
            oil_sector_codes: Set of sector codes classified as oil.

        Returns:
            ValueMeasuresResult with all 8 indicators.

        Raises:
            ValueMeasuresValidationError: If prerequisites invalid.
        """
        delta_x = np.asarray(delta_x, dtype=np.float64)
        n = loaded_model.n

        # Validate prerequisites (raises on failure)
        validated = validate_value_measures_prerequisites(
            n=n,
            x=loaded_model.x,
            gross_operating_surplus=loaded_model.gross_operating_surplus_array,
            taxes_less_subsidies=loaded_model.taxes_less_subsidies_array,
            final_demand_f=loaded_model.final_demand_f_array,
            imports_vector=loaded_model.imports_vector_array,
            deflator_series=loaded_model.model_version.deflator_series,
            base_year=base_year,
        )

        # --- GDP at basic price ---
        gdp_basic_by_sector = sat_result.delta_va
        gdp_basic = float(np.sum(gdp_basic_by_sector))

        # --- GDP at market price ---
        tax_effect_by_sector = validated.tax_ratio * delta_x
        tax_effect_total = float(np.sum(tax_effect_by_sector))
        gdp_market = gdp_basic + tax_effect_total

        # --- Real GDP ---
        gdp_real = gdp_market / validated.deflator

        # --- GDP intensity ---
        total_output = float(np.sum(delta_x))
        gdp_intensity = gdp_market / total_output if total_output != 0 else 0.0

        # --- Balance of trade ---
        export_effect_by_sector = validated.export_ratio * delta_x
        export_total = float(np.sum(export_effect_by_sector))
        import_total = float(np.sum(sat_result.delta_imports))
        bot = export_total - import_total

        # --- Oil sector mask ---
        sector_codes = loaded_model.sector_codes
        oil_mask = np.array(
            [code in oil_sector_codes for code in sector_codes],
            dtype=bool,
        )
        non_oil_mask = ~oil_mask

        # --- Non-oil exports ---
        non_oil_exports = float(np.sum(export_effect_by_sector[non_oil_mask]))

        # --- Government non-oil revenue ---
        gov_non_oil_revenue = float(np.sum(tax_effect_by_sector[non_oil_mask]))

        # --- Government revenue/spending ratio ---
        gov_spending_effect = float(
            np.sum(validated.gov_spending_ratio * delta_x)
        )
        if gov_spending_effect != 0:
            gov_rev_spend_ratio = gov_non_oil_revenue / gov_spending_effect
        else:
            gov_rev_spend_ratio = 0.0

        return ValueMeasuresResult(
            gdp_basic_price=gdp_basic,
            gdp_market_price=gdp_market,
            gdp_real=gdp_real,
            gdp_intensity=gdp_intensity,
            balance_of_trade=bot,
            non_oil_exports=non_oil_exports,
            government_non_oil_revenue=gov_non_oil_revenue,
            government_revenue_spending_ratio=gov_rev_spend_ratio,
            gdp_basic_by_sector=gdp_basic_by_sector,
            tax_effect_by_sector=tax_effect_by_sector,
            export_effect_by_sector=export_effect_by_sector,
        )
