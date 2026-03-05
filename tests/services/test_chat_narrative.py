"""Tests for ChatNarrativeService (Sprint 28 — S28-3a).

Covers:
- NarrativeFacts extraction from ToolExecutionResult lists
- Deterministic baseline narrative generation (no LLM)
"""

import pytest

from src.models.chat import ToolExecutionResult


pytestmark = pytest.mark.anyio


# ------------------------------------------------------------------
# TestNarrativeFacts — extract_facts
# ------------------------------------------------------------------


class TestNarrativeFacts:
    def test_extract_facts_successful_run(self):
        """run_engine success -> run_completed=True, has_meaningful_results=True."""
        from src.services.chat_narrative import ChatNarrativeService

        svc = ChatNarrativeService()
        results = [
            ToolExecutionResult(
                tool_name="run_engine",
                status="success",
                result={
                    "run_id": "abc-123",
                    "model_version_id": "mv-1",
                    "scenario_spec_id": "sc-1",
                    "scenario_spec_version": 1,
                    "result_summary": {"total_output": {"total": 1500.0}},
                },
            ),
        ]
        facts = svc.extract_facts(results)
        assert facts.run_completed is True
        assert facts.run_id == "abc-123"
        assert facts.model_version_id == "mv-1"
        assert facts.result_summary == {"total_output": {"total": 1500.0}}
        assert facts.has_meaningful_results is True
        assert facts.errors == []

    def test_extract_facts_run_failed(self):
        """run_engine error -> run_completed=False, error collected."""
        from src.services.chat_narrative import ChatNarrativeService

        svc = ChatNarrativeService()
        results = [
            ToolExecutionResult(
                tool_name="run_engine",
                status="error",
                reason_code="run_failed",
                error_summary="Model not found",
            ),
        ]
        facts = svc.extract_facts(results)
        assert facts.run_completed is False
        assert facts.run_id is None
        assert facts.has_meaningful_results is False
        assert "Model not found" in facts.errors

    def test_extract_facts_export_completed(self):
        """create_export COMPLETED -> export_completed=True, checksums present."""
        from src.services.chat_narrative import ChatNarrativeService

        svc = ChatNarrativeService()
        results = [
            ToolExecutionResult(
                tool_name="create_export",
                status="success",
                result={
                    "export_id": "e-42",
                    "status": "COMPLETED",
                    "checksums": {"xlsx": "sha256-aaa", "pdf": "sha256-bbb"},
                },
            ),
        ]
        facts = svc.extract_facts(results)
        assert facts.export_completed is True
        assert facts.export_id == "e-42"
        assert facts.export_status == "COMPLETED"
        assert facts.export_checksums == {"xlsx": "sha256-aaa", "pdf": "sha256-bbb"}
        assert facts.export_blocking_reasons == []
        assert facts.has_meaningful_results is True

    def test_extract_facts_export_blocked(self):
        """create_export BLOCKED -> export_status=BLOCKED, blocking_reasons, still meaningful."""
        from src.services.chat_narrative import ChatNarrativeService

        svc = ChatNarrativeService()
        results = [
            ToolExecutionResult(
                tool_name="run_engine",
                status="success",
                result={
                    "run_id": "r1",
                    "result_summary": {"total_output": {"total": 100.0}},
                },
            ),
            ToolExecutionResult(
                tool_name="create_export",
                status="success",
                result={
                    "export_id": "e1",
                    "status": "BLOCKED",
                    "blocking_reasons": ["No quality assessment"],
                },
            ),
        ]
        facts = svc.extract_facts(results)
        assert facts.export_status == "BLOCKED"
        assert facts.export_completed is False
        assert facts.export_blocking_reasons == ["No quality assessment"]
        assert facts.has_meaningful_results is True

    def test_extract_facts_all_failed(self):
        """All tools error -> has_meaningful_results=False, errors collected."""
        from src.services.chat_narrative import ChatNarrativeService

        svc = ChatNarrativeService()
        results = [
            ToolExecutionResult(
                tool_name="run_engine",
                status="error",
                reason_code="run_failed",
                error_summary="Model not found",
            ),
            ToolExecutionResult(
                tool_name="create_export",
                status="error",
                reason_code="export_failed",
                error_summary="Run prerequisite missing",
            ),
        ]
        facts = svc.extract_facts(results)
        assert facts.run_completed is False
        assert facts.export_completed is False
        assert facts.has_meaningful_results is False
        assert len(facts.errors) == 2
        assert "Model not found" in facts.errors
        assert "Run prerequisite missing" in facts.errors

    def test_extract_facts_narrate_results_success(self):
        """narrate_results success -> has_meaningful_results=True."""
        from src.services.chat_narrative import ChatNarrativeService

        svc = ChatNarrativeService()
        results = [
            ToolExecutionResult(
                tool_name="narrate_results",
                status="success",
                result={"narrative": "Output grew by 5%"},
            ),
        ]
        facts = svc.extract_facts(results)
        assert facts.has_meaningful_results is True
        # narrate_results does not set run/export fields
        assert facts.run_completed is False
        assert facts.export_completed is False

    def test_extract_facts_mixed_success_and_error(self):
        """run_engine success + create_export error -> meaningful=True, errors collected."""
        from src.services.chat_narrative import ChatNarrativeService

        svc = ChatNarrativeService()
        results = [
            ToolExecutionResult(
                tool_name="run_engine",
                status="success",
                result={
                    "run_id": "r-ok",
                    "model_version_id": "mv-2",
                    "result_summary": {"employment": {"total": 250.0}},
                },
            ),
            ToolExecutionResult(
                tool_name="create_export",
                status="error",
                reason_code="export_failed",
                error_summary="Artifact storage unreachable",
            ),
        ]
        facts = svc.extract_facts(results)
        assert facts.run_completed is True
        assert facts.has_meaningful_results is True
        assert facts.run_id == "r-ok"
        assert facts.export_completed is False
        assert "Artifact storage unreachable" in facts.errors

    def test_extract_facts_empty_list(self):
        """No results -> all defaults."""
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts

        svc = ChatNarrativeService()
        facts = svc.extract_facts([])
        assert facts == NarrativeFacts()
        assert facts.run_completed is False
        assert facts.has_meaningful_results is False
        assert facts.errors == []

    def test_extract_facts_blocked_tool_ignored(self):
        """Tools with status='blocked' (safety cap) -> not counted as error."""
        from src.services.chat_narrative import ChatNarrativeService

        svc = ChatNarrativeService()
        results = [
            ToolExecutionResult(
                tool_name="run_engine",
                status="blocked",
                reason_code="safety_cap",
                error_summary="blocked by safety cap",
            ),
        ]
        facts = svc.extract_facts(results)
        assert facts.run_completed is False
        assert facts.has_meaningful_results is False
        # blocked tools should NOT add to errors list
        assert facts.errors == []


