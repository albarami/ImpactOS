"""Pydantic models for Economist Copilot chat (Sprint 25)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TraceMetadata(BaseModel):
    """Provenance trace attached to assistant results messages."""

    run_id: str | None = None
    scenario_spec_id: str | None = None
    scenario_spec_version: int | None = None
    model_version_id: str | None = None
    plan_id: str | None = None
    suite_id: str | None = None
    batch_id: str | None = None
    run_ids: list[str] = Field(default_factory=list)
    export_id: str | None = None
    io_table: str | None = None
    multiplier_type: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    confidence: str | None = None
    confidence_reasons: list[str] = Field(default_factory=list)
    pending_confirmation: dict | None = None


class ToolCall(BaseModel):
    """Tool invocation record."""

    tool_name: str
    arguments: dict
    result: dict | None = None


class ToolExecutionResult(BaseModel):
    """Result of executing a tool call."""

    tool_name: str
    status: Literal["success", "error", "blocked"]
    reason_code: str = ""
    retryable: bool = False
    latency_ms: int = 0
    result: dict | None = None
    error_summary: str | None = None


class TokenUsage(BaseModel):
    """LLM token usage for a single turn."""

    input_tokens: int = 0
    output_tokens: int = 0


class ChatMessageResponse(BaseModel):
    """Single message in API response."""

    message_id: str
    role: str
    content: str
    tool_calls: list[ToolCall] | None = None
    trace_metadata: TraceMetadata | None = None
    prompt_version: str | None = None
    model_provider: str | None = None
    model_id: str | None = None
    token_usage: TokenUsage | None = None
    created_at: str


class ChatSessionResponse(BaseModel):
    """Session metadata in API response."""

    session_id: str
    workspace_id: str
    title: str | None = None
    created_at: str
    updated_at: str


class CreateSessionRequest(BaseModel):
    """Request to create a new chat session."""

    title: str | None = None


class SendMessageRequest(BaseModel):
    """Request to send a user message."""

    content: str
    confirm_scenario: bool | None = None


class ChatSessionDetail(BaseModel):
    """Session with messages."""

    session: ChatSessionResponse
    messages: list[ChatMessageResponse]


class ListSessionsResponse(BaseModel):
    """Paginated session list."""

    sessions: list[ChatSessionResponse]
