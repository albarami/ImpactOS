"""ChatNarrativeService — post-execution narrative (Sprint 28).

Extracts normalized facts from tool execution results and builds
deterministic template-based baseline narratives.  LLM enrichment
is handled separately by EconomistCopilot.enrich_narrative().

Agent-to-Math Boundary: this module never computes economic results.
It only formats facts that were already computed and persisted by the
deterministic engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models.chat import ToolExecutionResult


# ------------------------------------------------------------------
# NarrativeFacts — normalized domain facts
# ------------------------------------------------------------------


@dataclass(frozen=True)
class NarrativeFacts:
    """Normalized domain facts extracted from tool execution results."""

    run_completed: bool = False
    run_id: str | None = None
    scenario_name: str | None = None
    model_version_id: str | None = None
    result_summary: dict | None = None  # metric_type -> values
    export_completed: bool = False
    export_id: str | None = None
    export_status: str | None = None  # COMPLETED, BLOCKED, FAILED
    export_blocking_reasons: list[str] = field(default_factory=list)
    export_checksums: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    has_meaningful_results: bool = False  # at least one tool produced results


# ------------------------------------------------------------------
# ChatNarrativeService
# ------------------------------------------------------------------


class ChatNarrativeService:
    """Extract facts and build baseline narrative from tool results."""

    # ----------------------------------------------------------
    # extract_facts
    # ----------------------------------------------------------

    def extract_facts(
        self, tool_results: list[ToolExecutionResult]
    ) -> NarrativeFacts:
        """Normalize tool execution results into domain facts.

        Iterates *tool_results* and extracts structured domain facts:
        - ``run_engine`` success  -> run_completed, run_id, model_version_id, result_summary
        - ``create_export`` success or blocked -> export_id, export_status, checksums, blocking_reasons
        - ``narrate_results`` success -> has_meaningful_results
        - Any tool with status ``error`` -> error_summary collected
        - Non-export tools with status ``blocked`` (safety cap) are ignored — not errors.
        """
        run_completed = False
        run_id: str | None = None
        model_version_id: str | None = None
        result_summary: dict | None = None
        export_completed = False
        export_id: str | None = None
        export_status: str | None = None
        export_blocking_reasons: list[str] = []
        export_checksums: dict[str, str] = {}
        errors: list[str] = []
        has_meaningful = False

        for tr in tool_results:
            if tr.tool_name == "run_engine":
                if tr.status == "success" and tr.result:
                    run_completed = True
                    has_meaningful = True
                    run_id = tr.result.get("run_id")
                    model_version_id = tr.result.get("model_version_id")
                    result_summary = tr.result.get("result_summary")
                elif tr.status == "error":
                    if tr.error_summary:
                        errors.append(tr.error_summary)
                # status == "blocked" -> intentionally ignored

            elif tr.tool_name == "create_export":
                if tr.status in ("success", "blocked") and tr.result:
                    has_meaningful = True
                    export_id = tr.result.get("export_id")
                    export_status = tr.result.get("status")
                    export_completed = export_status == "COMPLETED"
                    export_blocking_reasons = tr.result.get(
                        "blocking_reasons", []
                    )
                    export_checksums = tr.result.get("checksums", {})
                elif tr.status == "error":
                    if tr.error_summary:
                        errors.append(tr.error_summary)

            elif tr.tool_name == "narrate_results":
                if tr.status == "success" and tr.result:
                    has_meaningful = True
                elif tr.status == "error" and tr.error_summary:
                    errors.append(tr.error_summary)

            elif tr.status == "error" and tr.error_summary:
                # Any other tool that errored
                errors.append(tr.error_summary)

        return NarrativeFacts(
            run_completed=run_completed,
            run_id=run_id,
            model_version_id=model_version_id,
            result_summary=result_summary,
            export_completed=export_completed,
            export_id=export_id,
            export_status=export_status,
            export_blocking_reasons=export_blocking_reasons,
            export_checksums=export_checksums,
            errors=errors,
            has_meaningful_results=has_meaningful,
        )

    # ----------------------------------------------------------
    # build_baseline_narrative
    # ----------------------------------------------------------

    def build_baseline_narrative(self, facts: NarrativeFacts) -> str:
        """Build a deterministic template narrative from facts.

        No LLM call.  Grounded only in persisted deterministic outputs.

        Templates
        ---------
        - Run completed:   ``Engine run completed (run_id: {run_id}).``
                           ``  {metric}: {total:,.2f}``  for each metric with a "total" key
        - Export COMPLETED: ``Export {export_id} generated successfully.``
                            ``  {fmt}: {checksum}``  for each checksum
        - Export BLOCKED:   ``Export {export_id} blocked:``
                            ``  - {reason}``  for each blocking reason
        - Export FAILED:    ``Export failed.``
        - All failed:       ``Execution encountered errors:``
                            ``  - {error}``  for each error
        - No facts:         empty string
        """
        parts: list[str] = []

        # --- Run section ---
        if facts.run_completed and facts.run_id:
            parts.append(f"Engine run completed (run_id: {facts.run_id}).")
            if facts.result_summary:
                for metric, values in facts.result_summary.items():
                    if isinstance(values, dict) and "total" in values:
                        parts.append(f"  {metric}: {values['total']:,.2f}")

        # --- Export section ---
        if facts.export_status:
            if facts.export_completed:
                parts.append(
                    f"Export {facts.export_id} generated successfully."
                )
                if facts.export_checksums:
                    for fmt, cs in facts.export_checksums.items():
                        parts.append(f"  {fmt}: {cs}")
            elif facts.export_status == "BLOCKED":
                parts.append(f"Export {facts.export_id} blocked:")
                for reason in facts.export_blocking_reasons:
                    parts.append(f"  - {reason}")
            elif facts.export_status == "FAILED":
                parts.append("Export failed.")

        # --- All-failed section ---
        if not facts.has_meaningful_results and facts.errors:
            parts.append("Execution encountered errors:")
            for err in facts.errors:
                parts.append(f"  - {err}")

        if not parts:
            return ""

        return "\n".join(parts)