# ------------------------------------------------------------------
# TestBaselineNarrative — build_baseline_narrative
# ------------------------------------------------------------------


class TestBaselineNarrative:
    def test_run_success_narrative(self):
        """Completed run generates narrative with run_id and metrics."""
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts

        svc = ChatNarrativeService()
        facts = NarrativeFacts(
            run_completed=True,
            run_id="r1",
            result_summary={"total_output": {"total": 1500.0}},
            has_meaningful_results=True,
        )
        narrative = svc.build_baseline_narrative(facts)
        assert "r1" in narrative
        assert "Engine run completed" in narrative
        assert "total_output: 1,500.00" in narrative

    def test_export_completed_narrative(self):
        """COMPLETED export generates narrative with checksums."""
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts

        svc = ChatNarrativeService()
        facts = NarrativeFacts(
            export_completed=True,
            export_id="e-99",
            export_status="COMPLETED",
            export_checksums={"xlsx": "sha256-abc", "pdf": "sha256-def"},
            has_meaningful_results=True,
        )
        narrative = svc.build_baseline_narrative(facts)
        assert "Export e-99 generated successfully." in narrative
        assert "xlsx: sha256-abc" in narrative
        assert "pdf: sha256-def" in narrative

    def test_export_blocked_narrative(self):
        """BLOCKED export generates narrative with blocking reasons."""
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts

        svc = ChatNarrativeService()
        facts = NarrativeFacts(
            run_completed=True,
            run_id="r1",
            result_summary={"total_output": {"total": 100.0}},
            export_completed=False,
            export_id="e1",
            export_status="BLOCKED",
            export_blocking_reasons=["No quality assessment"],
            has_meaningful_results=True,
        )
        narrative = svc.build_baseline_narrative(facts)
        assert "blocked" in narrative.lower()
        assert "No quality assessment" in narrative

    def test_all_failed_narrative(self):
        """All-failed generates error narrative."""
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts

        svc = ChatNarrativeService()
        facts = NarrativeFacts(
            run_completed=False,
            errors=["Model not found"],
            has_meaningful_results=False,
        )
        narrative = svc.build_baseline_narrative(facts)
        assert "Execution encountered errors:" in narrative
        assert "Model not found" in narrative

    def test_empty_facts_returns_empty_string(self):
        """Empty NarrativeFacts -> empty string."""
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts

        svc = ChatNarrativeService()
        facts = NarrativeFacts()
        narrative = svc.build_baseline_narrative(facts)
        assert narrative == ""

    def test_run_and_export_combined(self):
        """Both run + export facts produce combined narrative."""
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts

        svc = ChatNarrativeService()
        facts = NarrativeFacts(
            run_completed=True,
            run_id="r-combo",
            result_summary={
                "total_output": {"total": 2000.0},
                "employment": {"total": 300.0},
            },
            export_completed=True,
            export_id="e-combo",
            export_status="COMPLETED",
            export_checksums={"xlsx": "sha256-xyz"},
            has_meaningful_results=True,
        )
        narrative = svc.build_baseline_narrative(facts)
        # Run section
        assert "Engine run completed (run_id: r-combo)." in narrative
        assert "total_output: 2,000.00" in narrative
        assert "employment: 300.00" in narrative
        # Export section
        assert "Export e-combo generated successfully." in narrative
        assert "xlsx: sha256-xyz" in narrative

    def test_export_failed_narrative(self):
        """FAILED export generates 'Export failed.' line."""
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts

        svc = ChatNarrativeService()
        facts = NarrativeFacts(
            export_status="FAILED",
            has_meaningful_results=False,
            errors=["Storage unavailable"],
        )
        narrative = svc.build_baseline_narrative(facts)
        assert "Export failed." in narrative
