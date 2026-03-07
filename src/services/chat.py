"""Chat service — orchestrates conversation turns (Sprint 25 + Sprint 28).

Manages session lifecycle, message persistence, copilot agent invocation,
and tool execution.  Enforces confirmation gate at the service level.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.economist_copilot import CopilotResponse, EconomistCopilot
from src.models.chat import (
    ChatMessageResponse,
    ChatSessionDetail,
    ChatSessionResponse,
    ListSessionsResponse,
    TokenUsage,
    ToolCall,
    TraceMetadata,
)
from src.models.common import new_uuid7
from src.repositories.chat import ChatMessageRepository, ChatSessionRepository
from src.services.chat_tool_executor import ChatToolExecutor

_logger = logging.getLogger(__name__)


def _session_row_to_response(row) -> ChatSessionResponse:
    """Convert ChatSessionRow to API response."""
    return ChatSessionResponse(
        session_id=str(row.session_id),
        workspace_id=str(row.workspace_id),
        title=row.title,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _message_row_to_response(row) -> ChatMessageResponse:
    """Convert ChatMessageRow to API response."""
    trace = None
    if row.trace_metadata:
        trace = TraceMetadata(**row.trace_metadata)

    token_usage = None
    if row.token_usage:
        token_usage = TokenUsage(**row.token_usage)

    return ChatMessageResponse(
        message_id=str(row.message_id),
        role=row.role,
        content=row.content,
        tool_calls=row.tool_calls,
        trace_metadata=trace,
        prompt_version=row.prompt_version,
        model_provider=row.model_provider,
        model_id=row.model_id,
        token_usage=token_usage,
        created_at=row.created_at.isoformat(),
    )


class ChatService:
    """Orchestrates chat sessions and message turns."""

    def __init__(
        self,
        session_repo: ChatSessionRepository,
        message_repo: ChatMessageRepository,
        copilot: EconomistCopilot | None = None,
        max_tokens: int = 4096,
        model: str = "",
        db_session: AsyncSession | None = None,
    ) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._copilot = copilot
        self._max_tokens = max_tokens
        self._model = model
        self._db_session = db_session

    async def create_session(
        self,
        workspace_id: UUID,
        title: str | None = None,
    ) -> ChatSessionResponse:
        """Create a new chat session."""
        session_id = new_uuid7()
        row = await self._session_repo.create(
            session_id=session_id,
            workspace_id=workspace_id,
            title=title,
        )
        return _session_row_to_response(row)

    async def get_session(
        self,
        workspace_id: UUID,
        session_id: UUID,
    ) -> ChatSessionDetail | None:
        """Get a session with its messages."""
        session_row = await self._session_repo.get(session_id, workspace_id)
        if session_row is None:
            return None

        message_rows = await self._message_repo.list_for_session(session_id)
        return ChatSessionDetail(
            session=_session_row_to_response(session_row),
            messages=[_message_row_to_response(m) for m in message_rows],
        )

    async def list_sessions(
        self,
        workspace_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> ListSessionsResponse:
        """List sessions for a workspace."""
        rows = await self._session_repo.list_for_workspace(
            workspace_id, limit=limit, offset=offset,
        )
        return ListSessionsResponse(
            sessions=[_session_row_to_response(r) for r in rows],
        )

    async def send_message(
        self,
        workspace_id: UUID,
        session_id: UUID,
        content: str,
        confirm_scenario: bool | None = None,
    ) -> ChatMessageResponse:
        """Send a user message and get an assistant response.

        1. Verify session exists and belongs to workspace
        2. Persist user message
        3. If confirm_scenario=True, replay stored pending intent (P2-4)
        4. Otherwise call copilot agent (if available)
        5. Persist assistant response with trace metadata
        6. Return assistant response
        """
        # Verify session exists
        session_row = await self._session_repo.get(session_id, workspace_id)
        if session_row is None:
            raise ValueError(f"Session {session_id} not found in workspace {workspace_id}")

        # Persist user message
        user_msg_id = new_uuid7()
        await self._message_repo.create(
            message_id=user_msg_id,
            session_id=session_id,
            role="user",
            content=content,
        )

        # Auto-title from first message
        if session_row.title is None:
            title = content[:100].strip()
            await self._session_repo.update_title(session_id, workspace_id, title)

        # Touch session updated_at
        await self._session_repo.touch(session_id, workspace_id)

        # If no copilot agent, return a stub response
        if self._copilot is None:
            assistant_msg_id = new_uuid7()
            row = await self._message_repo.create(
                message_id=assistant_msg_id,
                session_id=session_id,
                role="assistant",
                content="Copilot is not configured. Please set up LLM API keys.",
            )
            return _message_row_to_response(row)

        # ------------------------------------------------------------------
        # P2-4: Stored intent replay
        #
        # If confirm_scenario=True AND the last assistant message has a
        # pending_confirmation in trace_metadata, replay that stored tool
        # call directly — do NOT call the LLM again. This prevents:
        # - LLM re-parsing (may produce different scenario)
        # - Lost tool arguments
        # - New scenario_spec_id on each turn
        # ------------------------------------------------------------------
        stored_intent = None
        if confirm_scenario is True and self._db_session is not None:
            stored_intent = await self._find_pending_intent(session_id)

        if stored_intent is not None:
            return await self._replay_stored_intent(
                workspace_id=workspace_id,
                session_id=session_id,
                stored_intent=stored_intent,
            )

        # Load conversation history for context
        message_rows = await self._message_repo.list_for_session(session_id)
        history = [
            {"role": m.role, "content": m.content}
            for m in message_rows
            if m.role in ("user", "assistant")
            and str(m.message_id) != str(user_msg_id)  # exclude current user msg
        ]

        # ------------------------------------------------------------------
        # P2-3: Server-side context injection
        #
        # Extract IDs from prior assistant trace_metadata so the copilot
        # prompt can reference them — no more relying on the LLM to infer
        # scenario_spec_id, run_id, etc. from plain text.
        # ------------------------------------------------------------------
        prior_ids = self._extract_prior_ids(message_rows)

        # Call copilot
        context = {
            "user_confirmed": confirm_scenario is True,
            "workspace_id": str(workspace_id),
            "max_tokens": self._max_tokens,
            "model": self._model,
            **prior_ids,
        }

        copilot_response: CopilotResponse = await self._copilot.process_turn(
            messages=history,
            user_message=content,
            context=context,
        )

        # Build trace metadata dict for persistence
        trace_dict = None
        if copilot_response.trace_metadata:
            trace_dict = copilot_response.trace_metadata.model_dump(exclude_none=True)

        # Build pending_confirmation into trace if present
        if copilot_response.pending_confirmation:
            trace_dict = trace_dict or {}
            trace_dict["pending_confirmation"] = copilot_response.pending_confirmation

        # Execute confirmed tool calls (skip if pending_confirmation)
        if (
            copilot_response.tool_calls
            and self._db_session is not None
            and not copilot_response.pending_confirmation
        ):
            tool_executor = ChatToolExecutor(
                session=self._db_session,
                workspace_id=workspace_id,
            )
            exec_results = await tool_executor.execute_all(copilot_response.tool_calls)
            # Merge results into tool calls
            for tc, er in zip(copilot_response.tool_calls, exec_results):
                tc.result = er.model_dump()
            # Populate trace metadata from execution results
            trace_dict = trace_dict or {}
            self._populate_trace_from_results(trace_dict, exec_results)

        # --- Post-execution narrative (S28) ---
        if (
            copilot_response.tool_calls
            and self._db_session is not None
            and not copilot_response.pending_confirmation
        ):
            copilot_response.content = await self._build_narrative(
                copilot_response.content,
                copilot_response.tool_calls,
            )

        # Build tool_calls list for persistence
        tool_calls_list = None
        if copilot_response.tool_calls:
            tool_calls_list = [tc.model_dump() for tc in copilot_response.tool_calls]

        # Persist assistant message
        assistant_msg_id = new_uuid7()
        row = await self._message_repo.create(
            message_id=assistant_msg_id,
            session_id=session_id,
            role="assistant",
            content=copilot_response.content,
            tool_calls=tool_calls_list,
            trace_metadata=trace_dict,
            prompt_version=copilot_response.prompt_version,
            model_provider=copilot_response.model_provider,
            model_id=copilot_response.model_id,
            token_usage=copilot_response.token_usage.model_dump(),
        )

        return _message_row_to_response(row)

    # ------------------------------------------------------------------
    # P2-4: Stored intent helpers
    # ------------------------------------------------------------------

    async def _find_pending_intent(self, session_id: UUID) -> dict | None:
        """Find the most recent pending_confirmation in session history.

        Scans assistant messages from newest to oldest. Returns the
        pending_confirmation dict if found, or None.
        """
        message_rows = await self._message_repo.list_for_session(session_id)
        # Walk newest→oldest assistant messages
        for row in reversed(message_rows):
            if row.role != "assistant":
                continue
            trace = row.trace_metadata
            if isinstance(trace, dict) and trace.get("pending_confirmation"):
                return trace["pending_confirmation"]
        return None

    @staticmethod
    def _extract_prior_ids(message_rows: list) -> dict:
        """P2-3: Extract persisted IDs from prior assistant trace_metadata.

        Scans assistant messages from newest to oldest and collects the
        most recent scenario_spec_id, run_id, model_version_id, and
        export_id from their trace_metadata. These are injected into the
        copilot context so the LLM doesn't have to infer them from text.

        Returns:
            Dict with prior_scenario_spec_id, prior_run_id, etc.
            Only includes keys whose values are non-None.
        """
        prior: dict = {}
        # Keys we want to extract and their context key names
        _TRACE_TO_CONTEXT = {
            "scenario_spec_id": "prior_scenario_spec_id",
            "scenario_spec_version": "prior_scenario_spec_version",
            "run_id": "prior_run_id",
            "run_ids": "prior_run_ids",
            "model_version_id": "prior_model_version_id",
            "plan_id": "prior_plan_id",
            "suite_id": "prior_suite_id",
            "batch_id": "prior_batch_id",
            "export_id": "prior_export_id",
        }

        for row in reversed(message_rows):
            if row.role != "assistant":
                continue
            trace = row.trace_metadata
            if not isinstance(trace, dict):
                continue
            for trace_key, ctx_key in _TRACE_TO_CONTEXT.items():
                if ctx_key not in prior and trace.get(trace_key):
                    prior[ctx_key] = trace[trace_key]

            # Stop scanning once all keys are found
            if len(prior) >= len(_TRACE_TO_CONTEXT):
                break

        return prior

    async def _replay_stored_intent(
        self,
        workspace_id: UUID,
        session_id: UUID,
        stored_intent: dict,
    ) -> ChatMessageResponse:
        """Execute a stored pending tool call without re-invoking the LLM.

        Args:
            workspace_id: Current workspace UUID.
            session_id: Current session UUID.
            stored_intent: Dict with 'tool' and 'arguments' keys from
                           the prior pending_confirmation trace.

        Returns:
            ChatMessageResponse with the executed tool's results.
        """
        from src.models.chat import ToolExecutionResult as TER

        tool_name = stored_intent["tool"]
        tool_args = stored_intent["arguments"]

        # Build ToolCall from stored intent
        tool_call = ToolCall(tool_name=tool_name, arguments=tool_args)

        # Execute directly
        tool_executor = ChatToolExecutor(
            session=self._db_session,
            workspace_id=workspace_id,
        )
        exec_results = await tool_executor.execute_all([tool_call])

        # Merge result into tool call
        for tc, er in zip([tool_call], exec_results):
            tc.result = er.model_dump()

        # Build trace
        trace_dict: dict = {"replayed_from_pending": True}
        self._populate_trace_from_results(trace_dict, exec_results)

        # Build content from narrative
        content = f"Confirmed and executed: {tool_name}"
        content = await self._build_narrative(content, [tool_call])

        # Build tool_calls list for persistence
        tool_calls_list = [tool_call.model_dump()]

        # Persist assistant message
        assistant_msg_id = new_uuid7()
        row = await self._message_repo.create(
            message_id=assistant_msg_id,
            session_id=session_id,
            role="assistant",
            content=content,
            tool_calls=tool_calls_list,
            trace_metadata=trace_dict,
            prompt_version="copilot_v1",
            model_provider="replay",
            model_id="stored_intent",
            token_usage=TokenUsage().model_dump(),
        )

        return _message_row_to_response(row)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _populate_trace_from_results(
        trace_dict: dict,
        exec_results: list,
    ) -> None:
        """Populate trace_dict with IDs from execution results."""
        for er in exec_results:
            if er.status == "success" and er.result:
                if er.tool_name == "run_engine":
                    trace_dict["run_id"] = er.result.get("run_id")
                    trace_dict["model_version_id"] = er.result.get("model_version_id")
                    trace_dict["scenario_spec_id"] = er.result.get("scenario_spec_id")
                    trace_dict["scenario_spec_version"] = er.result.get("scenario_spec_version")
                elif er.tool_name == "build_scenario":
                    trace_dict["scenario_spec_id"] = er.result.get("scenario_spec_id")
                    trace_dict["scenario_spec_version"] = er.result.get("version")
                elif er.tool_name == "run_depth_suite":
                    trace_dict["plan_id"] = er.result.get("plan_id")
                    trace_dict["suite_id"] = er.result.get("suite_id")
                    trace_dict["batch_id"] = er.result.get("batch_id")
                    trace_dict["run_ids"] = er.result.get("run_ids", [])
                    if er.result.get("run_ids"):
                        trace_dict["run_id"] = er.result["run_ids"][0]
                elif er.tool_name == "create_export":
                    trace_dict["export_id"] = er.result.get("export_id")
            # Governance-blocked exports still carry an export_id for trace
            elif (
                er.status == "blocked"
                and er.tool_name == "create_export"
                and er.result
            ):
                trace_dict["export_id"] = er.result.get("export_id")

    async def _build_narrative(
        self,
        original_content: str,
        tool_calls: list,
    ) -> str:
        """Build post-execution narrative from tool results (S28).

        Returns the narrative content, falling back to original_content
        if no meaningful results were produced.
        """
        from src.services.chat_narrative import ChatNarrativeService
        from src.models.chat import ToolExecutionResult as TER

        narrative_svc = ChatNarrativeService()
        # Build ToolExecutionResult objects from tool call results
        ter_list: list[TER] = []
        for tc in tool_calls:
            if tc.result is not None:
                if isinstance(tc.result, TER):
                    ter_list.append(tc.result)
                elif isinstance(tc.result, dict):
                    ter_list.append(TER(**tc.result))

        if not ter_list:
            return original_content

        facts = narrative_svc.extract_facts(ter_list)

        if facts.has_meaningful_results:
            # Replace pre-execution LLM content with post-execution narrative
            baseline = narrative_svc.build_baseline_narrative(facts)
            if baseline:
                # Optional LLM enrichment (S28-3c): if copilot is available,
                # enrich the deterministic baseline into economist prose.
                # Falls back to baseline on LLM failure or if copilot is None.
                if self._copilot is not None:
                    try:
                        enriched = await self._copilot.enrich_narrative(
                            baseline=baseline,
                            context={
                                "scenario_name": facts.scenario_name or "N/A",
                            },
                        )
                        return enriched
                    except Exception:
                        _logger.warning(
                            "Narrative enrichment failed, using baseline",
                            exc_info=True,
                        )
                        return baseline
                else:
                    return baseline
        elif facts.errors:
            # All failed: preserve original + append failure summary
            failure_summary = narrative_svc.build_baseline_narrative(facts)
            if failure_summary:
                return original_content + "\n\n" + failure_summary

        return original_content
