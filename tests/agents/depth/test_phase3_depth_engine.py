"""Phase 3 verification: Al-Muhasabi Depth Engine reality gap closure.

These tests prove:
1. All 5 agents call LLM when available (P3-1)
2. Suite planner max_runs is configurable from context (P3-2)
3. Sensitivity sweeps have parameter ranges, not just strings (P3-3)
4. Muhasaba enforces polarity guard (P3-4)
5. Khawatir reads key_questions from context (P3-5)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.agents.depth.khawatir import KhawatirAgent, _generate_fallback_candidates
from src.agents.depth.muraqaba import MuraqabaAgent
from src.agents.depth.mujahada import MujahadaAgent
from src.agents.depth.muhasaba import MuhasabaAgent, _score_all_candidates
from src.agents.depth.suite_planner import SuitePlannerAgent, _build_suite_from_scored
from src.agents.llm_client import LLMClient, LLMResponse, LLMProvider, TokenUsage
from src.models.common import DataClassification, new_uuid7
from src.models.depth import KhawatirOutput, MuhasabaOutput

pytestmark = pytest.mark.anyio


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_llm_client(available: bool = True) -> LLMClient:
    """Create a mock LLM client that reports availability."""
    client = MagicMock(spec=LLMClient)
    client.is_available_for = MagicMock(return_value=available)
    client.call = AsyncMock()
    client.parse_structured_output = MagicMock()
    client.cumulative_usage = MagicMock(return_value=TokenUsage())
    return client


def _make_scored(label: str, score: float, is_contrarian: bool = False,
                 source_type: str = "insight") -> dict:
    """Create a scored candidate dict for suite planner tests."""
    return {
        "direction_id": str(new_uuid7()),
        "label": label,
        "composite_score": score,
        "novelty_score": score,
        "feasibility_score": score,
        "data_availability_score": score,
        "is_contrarian": is_contrarian,
        "accepted": True,
        "rank": 1,
        "source_type": source_type,
        "sector_codes": ["A", "B"],
        "required_levers": ["FINAL_DEMAND_SHOCK"],
    }


def _base_context() -> dict:
    """Minimal context for agent tests."""
    return {
        "sector_codes": ["A", "B", "C", "D", "E"],
        "engagement_name": "Test Project",
        "key_questions": [
            "What is the job creation impact of the new hospital project?",
            "How does import substitution affect local manufacturing?",
        ],
        "workspace_id": str(uuid4()),
    }


# ------------------------------------------------------------------
# P3-1: LLM mode wired (all 5 agents)
# ------------------------------------------------------------------


class TestLLMWiring:
    """P3-1: All 5 agents must call LLM when available."""

    async def test_khawatir_calls_llm(self):
        """Khawatir._run_with_llm must call llm_client.call()."""
        client = _make_llm_client(available=True)
        # Mock LLM response with valid KhawatirOutput JSON
        fallback = _generate_fallback_candidates(_base_context())
        output = KhawatirOutput(candidates=fallback)
        client.call = AsyncMock(return_value=LLMResponse(
            content=output.model_dump_json(),
            parsed=output,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))

        agent = KhawatirAgent()
        result = await agent.run(
            context=_base_context(),
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        # LLM client MUST have been called
        client.call.assert_called_once()
        assert "candidates" in result

    async def test_muraqaba_calls_llm(self):
        """Muraqaba._run_with_llm must call llm_client.call()."""
        client = _make_llm_client(available=True)
        from src.models.depth import MuraqabaOutput, BiasRegister
        fallback_output = MuraqabaOutput(
            bias_register=BiasRegister(entries=[], overall_bias_risk=0.0),
        )
        client.call = AsyncMock(return_value=LLMResponse(
            content=fallback_output.model_dump_json(),
            parsed=fallback_output,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))

        ctx = _base_context()
        ctx["candidates"] = [
            {"direction_id": str(new_uuid7()), "label": "Test",
             "source_type": "insight", "sector_codes": ["A"],
             "required_levers": []}
        ]
        agent = MuraqabaAgent()
        result = await agent.run(
            context=ctx,
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        client.call.assert_called_once()

    async def test_mujahada_calls_llm(self):
        """Mujahada._run_with_llm must call llm_client.call()."""
        client = _make_llm_client(available=True)
        from src.models.depth import MujahadaOutput
        fallback_output = MujahadaOutput(contrarians=[], qualitative_risks=[])
        client.call = AsyncMock(return_value=LLMResponse(
            content=fallback_output.model_dump_json(),
            parsed=fallback_output,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))

        agent = MujahadaAgent()
        result = await agent.run(
            context=_base_context(),
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        client.call.assert_called_once()

    async def test_muhasaba_calls_llm(self):
        """Muhasaba._run_with_llm must call llm_client.call()."""
        client = _make_llm_client(available=True)
        fallback_output = MuhasabaOutput(scored=[])
        client.call = AsyncMock(return_value=LLMResponse(
            content=fallback_output.model_dump_json(),
            parsed=fallback_output,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))

        ctx = _base_context()
        ctx["candidates"] = []
        ctx["contrarians"] = []
        agent = MuhasabaAgent()
        result = await agent.run(
            context=ctx,
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        client.call.assert_called_once()

    async def test_suite_planner_calls_llm(self):
        """SuitePlanner._run_with_llm must call llm_client.call()."""
        client = _make_llm_client(available=True)
        from src.models.depth import SuitePlanningOutput, ScenarioSuitePlan
        fallback_output = SuitePlanningOutput(
            suite_plan=ScenarioSuitePlan(
                workspace_id=uuid4(),
                runs=[],
                recommended_outputs=["multipliers"],
                rationale="Test",
            ),
        )
        client.call = AsyncMock(return_value=LLMResponse(
            content=fallback_output.model_dump_json(),
            parsed=fallback_output,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))

        ctx = _base_context()
        ctx["scored"] = []
        ctx["qualitative_risks"] = []
        agent = SuitePlannerAgent()
        result = await agent.run(
            context=ctx,
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        client.call.assert_called_once()

    async def test_fallback_when_no_llm(self):
        """All agents still use fallback when LLM unavailable."""
        agent = KhawatirAgent()
        result = await agent.run(
            context=_base_context(),
            llm_client=None,
            classification=DataClassification.INTERNAL,
        )

        assert "candidates" in result
        # 5 templates + 2 question-calibrated from key_questions in context
        assert len(result["candidates"]) >= 5


# ------------------------------------------------------------------
# P3-2: Suite planner configurable max_runs
# ------------------------------------------------------------------


class TestSuitePlannerConfigurableMaxRuns:
    """P3-2: Suite planner max_runs must be configurable from context."""

    def test_default_max_runs_is_20(self):
        """Default without context override is 20 (product requirement)."""
        scored = [_make_scored(f"Dir {i}", 8.0 - i * 0.1) for i in range(25)]
        ctx = {"scored": scored, "qualitative_risks": [], "workspace_id": str(uuid4())}
        suite = _build_suite_from_scored(ctx)
        assert len(suite.runs) == 20

    def test_context_max_runs_override(self):
        """Context can set max_runs to allow more runs."""
        scored = [_make_scored(f"Dir {i}", 8.0 - i * 0.3) for i in range(10)]
        ctx = {"scored": scored, "qualitative_risks": [], "max_runs": 8, "workspace_id": str(uuid4())}
        suite = _build_suite_from_scored(ctx)
        assert len(suite.runs) == 8

    def test_context_max_runs_lower(self):
        """Context can set max_runs below default."""
        scored = [_make_scored(f"Dir {i}", 8.0 - i * 0.3) for i in range(10)]
        ctx = {"scored": scored, "qualitative_risks": [], "max_runs": 3, "workspace_id": str(uuid4())}
        suite = _build_suite_from_scored(ctx)
        assert len(suite.runs) == 3


# ------------------------------------------------------------------
# P3-3: Sensitivity sweep parameters
# ------------------------------------------------------------------


class TestSensitivitySweepParameters:
    """P3-3: Sensitivity sweeps must have parameter ranges."""

    def test_sensitivity_sweep_has_range(self):
        """High-novelty runs get sensitivity_sweep with parameter dict, not just a string."""
        scored = [_make_scored("High Novelty Run", 9.0)]
        ctx = {"scored": scored, "qualitative_risks": [], "workspace_id": str(uuid4())}
        suite = _build_suite_from_scored(ctx)
        assert len(suite.runs) == 1
        run = suite.runs[0]

        # Must have at least one sensitivity entry
        assert len(run.sensitivities) > 0

        # At least one should be a dict with range parameters
        sweep_entries = [s for s in run.sensitivities if isinstance(s, dict)]
        assert len(sweep_entries) > 0, (
            "Sensitivity sweeps should be dicts with parameter ranges, not just strings"
        )
        # Each sweep dict should have type and range
        for entry in sweep_entries:
            assert "type" in entry
            assert "range" in entry or "values" in entry

    def test_contrarian_has_sensitivity_parameters(self):
        """Contrarian runs get import_share/phasing sensitivities with ranges."""
        scored = [_make_scored("Contrarian Run", 7.0, is_contrarian=True)]
        ctx = {"scored": scored, "qualitative_risks": [], "workspace_id": str(uuid4())}
        suite = _build_suite_from_scored(ctx)
        assert len(suite.runs) == 1
        run = suite.runs[0]

        # Must have sensitivity entries
        assert len(run.sensitivities) > 0
        sweep_dicts = [s for s in run.sensitivities if isinstance(s, dict)]
        types = {s["type"] for s in sweep_dicts}
        assert "import_share" in types or "phasing" in types

    def test_sensitivity_multipliers_materialized(self):
        """P3-3: sensitivity_multipliers must be materialized from sweep range metadata."""
        scored = [_make_scored("High Novelty", 9.0)]
        ctx = {"scored": scored, "qualitative_risks": [], "workspace_id": str(uuid4())}
        suite = _build_suite_from_scored(ctx)
        run = suite.runs[0]

        # Must have materialized multipliers, not just metadata
        assert hasattr(run, "sensitivity_multipliers")
        assert isinstance(run.sensitivity_multipliers, list)
        assert len(run.sensitivity_multipliers) >= 3, (
            "Sensitivity sweep with steps=5 should produce at least 3 materialized multipliers"
        )
        # All entries must be floats, not dicts
        for m in run.sensitivity_multipliers:
            assert isinstance(m, (int, float)), f"Expected float, got {type(m)}: {m}"
        # Must include the endpoints
        assert min(run.sensitivity_multipliers) <= 0.81
        assert max(run.sensitivity_multipliers) >= 1.19

    def test_no_sensitivity_multipliers_when_low_novelty(self):
        """Runs without sensitivity sweeps get empty multipliers list."""
        scored = [_make_scored("Low Novelty", 5.0)]
        ctx = {"scored": scored, "qualitative_risks": [], "workspace_id": str(uuid4())}
        suite = _build_suite_from_scored(ctx)
        run = suite.runs[0]

        assert hasattr(run, "sensitivity_multipliers")
        assert run.sensitivity_multipliers == []


# ------------------------------------------------------------------
# P3-4: Polarity guard in Muhasaba
# ------------------------------------------------------------------


class TestPolarityGuard:
    """P3-4: Muhasaba must flag unbalanced suites."""

    def test_all_upside_triggers_polarity_warning(self):
        """When all candidates are upside (non-contrarian), flag polarity imbalance."""
        context = {
            "candidates": [
                {"direction_id": str(new_uuid7()), "label": f"Growth {i}",
                 "source_type": "insight", "sector_codes": ["A"],
                 "required_levers": ["FINAL_DEMAND_SHOCK"]}
                for i in range(5)
            ],
            "contrarians": [],
        }
        scored = _score_all_candidates(context)
        # All should be accepted
        assert all(s.accepted for s in scored)

        # Check for polarity_warning
        has_contrarian = any(s.is_contrarian for s in scored)
        assert not has_contrarian, "Should have no contrarians for this test"

        # The scoring function should now flag this as unbalanced
        # by adding a polarity_warning to the output
        output = MuhasabaOutput(scored=scored)
        assert output.polarity_warning is not None, (
            "Muhasaba must warn when no contrarian directions are present"
        )

    def test_balanced_suite_no_polarity_warning(self):
        """When contrarians are present, no polarity warning."""
        context = {
            "candidates": [
                {"direction_id": str(new_uuid7()), "label": "Growth",
                 "source_type": "insight", "sector_codes": ["A"],
                 "required_levers": ["FINAL_DEMAND_SHOCK"]},
            ],
            "contrarians": [
                {"direction_id": str(new_uuid7()), "label": "Stress",
                 "source_type": "insight", "sector_codes": ["A"],
                 "is_quantifiable": True,
                 "required_levers": ["IMPORT_SUBSTITUTION"]},
            ],
        }
        scored = _score_all_candidates(context)
        has_contrarian = any(s.is_contrarian for s in scored)
        assert has_contrarian

        output = MuhasabaOutput(scored=scored)
        assert output.polarity_warning is None

    def test_negative_question_with_contrarians_gets_warning(self):
        """P3-4: Negative/risk questions with mixed (but mostly upside) candidates
        should still trigger polarity warning when contrarian ratio is too low."""
        context = {
            "candidates": [
                {"direction_id": str(new_uuid7()), "label": f"Upside {i}",
                 "source_type": "insight", "sector_codes": ["A"],
                 "required_levers": ["FINAL_DEMAND_SHOCK"]}
                for i in range(5)
            ],
            "contrarians": [
                {"direction_id": str(new_uuid7()), "label": "Minor stress",
                 "source_type": "insight", "sector_codes": ["A"],
                 "is_quantifiable": True,
                 "required_levers": ["IMPORT_SUBSTITUTION"]},
            ],
        }
        scored = _score_all_candidates(context)
        # 1 contrarian out of 6 — should warn for negative questions
        output = MuhasabaOutput(
            scored=scored,
            key_questions=["What are the risks to employment from this project?"],
        )
        assert output.polarity_warning is not None, (
            "Negative/risk question with only 1/6 contrarian should trigger polarity warning"
        )

    def test_positive_question_with_one_contrarian_no_warning(self):
        """P3-4: Positive questions with at least one contrarian should NOT warn."""
        context = {
            "candidates": [
                {"direction_id": str(new_uuid7()), "label": "Growth",
                 "source_type": "insight", "sector_codes": ["A"],
                 "required_levers": ["FINAL_DEMAND_SHOCK"]},
            ],
            "contrarians": [
                {"direction_id": str(new_uuid7()), "label": "Stress",
                 "source_type": "insight", "sector_codes": ["A"],
                 "is_quantifiable": True,
                 "required_levers": ["IMPORT_SUBSTITUTION"]},
            ],
        }
        scored = _score_all_candidates(context)
        output = MuhasabaOutput(
            scored=scored,
            key_questions=["What is the GDP impact of tourism investment?"],
        )
        assert output.polarity_warning is None


# ------------------------------------------------------------------
# P3-5: Question-calibrated candidates
# ------------------------------------------------------------------


class TestQuestionCalibratedCandidates:
    """P3-5: Khawatir must generate candidates addressing key_questions."""

    def test_candidates_address_key_questions(self):
        """When key_questions are in context, at least one candidate references them."""
        context = {
            "sector_codes": ["F", "Q"],  # Construction, Health
            "key_questions": [
                "What is the job creation impact of the new hospital project?",
            ],
        }
        candidates = _generate_fallback_candidates(context)

        # At least one candidate should reference "hospital" or "health" or
        # use sector Q, or have a description relating to the question
        has_question_relevant = any(
            "Q" in c.sector_codes
            or "hospital" in c.description.lower()
            or "health" in c.description.lower()
            or "job" in c.description.lower()
            for c in candidates
        )
        # The fallback should at minimum incorporate key_questions into
        # at least one candidate's description or test_plan
        assert has_question_relevant or any(
            c.rationale and "key_question" in c.rationale.lower()
            for c in candidates
        ), "At least one candidate should address key_questions from context"


# ------------------------------------------------------------------
# P3-5: Denomination in depth prompts
# ------------------------------------------------------------------


class TestDenominationInPrompts:
    """P3-5: Depth prompts must include model denomination context."""

    def test_khawatir_prompt_includes_denomination(self):
        """Khawatir prompt must tell LLM about denomination (SAR_MILLIONS)."""
        from src.agents.depth.prompts.khawatir import build_prompt
        ctx = {**_base_context(), "denomination": "SAR_MILLIONS"}
        prompt = build_prompt(ctx)
        assert "SAR_MILLIONS" in prompt, (
            "Khawatir prompt must include denomination when context provides it"
        )

    def test_mujahada_prompt_includes_denomination(self):
        """Mujahada prompt must tell LLM about denomination for ProposedShockSpec."""
        from src.agents.depth.prompts.mujahada import build_prompt
        ctx = {
            **_base_context(),
            "denomination": "SAR_MILLIONS",
            "candidates": [
                {"direction_id": str(new_uuid7()), "label": "Test",
                 "source_type": "insight"},
            ],
            "bias_register": {"entries": [], "overall_bias_risk": 0},
        }
        prompt = build_prompt(ctx)
        assert "SAR_MILLIONS" in prompt, (
            "Mujahada prompt must include denomination for shock spec guidance"
        )

    def test_suite_prompt_includes_denomination(self):
        """Suite planner prompt must include denomination for lever values."""
        from src.agents.depth.prompts.suite import build_prompt
        ctx = {
            **_base_context(),
            "denomination": "SAR_MILLIONS",
            "scored": [_make_scored("Test", 8.0)],
            "qualitative_risks": [],
        }
        prompt = build_prompt(ctx)
        assert "SAR_MILLIONS" in prompt, (
            "Suite planner prompt must include denomination for executable lever values"
        )

    def test_khawatir_prompt_includes_key_questions(self):
        """Khawatir prompt must relay key_questions to LLM."""
        from src.agents.depth.prompts.khawatir import build_prompt
        ctx = {
            **_base_context(),
            "key_questions": ["What is the GDP impact of tourism?"],
        }
        prompt = build_prompt(ctx)
        assert "GDP impact of tourism" in prompt, (
            "Khawatir prompt must include key_questions from context"
        )


# ------------------------------------------------------------------
# P3-5: LLM response parsing tests (structured output + fallback)
# ------------------------------------------------------------------


class TestLLMParsedOutputs:
    """P3-5: Tests proving LLM responses are parsed into output objects.

    Each test exercises the actual code path where response.parsed is used
    (structured output) or parse_structured_output is called (raw JSON fallback).
    """

    async def test_khawatir_uses_parsed_response(self):
        """Khawatir returns structured output when response.parsed is set."""
        client = _make_llm_client(available=True)
        fallback = _generate_fallback_candidates(_base_context())
        output = KhawatirOutput(candidates=fallback)

        client.call = AsyncMock(return_value=LLMResponse(
            content=output.model_dump_json(),
            parsed=output,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))

        agent = KhawatirAgent()
        result = await agent.run(
            context=_base_context(),
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        # parse_structured_output must NOT have been called (parsed was set)
        client.parse_structured_output.assert_not_called()
        assert len(result["candidates"]) == len(fallback)

    async def test_khawatir_falls_back_to_parse_structured_output(self):
        """When parsed=None, Khawatir uses parse_structured_output on raw content."""
        client = _make_llm_client(available=True)
        fallback = _generate_fallback_candidates(_base_context())
        output = KhawatirOutput(candidates=fallback)

        client.call = AsyncMock(return_value=LLMResponse(
            content=output.model_dump_json(),
            parsed=None,  # Structured output not available
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))
        client.parse_structured_output = MagicMock(return_value=output)

        agent = KhawatirAgent()
        result = await agent.run(
            context=_base_context(),
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        # parse_structured_output MUST have been called
        client.parse_structured_output.assert_called_once()
        call_kwargs = client.parse_structured_output.call_args
        assert call_kwargs.kwargs["schema"] is KhawatirOutput
        assert len(result["candidates"]) == len(fallback)

    async def test_khawatir_deterministic_fallback_on_parse_error(self):
        """When parse_structured_output raises ValueError, Khawatir uses deterministic fallback."""
        client = _make_llm_client(available=True)

        client.call = AsyncMock(return_value=LLMResponse(
            content="not valid json at all",
            parsed=None,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))
        client.parse_structured_output = MagicMock(
            side_effect=ValueError("Invalid JSON from LLM"),
        )

        agent = KhawatirAgent()
        result = await agent.run(
            context=_base_context(),
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        # Must still return valid candidates from deterministic fallback
        assert "candidates" in result
        assert len(result["candidates"]) >= 5

    async def test_muhasaba_uses_parsed_response(self):
        """Muhasaba returns structured output when response.parsed is set."""
        client = _make_llm_client(available=True)
        output = MuhasabaOutput(scored=[], key_questions=["test"])

        client.call = AsyncMock(return_value=LLMResponse(
            content=output.model_dump_json(),
            parsed=output,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))

        ctx = {**_base_context(), "candidates": [], "contrarians": []}
        agent = MuhasabaAgent()
        result = await agent.run(
            context=ctx,
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        client.parse_structured_output.assert_not_called()
        assert "scored" in result

    async def test_muhasaba_falls_back_to_parse_structured_output(self):
        """When parsed=None, Muhasaba uses parse_structured_output."""
        client = _make_llm_client(available=True)
        output = MuhasabaOutput(scored=[], key_questions=["test"])

        client.call = AsyncMock(return_value=LLMResponse(
            content=output.model_dump_json(),
            parsed=None,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))
        client.parse_structured_output = MagicMock(return_value=output)

        ctx = {**_base_context(), "candidates": [], "contrarians": []}
        agent = MuhasabaAgent()
        result = await agent.run(
            context=ctx,
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        client.parse_structured_output.assert_called_once()
        call_kwargs = client.parse_structured_output.call_args
        assert call_kwargs.kwargs["schema"] is MuhasabaOutput

    async def test_mujahada_falls_back_to_parse_structured_output(self):
        """When parsed=None, Mujahada uses parse_structured_output."""
        client = _make_llm_client(available=True)
        from src.models.depth import MujahadaOutput
        output = MujahadaOutput(contrarians=[], qualitative_risks=[])

        client.call = AsyncMock(return_value=LLMResponse(
            content=output.model_dump_json(),
            parsed=None,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))
        client.parse_structured_output = MagicMock(return_value=output)

        agent = MujahadaAgent()
        result = await agent.run(
            context=_base_context(),
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        client.parse_structured_output.assert_called_once()

    async def test_suite_planner_falls_back_to_parse_structured_output(self):
        """When parsed=None, SuitePlanner uses parse_structured_output."""
        client = _make_llm_client(available=True)
        from src.models.depth import SuitePlanningOutput, ScenarioSuitePlan
        output = SuitePlanningOutput(
            suite_plan=ScenarioSuitePlan(
                workspace_id=uuid4(),
                runs=[],
                recommended_outputs=["multipliers"],
                rationale="Test",
            ),
        )

        client.call = AsyncMock(return_value=LLMResponse(
            content=output.model_dump_json(),
            parsed=None,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=200),
        ))
        client.parse_structured_output = MagicMock(return_value=output)

        ctx = {**_base_context(), "scored": [], "qualitative_risks": []}
        agent = SuitePlannerAgent()
        result = await agent.run(
            context=ctx,
            llm_client=client,
            classification=DataClassification.INTERNAL,
        )

        client.parse_structured_output.assert_called_once()


# ------------------------------------------------------------------
# P3-6: Suite planner lever values must not be placeholder zeros
# ------------------------------------------------------------------


class TestSuitePlannerLeverValues:
    """P3-6: Executable levers must have real non-zero values."""

    def test_final_demand_shock_has_nonzero_value(self):
        """FINAL_DEMAND_SHOCK levers must have non-zero value derived from context."""
        dir_id = str(new_uuid7())
        scored = [{
            "direction_id": dir_id,
            "label": "Construction boost",
            "composite_score": 8.0,
            "novelty_score": 8.0,
            "feasibility_score": 8.0,
            "data_availability_score": 8.0,
            "is_contrarian": False,
            "accepted": True,
            "rank": 1,
        }]
        candidates = [{
            "direction_id": dir_id,
            "label": "Construction boost",
            "source_type": "insight",
            "sector_codes": ["F"],
            "required_levers": ["FINAL_DEMAND_SHOCK"],
        }]
        existing_shocks = [
            {"sector_code": "F", "shock_value": 500.0},
            {"sector_code": "C", "shock_value": 200.0},
        ]
        ctx = {
            "scored": scored,
            "qualitative_risks": [],
            "workspace_id": str(uuid4()),
            "candidates": candidates,
            "existing_shocks": existing_shocks,
        }
        suite = _build_suite_from_scored(ctx)
        assert len(suite.runs) == 1
        run = suite.runs[0]
        assert len(run.executable_levers) == 1
        lever = run.executable_levers[0]
        assert lever["type"] == "FINAL_DEMAND_SHOCK"
        assert lever["value"] != 0, (
            "P3-6: FINAL_DEMAND_SHOCK must not have placeholder value=0"
        )

    def test_lever_value_derived_from_existing_shocks(self):
        """When existing_shocks are in context, lever values scale from them."""
        dir_id = str(new_uuid7())
        scored = [{
            "direction_id": dir_id,
            "label": "Test",
            "composite_score": 8.0,
            "novelty_score": 5.0,
            "feasibility_score": 8.0,
            "data_availability_score": 8.0,
            "is_contrarian": False,
            "accepted": True,
            "rank": 1,
        }]
        candidates = [{
            "direction_id": dir_id,
            "label": "Test",
            "source_type": "insight",
            "sector_codes": ["F"],
            "required_levers": ["FINAL_DEMAND_SHOCK"],
        }]
        existing_shocks = [
            {"sector_code": "F", "shock_value": 1000.0},
        ]
        ctx = {
            "scored": scored,
            "qualitative_risks": [],
            "workspace_id": str(uuid4()),
            "candidates": candidates,
            "existing_shocks": existing_shocks,
        }
        suite = _build_suite_from_scored(ctx)
        lever = suite.runs[0].executable_levers[0]
        # Value must be positive and relate to existing shock scale
        assert lever["value"] > 0

    def test_import_share_adjustment_has_nonzero_value(self):
        """IMPORT_SUBSTITUTION lever must produce non-zero IMPORT_SHARE_ADJUSTMENT."""
        dir_id = str(new_uuid7())
        scored = [{
            "direction_id": dir_id,
            "label": "Import sub",
            "composite_score": 8.0,
            "novelty_score": 5.0,
            "feasibility_score": 8.0,
            "data_availability_score": 8.0,
            "is_contrarian": False,
            "accepted": True,
            "rank": 1,
        }]
        candidates = [{
            "direction_id": dir_id,
            "label": "Import sub",
            "source_type": "insight",
            "sector_codes": ["C"],
            "required_levers": ["IMPORT_SUBSTITUTION"],
        }]
        ctx = {
            "scored": scored,
            "qualitative_risks": [],
            "workspace_id": str(uuid4()),
            "candidates": candidates,
        }
        suite = _build_suite_from_scored(ctx)
        lever = suite.runs[0].executable_levers[0]
        assert lever["type"] == "IMPORT_SHARE_ADJUSTMENT"
        assert lever["value"] != 0, (
            "P3-6: IMPORT_SHARE_ADJUSTMENT must not have placeholder value=0"
        )

    def test_local_content_target_has_nonzero_value(self):
        """LOCAL_CONTENT lever must produce non-zero LOCAL_CONTENT_TARGET."""
        dir_id = str(new_uuid7())
        scored = [{
            "direction_id": dir_id,
            "label": "Local content",
            "composite_score": 8.0,
            "novelty_score": 5.0,
            "feasibility_score": 8.0,
            "data_availability_score": 8.0,
            "is_contrarian": False,
            "accepted": True,
            "rank": 1,
        }]
        candidates = [{
            "direction_id": dir_id,
            "label": "Local content",
            "source_type": "insight",
            "sector_codes": ["C"],
            "required_levers": ["LOCAL_CONTENT"],
        }]
        ctx = {
            "scored": scored,
            "qualitative_risks": [],
            "workspace_id": str(uuid4()),
            "candidates": candidates,
        }
        suite = _build_suite_from_scored(ctx)
        lever = suite.runs[0].executable_levers[0]
        assert lever["type"] == "LOCAL_CONTENT_TARGET"
        assert lever["value"] != 0, (
            "P3-6: LOCAL_CONTENT_TARGET must not have placeholder value=0"
        )

    def test_contrarian_quantified_levers_pass_through(self):
        """Contrarian directions with quantified_levers bypass value generation."""
        dir_id = str(new_uuid7())
        scored = [{
            "direction_id": dir_id,
            "label": "Stress test",
            "composite_score": 7.0,
            "novelty_score": 7.0,
            "feasibility_score": 7.0,
            "data_availability_score": 7.0,
            "is_contrarian": True,
            "accepted": True,
            "rank": 1,
        }]
        contrarians = [{
            "direction_id": dir_id,
            "label": "Stress test",
            "source_type": "insight",
            "sector_codes": ["F"],
            "required_levers": ["FINAL_DEMAND_SHOCK"],
            "is_quantifiable": True,
            "quantified_levers": [
                {"type": "FINAL_DEMAND_SHOCK", "sector": "F", "value": -300.0},
            ],
        }]
        ctx = {
            "scored": scored,
            "qualitative_risks": [],
            "workspace_id": str(uuid4()),
            "candidates": [],
            "contrarians": contrarians,
        }
        suite = _build_suite_from_scored(ctx)
        lever = suite.runs[0].executable_levers[0]
        # Quantified levers must pass through unchanged
        assert lever["value"] == -300.0
