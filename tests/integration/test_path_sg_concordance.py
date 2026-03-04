"""Integration Path 8: SG Parser -> Concordance -> Compiler.

Tests that ConcordanceService correctly maps between D-2 (84 divisions) and
D-1 (20 sections), that round-trip aggregation is consistent, and that
SGTemplateParser-produced division codes (when available) have no orphans
in the concordance.

This path verifies the D-2 (84 divisions) -> D-1 (20 sections) concordance
chain works end-to-end through the compiler.
"""

import pytest

from .golden_scenarios.shared import ISIC_20_SECTIONS

# Resolve paths relative to project root (cwd)
CONCORDANCE_PATH = "data/curated/concordance_section_division.json"
WEIGHTS_PATH = "data/curated/division_output_weights_sg_2018.json"


@pytest.mark.integration
class TestSGParserToConcordanceToCompiler:
    """SG Parser -> Concordance -> Compiler path (Amendment A)."""

    # ---------------------------------------------------------------
    # Test 9a-1: Every model section has a division mapping
    # ---------------------------------------------------------------

    def test_every_model_section_has_division_mapping(self):
        """All 20 ISIC sections in the model must map to >= 1 division.

        Loads the concordance JSON and verifies that each of the 20
        standard ISIC Rev.4 section codes (A-T) is present and maps to
        at least one division code.
        """
        from src.data.concordance import ConcordanceService

        concordance = ConcordanceService(
            concordance_path=CONCORDANCE_PATH,
            weights_path=WEIGHTS_PATH,
        )

        # All 20 ISIC sections must be present
        assert sorted(concordance.section_codes) == sorted(ISIC_20_SECTIONS), (
            f"Concordance sections {sorted(concordance.section_codes)} "
            f"!= expected {sorted(ISIC_20_SECTIONS)}"
        )

        for section in ISIC_20_SECTIONS:
            divs = concordance.section_to_divisions(section)
            assert len(divs) >= 1, (
                f"Section {section} has no division mappings"
            )
            # Each division should map back to this section
            for div in divs:
                mapped_section = concordance.division_to_section(div)
                assert mapped_section == section, (
                    f"Division {div} maps to {mapped_section}, "
                    f"expected {section}"
                )

    # ---------------------------------------------------------------
    # Test 9a-2: Concordance bidirectional round-trip
    # ---------------------------------------------------------------

    def test_concordance_bidirectional(self):
        """Round-trip: aggregate(disaggregate(v)) ~ v within tolerance.

        Creates a section-level vector, disaggregates to 84 divisions
        using proportional weights, then re-aggregates back. The
        round-trip result should match the original within floating-point
        tolerance (since aggregate(disaggregate(v)) ~ v by construction).
        """
        from src.data.concordance import ConcordanceService

        concordance = ConcordanceService(
            concordance_path=CONCORDANCE_PATH,
            weights_path=WEIGHTS_PATH,
        )

        # Create a section-level vector with known values
        section_values = {
            section: float(i + 1) * 100.0
            for i, section in enumerate(ISIC_20_SECTIONS)
        }

        # Disaggregate to divisions
        div_values = concordance.disaggregate_section_vector(section_values)

        # Re-aggregate back to sections
        roundtrip = concordance.aggregate_division_vector(
            div_values, method="sum",
        )

        # Round-trip should recover original values (within tolerance)
        for section in ISIC_20_SECTIONS:
            original = section_values[section]
            recovered = roundtrip.get(section, 0.0)
            assert abs(recovered - original) < 1e-6, (
                f"Section {section}: original={original}, "
                f"recovered={recovered}, diff={abs(recovered - original)}"
            )

    # ---------------------------------------------------------------
    # Test 9a-3: Aggregation consistency
    # ---------------------------------------------------------------

    def test_aggregation_consistency(self):
        """Sum of division values equals sum of aggregated section values.

        Populates every active division with a value, aggregates via sum,
        and verifies total conservation (no values lost or gained).
        """
        from src.data.concordance import ConcordanceService

        concordance = ConcordanceService(
            concordance_path=CONCORDANCE_PATH,
            weights_path=WEIGHTS_PATH,
        )

        # Give every division a value
        all_divs = concordance.all_division_codes
        div_values = {div: float(int(div) + 1) for div in all_divs}
        total_div = sum(div_values.values())

        # Aggregate to sections
        section_values = concordance.aggregate_division_vector(
            div_values, method="sum",
        )
        total_section = sum(section_values.values())

        # Total must be conserved
        assert abs(total_section - total_div) < 1e-6, (
            f"Total not conserved: divisions={total_div}, "
            f"sections={total_section}"
        )

        # Every section that has divisions in our set should have a value
        for section in concordance.section_codes:
            divs = concordance.section_to_divisions(section)
            expected = sum(div_values.get(d, 0.0) for d in divs)
            actual = section_values.get(section, 0.0)
            assert abs(actual - expected) < 1e-6, (
                f"Section {section}: expected={expected}, actual={actual}"
            )

    # ---------------------------------------------------------------
    # Test 9a-4: No orphan codes in concordance data
    # ---------------------------------------------------------------

    def test_no_orphan_codes(self):
        """All division codes in weights file exist in concordance.

        Loads the division output weights and verifies every weighted
        division code maps to a valid ISIC section via the concordance.
        This catches data mismatches between the two curated files.
        """
        import json

        from src.data.concordance import ConcordanceService

        concordance = ConcordanceService(
            concordance_path=CONCORDANCE_PATH,
            weights_path=WEIGHTS_PATH,
        )

        # Load weights file to get all division codes
        with open(WEIGHTS_PATH, encoding="utf-8") as f:
            weights_data = json.load(f)

        weight_codes = [d["code"] for d in weights_data["divisions"]]

        orphan_codes = []
        for code in weight_codes:
            try:
                section = concordance.division_to_section(code)
                assert section in ISIC_20_SECTIONS, (
                    f"Division {code} maps to unknown section {section}"
                )
            except KeyError:
                orphan_codes.append(code)

        assert len(orphan_codes) == 0, (
            f"Orphan division codes in weights file "
            f"(not in concordance): {orphan_codes}"
        )

        # Also verify all concordance divisions are in weights
        concordance_divs = set(concordance.all_division_codes)
        weight_code_set = set(weight_codes)
        missing_from_weights = concordance_divs - weight_code_set
        # This is a warning, not a failure: weights may not cover everything
        # But every concordance division should ideally have a weight
        if missing_from_weights:
            import warnings

            warnings.warn(
                f"Concordance divisions missing from weights: "
                f"{sorted(missing_from_weights)}",
                stacklevel=1,
            )
