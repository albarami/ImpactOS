"""Bidirectional mapping between ISIC section (20) and division (84) levels.

Supports:
    - Division -> Section lookup (lossless)
    - Section -> Divisions lookup (lossless)
    - Aggregate: 84-division vector -> 20-section vector (sum or weighted avg)
    - Disaggregate: 20-section vector -> 84-division vector (proportional, lossy)

IMPORTANT: Disaggregation is a lossy operation.
    aggregate(disaggregate(v)) ~ v  (within tolerance)
    BUT disaggregate(aggregate(v)) != v  (information lost)
"""

from __future__ import annotations

import json
import warnings


class ConcordanceService:
    """Bidirectional mapping between ISIC section (20) and division (84) levels."""

    def __init__(
        self,
        concordance_path: str,
        weights_path: str | None = None,
    ) -> None:
        """Load concordance and optional division weights.

        Args:
            concordance_path: Path to concordance_section_division.json.
            weights_path: Optional path to division_output_weights_sg_2018.json.
        """
        with open(concordance_path, encoding="utf-8") as f:
            data = json.load(f)

        # Build lookup tables
        self._div_to_section: dict[str, str] = {}
        self._section_to_divs: dict[str, list[str]] = {}
        self._section_order: list[str] = []

        for mapping in data["mappings"]:
            section = mapping["section_code"]
            divs = mapping["division_codes"]
            self._section_to_divs[section] = divs
            self._section_order.append(section)
            for div in divs:
                self._div_to_section[div] = section

        # Load optional weights
        self._weights: dict[str, float] | None = None
        if weights_path is not None:
            with open(weights_path, encoding="utf-8") as f:
                weights_data = json.load(f)
            self._weights = {
                d["code"]: float(d["total_output"])
                for d in weights_data["divisions"]
            }

    # -----------------------------------------------------------------
    # Basic lookups
    # -----------------------------------------------------------------

    def division_to_section(self, division_code: str) -> str:
        """Map division code to section code.

        '06' -> 'B'.

        Raises:
            KeyError: If division_code is not in the active concordance.
        """
        try:
            return self._div_to_section[division_code]
        except KeyError:
            raise KeyError(
                f"Unknown or inactive division code: '{division_code}'. "
                f"Only 84 active SG divisions are mapped."
            ) from None

    def section_to_divisions(self, section_code: str) -> list[str]:
        """Map section code to active division codes.

        'B' -> ['05', '06', '07', '08', '09'].

        Raises:
            KeyError: If section_code is not a valid ISIC section.
        """
        try:
            return list(self._section_to_divs[section_code])
        except KeyError:
            raise KeyError(
                f"Unknown section code: '{section_code}'. "
                f"Valid sections: {sorted(self._section_to_divs.keys())}"
            ) from None

    @property
    def section_codes(self) -> list[str]:
        """Ordered list of all section codes."""
        return list(self._section_order)

    @property
    def all_division_codes(self) -> list[str]:
        """All active division codes in sorted order."""
        return sorted(self._div_to_section.keys())

    # -----------------------------------------------------------------
    # Aggregation (84-division -> 20-section)
    # -----------------------------------------------------------------

    def aggregate_division_vector(
        self,
        division_values: dict[str, float],
        method: str = "sum",
    ) -> dict[str, float]:
        """Aggregate 84-division vector to 20-section vector.

        Args:
            division_values: {division_code: value} dict.
            method: 'sum' for absolute values (SAR amounts),
                    'weighted_avg' for ratios/percentages (requires weights).

        Returns:
            {section_code: aggregated_value} dict for all sections
            that have at least one contributing division.
        """
        if method == "sum":
            return self._aggregate_sum(division_values)
        elif method == "weighted_avg":
            return self._aggregate_weighted_avg(division_values)
        else:
            raise ValueError(f"Unknown aggregation method: '{method}'")

    def _aggregate_sum(
        self,
        division_values: dict[str, float],
    ) -> dict[str, float]:
        """Simple sum aggregation."""
        result: dict[str, float] = {}
        for div_code, value in division_values.items():
            if div_code not in self._div_to_section:
                continue
            section = self._div_to_section[div_code]
            result[section] = result.get(section, 0.0) + value
        return result

    def _aggregate_weighted_avg(
        self,
        division_values: dict[str, float],
    ) -> dict[str, float]:
        """Weighted average aggregation using division output weights."""
        if self._weights is None:
            raise ValueError(
                "Weighted average requires division weights. "
                "Pass weights_path to constructor."
            )
        result: dict[str, float] = {}
        for section, divs in self._section_to_divs.items():
            total_weight = 0.0
            weighted_sum = 0.0
            for div in divs:
                if div in division_values and div in self._weights:
                    w = self._weights[div]
                    weighted_sum += division_values[div] * w
                    total_weight += w
            if total_weight > 0:
                result[section] = weighted_sum / total_weight
        return result

    # -----------------------------------------------------------------
    # Disaggregation (20-section -> 84-division)
    # -----------------------------------------------------------------

    def disaggregate_section_vector(
        self,
        section_values: dict[str, float],
        weights: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Disaggregate 20-section vector to 84-division vector.

        Uses proportional allocation based on weights.
        If weights not available, distributes equally (with warning).

        IMPORTANT: This operation is lossy.
            aggregate(disaggregate(v)) ~ v  (within tolerance)
            BUT disaggregate(aggregate(v)) != v  (information lost)

        Args:
            section_values: {section_code: value} dict.
            weights: Optional override weights {div_code: weight}.
                     Falls back to constructor weights, then equal split.

        Returns:
            {division_code: value} dict.
        """
        effective_weights = weights or self._weights
        use_equal = effective_weights is None

        if use_equal:
            warnings.warn(
                "No division weights available. Using equal distribution "
                "across divisions within each section. Results will be "
                "approximate.",
                UserWarning,
                stacklevel=2,
            )

        result: dict[str, float] = {}
        for section_code, section_value in section_values.items():
            if section_code not in self._section_to_divs:
                continue
            divs = self._section_to_divs[section_code]

            if use_equal:
                # Equal split
                per_div = section_value / len(divs)
                for div in divs:
                    result[div] = per_div
            else:
                # Proportional split by weight
                div_weights = {
                    d: effective_weights.get(d, 0.0)
                    for d in divs
                }
                total_w = sum(div_weights.values())
                if total_w <= 0:
                    # Fallback to equal
                    per_div = section_value / len(divs)
                    for div in divs:
                        result[div] = per_div
                else:
                    for div in divs:
                        share = div_weights[div] / total_w
                        result[div] = section_value * share

        return result
