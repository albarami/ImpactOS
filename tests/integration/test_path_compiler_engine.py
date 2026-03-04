# tests/integration/test_path_compiler_engine.py
"""Integration Path 2: Compiler -> Engine + Compiler Gate Metric.

Tests:
1. ScenarioCompiler output feeds Leontief correctly (hand-authored decisions)
2. MappingSuggestionAgent.suggest_batch coverage/accuracy gate (real pipeline)

Uses SECTOR_CODES_SMALL (F/C/G) for basic compiler->engine path tests.
Uses SEED_LIBRARY and LABELED_BOQ from shared.py for the suggestion gate test.
"""

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.agents.mapping_agent import MappingSuggestionAgent
from src.compiler.scenario_compiler import CompilationInput, ScenarioCompiler
from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.models.mapping import DecisionType, MappingDecision
from src.models.scenario import TimeHorizon
from tests.integration.golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    LABELED_BOQ,
    SECTOR_CODES_SMALL,
    SEED_LIBRARY,
    make_labeled_boq_items,
    make_line_item,
)


@pytest.fixture
def loaded_model():
    store = ModelStore()
    mv = store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR, source="test-compiler-engine",
    )
    return store.get(mv.model_version_id)


@pytest.mark.integration
class TestCompilerToEngine:
    """Compiler output -> valid Leontief inputs (hand-authored decisions)."""

    def test_scenario_spec_has_shock_items(self):
        """Compiled scenario has shock items matching BoQ mapping."""
        items = [make_line_item("concrete works", 100_000_000)]
        decisions = [
            MappingDecision(
                line_item_id=items[0].line_item_id,
                suggested_sector_code="F",
                suggested_confidence=0.9,
                final_sector_code="F",
                decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
        ]
        compiler = ScenarioCompiler()
        spec = compiler.compile(CompilationInput(
            workspace_id=uuid7(),
            scenario_name="Test",
            base_model_version_id=uuid7(),
            base_year=GOLDEN_BASE_YEAR,
            time_horizon=TimeHorizon(start_year=2024, end_year=2026),
            line_items=items,
            decisions=decisions,
            phasing={2024: 0.5, 2025: 0.3, 2026: 0.2},
        ))
        assert len(spec.shock_items) > 0

    def test_domestic_share_reduces_shock(self):
        """With 65% domestic share, delta_d < total spend."""
        items = [make_line_item("steel supply", 100_000_000)]
        decisions = [
            MappingDecision(
                line_item_id=items[0].line_item_id,
                suggested_sector_code="C",
                suggested_confidence=0.9,
                final_sector_code="C",
                decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
        ]
        compiler = ScenarioCompiler()
        spec = compiler.compile(CompilationInput(
            workspace_id=uuid7(),
            scenario_name="Test",
            base_model_version_id=uuid7(),
            base_year=GOLDEN_BASE_YEAR,
            time_horizon=TimeHorizon(start_year=2024, end_year=2024),
            line_items=items,
            decisions=decisions,
            default_domestic_share=0.65,
            default_import_share=0.35,
            phasing={2024: 1.0},
        ))
        # Total domestic amount should be 65% of 100M = 65M
        total_domestic = sum(
            s.amount_real_base_year * s.domestic_share
            for s in spec.shock_items
        )
        assert total_domestic < 100_000_000

    def test_compiled_spec_feeds_leontief(self, loaded_model):
        """Full path: compile -> extract delta_d -> solve -> valid result."""
        items = [
            make_line_item("concrete", 50_000_000),
            make_line_item("steel", 30_000_000),
        ]
        decisions = [
            MappingDecision(
                line_item_id=items[0].line_item_id,
                suggested_sector_code="F", suggested_confidence=0.9,
                final_sector_code="F", decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
            MappingDecision(
                line_item_id=items[1].line_item_id,
                suggested_sector_code="C", suggested_confidence=0.85,
                final_sector_code="C", decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
        ]
        compiler = ScenarioCompiler()
        spec = compiler.compile(CompilationInput(
            workspace_id=uuid7(),
            scenario_name="Test",
            base_model_version_id=loaded_model.model_version.model_version_id,
            base_year=GOLDEN_BASE_YEAR,
            time_horizon=TimeHorizon(start_year=2024, end_year=2024),
            line_items=items,
            decisions=decisions,
            phasing={2024: 1.0},
        ))

        # Extract delta_d from shock items
        delta_d = np.zeros(len(SECTOR_CODES_SMALL))
        sector_idx = {code: i for i, code in enumerate(SECTOR_CODES_SMALL)}
        for shock in spec.shock_items:
            if shock.sector_code in sector_idx:
                delta_d[sector_idx[shock.sector_code]] += (
                    shock.amount_real_base_year * shock.domestic_share
                )

        solver = LeontiefSolver()
        result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        assert result.delta_x_total.shape == (3,)
        assert np.all(result.delta_x_total >= 0)


@pytest.mark.integration
@pytest.mark.gate
class TestCompilerAutoMapping:
    """Compiler gate metric: MappingSuggestionAgent coverage and accuracy.

    Uses SEED_LIBRARY and LABELED_BOQ from shared.py. The agent performs
    real pattern matching against the seeded library -- no mocks.

    Gate criteria (Amendment 4):
    - Coverage >= 60%: fraction of items where agent proposes a mapping
    - Accuracy >= 80%: fraction of proposed mappings matching ground truth ISIC section
    """

    def test_compiler_auto_mapping_gate(self):
        """Auto-mapping coverage >= 60% and accuracy >= 80% on labeled BoQ."""
        # Build taxonomy (minimal -- agent uses library matching primarily)
        taxonomy = [
            {"sector_code": code, "description": desc}
            for code, desc in [
                ("A", "Agriculture"), ("B", "Mining"), ("C", "Manufacturing"),
                ("D", "Electricity"), ("E", "Water"), ("F", "Construction"),
                ("G", "Wholesale"), ("H", "Transport"), ("I", "Accommodation"),
                ("J", "ICT"), ("K", "Financial"), ("L", "Real estate"),
                ("M", "Professional"), ("N", "Administrative"), ("O", "Public admin"),
                ("P", "Education"), ("Q", "Health"), ("R", "Arts"),
                ("S", "Other services"), ("T", "Households"),
            ]
        ]

        agent = MappingSuggestionAgent(library=SEED_LIBRARY)
        boq_items = make_labeled_boq_items(LABELED_BOQ)
        batch_result = agent.suggest_batch(boq_items, taxonomy=taxonomy)

        suggestions = batch_result.suggestions
        assert len(suggestions) == len(LABELED_BOQ)

        # Compute coverage: items where confidence > 0.1 (not a fallback)
        covered = [s for s in suggestions if s.confidence > 0.1]
        coverage = len(covered) / len(LABELED_BOQ)

        # Compute accuracy: of covered items, how many match ground truth?
        # We need to align suggestions with labeled BoQ by line_item_id
        item_id_to_truth = {
            item.line_item_id: label["ground_truth_isic"]
            for item, label in zip(boq_items, LABELED_BOQ, strict=False)
        }
        correct = [
            s for s in covered
            if s.sector_code == item_id_to_truth.get(s.line_item_id)
        ]
        accuracy = len(correct) / len(covered) if covered else 0.0

        assert coverage >= 0.60, f"Coverage {coverage:.0%} < 60% ({len(covered)}/{len(LABELED_BOQ)})"
        assert accuracy >= 0.80, f"Accuracy {accuracy:.0%} < 80% ({len(correct)}/{len(covered)})"
