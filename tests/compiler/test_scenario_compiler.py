"""Tests for scenario compilation service (MVP-4 Section 9).

Covers: BoQLineItems + MappingDecisions → sector-year shocks,
domestic/import splits, phasing, deflation, ScenarioSpec output,
DataQualitySummary, residual buckets.
"""

import pytest
from uuid_extensions import uuid7

from src.compiler.scenario_compiler import ScenarioCompiler, CompilationInput
from src.models.document import BoQLineItem
from src.models.governance import BoundingBox, EvidenceSnippet
from src.models.mapping import DecisionType, MappingDecision
from src.models.scenario import (
    FinalDemandShock,
    ScenarioSpec,
    TimeHorizon,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORKSPACE_ID = uuid7()
MODEL_VERSION_ID = uuid7()
EXTRACTION_JOB_ID = uuid7()


def _make_line_item(
    description: str = "Steel",
    total_value: float = 1_000_000.0,
    page_ref: int = 0,
) -> BoQLineItem:
    snippet_id = uuid7()
    return BoQLineItem(
        doc_id=uuid7(),
        extraction_job_id=EXTRACTION_JOB_ID,
        raw_text=description,
        description=description,
        quantity=100.0,
        unit="tonnes",
        unit_price=total_value / 100,
        total_value=total_value,
        currency_code="SAR",
        page_ref=page_ref,
        evidence_snippet_ids=[snippet_id],
    )


def _make_decision(
    line_item_id=None,
    sector_code: str = "C41",
    confidence: float = 0.90,
    decision_type: DecisionType = DecisionType.APPROVED,
) -> MappingDecision:
    return MappingDecision(
        line_item_id=line_item_id or uuid7(),
        suggested_sector_code=sector_code,
        suggested_confidence=confidence,
        final_sector_code=sector_code,
        decision_type=decision_type,
        decided_by=uuid7(),
    )


def _make_compilation_input(
    line_items: list[BoQLineItem] | None = None,
    decisions: list[MappingDecision] | None = None,
    default_domestic_share: float = 0.65,
    phasing: dict[int, float] | None = None,
) -> CompilationInput:
    if line_items is None:
        li = _make_line_item()
        line_items = [li]
    if decisions is None:
        decisions = [_make_decision(line_item_id=li.line_item_id) for li in line_items]

    return CompilationInput(
        workspace_id=WORKSPACE_ID,
        scenario_name="Test Scenario",
        base_model_version_id=MODEL_VERSION_ID,
        base_year=2023,
        time_horizon=TimeHorizon(start_year=2026, end_year=2028),
        line_items=line_items,
        decisions=decisions,
        default_domestic_share=default_domestic_share,
        default_import_share=1.0 - default_domestic_share,
        phasing=phasing or {2026: 0.3, 2027: 0.4, 2028: 0.3},
    )


# ===================================================================
# Basic compilation
# ===================================================================


class TestBasicCompilation:
    """Compile BoQLineItems + MappingDecisions into ScenarioSpec."""

    def test_produces_scenario_spec(self) -> None:
        compiler = ScenarioCompiler()
        inp = _make_compilation_input()
        spec = compiler.compile(inp)
        assert isinstance(spec, ScenarioSpec)

    def test_spec_has_shock_items(self) -> None:
        compiler = ScenarioCompiler()
        inp = _make_compilation_input()
        spec = compiler.compile(inp)
        assert len(spec.shock_items) > 0

    def test_spec_has_correct_name(self) -> None:
        compiler = ScenarioCompiler()
        inp = _make_compilation_input()
        spec = compiler.compile(inp)
        assert spec.name == "Test Scenario"

    def test_spec_has_workspace_id(self) -> None:
        compiler = ScenarioCompiler()
        inp = _make_compilation_input()
        spec = compiler.compile(inp)
        assert spec.workspace_id == WORKSPACE_ID

    def test_spec_version_is_one(self) -> None:
        compiler = ScenarioCompiler()
        inp = _make_compilation_input()
        spec = compiler.compile(inp)
        assert spec.version == 1


# ===================================================================
# Sector-year shock aggregation
# ===================================================================


class TestShockAggregation:
    """Line items aggregate into sector-year FinalDemandShock vectors."""

    def test_single_item_produces_shocks_per_year(self) -> None:
        li = _make_line_item(total_value=1_000_000.0)
        dec = _make_decision(line_item_id=li.line_item_id, sector_code="C41")
        compiler = ScenarioCompiler()
        inp = _make_compilation_input(
            line_items=[li], decisions=[dec],
            phasing={2026: 0.5, 2027: 0.5},
        )
        spec = compiler.compile(inp)
        # Should have shocks for 2026 and 2027
        years = {s.year for s in spec.shock_items if isinstance(s, FinalDemandShock)}
        assert years == {2026, 2027}

    def test_multiple_items_same_sector_aggregate(self) -> None:
        li1 = _make_line_item("Steel A", total_value=500_000.0)
        li2 = _make_line_item("Steel B", total_value=300_000.0)
        dec1 = _make_decision(line_item_id=li1.line_item_id, sector_code="C41")
        dec2 = _make_decision(line_item_id=li2.line_item_id, sector_code="C41")
        compiler = ScenarioCompiler()
        inp = _make_compilation_input(
            line_items=[li1, li2], decisions=[dec1, dec2],
            phasing={2026: 1.0},
        )
        spec = compiler.compile(inp)
        shocks_c41 = [s for s in spec.shock_items if isinstance(s, FinalDemandShock) and s.sector_code == "C41"]
        assert len(shocks_c41) == 1
        assert shocks_c41[0].amount_real_base_year == pytest.approx(800_000.0)

    def test_different_sectors_separate_shocks(self) -> None:
        li1 = _make_line_item("Steel", total_value=500_000.0)
        li2 = _make_line_item("Concrete", total_value=300_000.0)
        dec1 = _make_decision(line_item_id=li1.line_item_id, sector_code="C41")
        dec2 = _make_decision(line_item_id=li2.line_item_id, sector_code="F")
        compiler = ScenarioCompiler()
        inp = _make_compilation_input(
            line_items=[li1, li2], decisions=[dec1, dec2],
            phasing={2026: 1.0},
        )
        spec = compiler.compile(inp)
        sector_codes = {s.sector_code for s in spec.shock_items if isinstance(s, FinalDemandShock)}
        assert sector_codes == {"C41", "F"}


# ===================================================================
# Domestic/import splits
# ===================================================================


class TestDomesticImportSplits:
    """Shocks apply domestic/import split from defaults."""

    def test_default_split_applied(self) -> None:
        li = _make_line_item(total_value=1_000_000.0)
        dec = _make_decision(line_item_id=li.line_item_id, sector_code="C41")
        compiler = ScenarioCompiler()
        inp = _make_compilation_input(
            line_items=[li], decisions=[dec],
            default_domestic_share=0.70,
            phasing={2026: 1.0},
        )
        spec = compiler.compile(inp)
        shock = spec.shock_items[0]
        assert isinstance(shock, FinalDemandShock)
        assert shock.domestic_share == pytest.approx(0.70)
        assert shock.import_share == pytest.approx(0.30)


# ===================================================================
# Phasing
# ===================================================================


class TestPhasing:
    """Spend is distributed across years per phasing schedule."""

    def test_phasing_distributes_correctly(self) -> None:
        li = _make_line_item(total_value=1_000_000.0)
        dec = _make_decision(line_item_id=li.line_item_id, sector_code="C41")
        compiler = ScenarioCompiler()
        inp = _make_compilation_input(
            line_items=[li], decisions=[dec],
            phasing={2026: 0.3, 2027: 0.4, 2028: 0.3},
        )
        spec = compiler.compile(inp)
        shocks = [s for s in spec.shock_items if isinstance(s, FinalDemandShock)]
        amounts = {s.year: s.amount_real_base_year for s in shocks}
        assert amounts[2026] == pytest.approx(300_000.0)
        assert amounts[2027] == pytest.approx(400_000.0)
        assert amounts[2028] == pytest.approx(300_000.0)


# ===================================================================
# Residual buckets
# ===================================================================


class TestResidualBuckets:
    """Unmapped/deferred items go to residual bucket."""

    def test_deferred_items_not_in_shocks(self) -> None:
        li1 = _make_line_item("Steel", total_value=500_000.0)
        li2 = _make_line_item("Unknown", total_value=300_000.0)
        dec1 = _make_decision(line_item_id=li1.line_item_id, sector_code="C41")
        dec2 = _make_decision(
            line_item_id=li2.line_item_id,
            sector_code="UNKNOWN",
            decision_type=DecisionType.DEFERRED,
        )
        # Manually fix dec2 to have no final_sector_code
        dec2 = MappingDecision(
            line_item_id=li2.line_item_id,
            suggested_sector_code="UNKNOWN",
            suggested_confidence=0.3,
            final_sector_code=None,
            decision_type=DecisionType.DEFERRED,
            decided_by=uuid7(),
        )
        compiler = ScenarioCompiler()
        inp = _make_compilation_input(
            line_items=[li1, li2], decisions=[dec1, dec2],
            phasing={2026: 1.0},
        )
        spec = compiler.compile(inp)
        # Only C41 should be in shocks
        shocks = [s for s in spec.shock_items if isinstance(s, FinalDemandShock)]
        sector_codes = {s.sector_code for s in shocks}
        assert "UNKNOWN" not in sector_codes

    def test_residual_tracked_in_data_quality(self) -> None:
        li1 = _make_line_item("Steel", total_value=500_000.0)
        li2 = _make_line_item("Unknown", total_value=300_000.0)
        dec1 = _make_decision(line_item_id=li1.line_item_id, sector_code="C41")
        dec2 = MappingDecision(
            line_item_id=li2.line_item_id,
            suggested_sector_code=None,
            suggested_confidence=None,
            final_sector_code=None,
            decision_type=DecisionType.DEFERRED,
            decided_by=uuid7(),
        )
        compiler = ScenarioCompiler()
        inp = _make_compilation_input(
            line_items=[li1, li2], decisions=[dec1, dec2],
            phasing={2026: 1.0},
        )
        spec = compiler.compile(inp)
        assert spec.data_quality_summary is not None
        assert spec.data_quality_summary.unresolved_items_count == 1


# ===================================================================
# DataQualitySummary
# ===================================================================


class TestDataQualitySummary:
    """Compilation produces a DataQualitySummary."""

    def test_summary_generated(self) -> None:
        compiler = ScenarioCompiler()
        inp = _make_compilation_input()
        spec = compiler.compile(inp)
        assert spec.data_quality_summary is not None

    def test_coverage_computed(self) -> None:
        li = _make_line_item(total_value=1_000_000.0)
        dec = _make_decision(line_item_id=li.line_item_id)
        compiler = ScenarioCompiler()
        inp = _make_compilation_input(line_items=[li], decisions=[dec])
        spec = compiler.compile(inp)
        # All items mapped → 100% coverage
        assert spec.data_quality_summary.boq_coverage_pct == pytest.approx(1.0)

    def test_partial_coverage(self) -> None:
        li1 = _make_line_item("Steel", total_value=700_000.0)
        li2 = _make_line_item("Unknown", total_value=300_000.0)
        dec1 = _make_decision(line_item_id=li1.line_item_id, sector_code="C41")
        dec2 = MappingDecision(
            line_item_id=li2.line_item_id,
            suggested_sector_code=None,
            suggested_confidence=None,
            final_sector_code=None,
            decision_type=DecisionType.DEFERRED,
            decided_by=uuid7(),
        )
        compiler = ScenarioCompiler()
        inp = _make_compilation_input(
            line_items=[li1, li2], decisions=[dec1, dec2],
        )
        spec = compiler.compile(inp)
        assert spec.data_quality_summary.boq_coverage_pct == pytest.approx(0.7)

    def test_confidence_histogram(self) -> None:
        li1 = _make_line_item("A", total_value=100.0)
        li2 = _make_line_item("B", total_value=100.0)
        li3 = _make_line_item("C", total_value=100.0)
        dec1 = _make_decision(line_item_id=li1.line_item_id, confidence=0.90)
        dec2 = _make_decision(line_item_id=li2.line_item_id, confidence=0.70)
        dec3 = _make_decision(line_item_id=li3.line_item_id, confidence=0.40)
        compiler = ScenarioCompiler()
        inp = _make_compilation_input(
            line_items=[li1, li2, li3], decisions=[dec1, dec2, dec3],
        )
        spec = compiler.compile(inp)
        mc = spec.data_quality_summary.mapping_confidence
        assert mc.high_pct == pytest.approx(1 / 3, abs=0.01)
        assert mc.medium_pct == pytest.approx(1 / 3, abs=0.01)
        assert mc.low_pct == pytest.approx(1 / 3, abs=0.01)
