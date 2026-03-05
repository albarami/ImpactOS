# Sprint 25: Economist Copilot v1 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add a conversational economist copilot that orchestrates the ImpactOS Leontief engine via chat, with DB persistence, versioned prompts, mandatory confirmation gate, and full trace metadata.

**Architecture:** Chat sessions/messages persisted in PostgreSQL from day 1. EconomistCopilot agent uses existing LLMClient with structured tool-calling (lookup_data, build_scenario, run_engine, narrate_results). Confirmation gate enforced before every engine run. All numeric outputs sourced from deterministic engine ResultSets — LLM never invents numbers.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, Pydantic v2, existing LLMClient (Anthropic/OpenAI/OpenRouter), Next.js 15, React 18, TanStack Query, Vitest, Tailwind CSS.

**Design doc:** `docs/plans/2026-03-05-economist-copilot-v1-design.md`

---

## Task 1: Migration 020 — chat_sessions + chat_messages

**Files:**
- Create: `alembic/versions/020_chat_sessions_messages.py`

**What to build:**
Two new tables following the migration 018 pattern:

```python
"""020: Chat sessions and messages tables (Sprint 25).

Revision ID: 020_chat_sessions_messages
Revises: 019_run_snapshot_scenario_link
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "020_chat_sessions_messages"
down_revision = "019_run_snapshot_scenario_link"
branch_labels = None
depends_on = None

FlexUUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
FlexJSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("session_id", FlexUUID, primary_key=True),
        sa.Column("workspace_id", FlexUUID, sa.ForeignKey("workspaces.workspace_id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_sessions_workspace", "chat_sessions", ["workspace_id", "updated_at"])

    op.create_table(
        "chat_messages",
        sa.Column("message_id", FlexUUID, primary_key=True),
        sa.Column("session_id", FlexUUID, sa.ForeignKey("chat_sessions.session_id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", FlexJSON, nullable=True),
        sa.Column("tool_results", FlexJSON, nullable=True),
        sa.Column("trace_metadata", FlexJSON, nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("model_provider", sa.String(50), nullable=True),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("token_usage", FlexJSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_messages_session", "chat_messages", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_workspace", table_name="chat_sessions")
    op.drop_table("chat_sessions")
```

**Commit:** `[sprint25] add chat persistence foundation with migration 020`

---

## Task 2: ORM rows + Pydantic models + repositories

**Files:**
- Modify: `src/db/tables.py` — add ChatSessionRow, ChatMessageRow
- Create: `src/models/chat.py` — Pydantic request/response models
- Create: `src/repositories/chat.py` — ChatSessionRepository, ChatMessageRepository
- Create: `tests/repositories/test_chat.py` — round-trip + workspace isolation tests

**ORM rows** (append to `src/db/tables.py`):

```python
class ChatSessionRow(Base):
    """Workspace-scoped chat session (Sprint 25)."""
    __tablename__ = "chat_sessions"

    session_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.workspace_id"), nullable=False, index=True,
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChatMessageRow(Base):
    """Single message in a chat session (Sprint 25)."""
    __tablename__ = "chat_messages"

    message_id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_sessions.session_id"), nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls = mapped_column(FlexJSON, nullable=True)
    tool_results = mapped_column(FlexJSON, nullable=True)
    trace_metadata = mapped_column(FlexJSON, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_usage = mapped_column(FlexJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

**Pydantic models** (`src/models/chat.py`):

```python
"""Pydantic models for Economist Copilot chat (Sprint 25)."""
from __future__ import annotations
from pydantic import BaseModel, Field


class TraceMetadata(BaseModel):
    """Provenance trace attached to assistant results messages."""
    run_id: str | None = None
    scenario_spec_id: str | None = None
    scenario_spec_version: int | None = None
    model_version_id: str | None = None
    io_table: str | None = None
    multiplier_type: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    confidence: str | None = None
    confidence_reasons: list[str] = Field(default_factory=list)


class ToolCall(BaseModel):
    """Tool invocation record."""
    tool_name: str
    arguments: dict
    result: dict | None = None


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
    confirm_scenario: bool | None = None  # True = user confirms proposed scenario


class ChatSessionDetail(BaseModel):
    """Session with messages."""
    session: ChatSessionResponse
    messages: list[ChatMessageResponse]


class ListSessionsResponse(BaseModel):
    """Paginated session list."""
    sessions: list[ChatSessionResponse]
```

**Repository** (`src/repositories/chat.py`): Standard pattern — `ChatSessionRepository` with `create`, `get`, `list_for_workspace`, `update_title`; `ChatMessageRepository` with `create`, `list_for_session`.

**Tests** (`tests/repositories/test_chat.py`): Round-trip create/get, workspace isolation, message ordering, update title.

**Commit:** same as Task 1 — `[sprint25] add chat persistence foundation with migration 020`

---

## Task 3: Versioned prompt artifact

**Files:**
- Create: `src/agents/prompts/economist_copilot_v1.py`
- Create: `tests/agents/test_economist_copilot.py` (prompt construction tests first)

**What to build:**
A `build_system_prompt(context: dict) -> str` function following the depth-prompt pattern. The prompt embeds:
- Identity (expert economist copilot for Strategic Gears)
- Domain knowledge (ISIC sectors, shock types, multiplier types)
- Conversation protocol (parse → interpret → clarify → CONFIRMATION GATE → run → narrate)
- Tool definitions (lookup_data, build_scenario, run_engine, narrate_results)
- Guardrails (never invent numbers, never skip confirmation gate)
- Output format rules (Direct/Indirect/Total, SAR currency, trace metadata block)

Version constant: `COPILOT_PROMPT_VERSION = "copilot_v1"`

**Prompt tests:**
- `test_prompt_contains_critical_rules` — verify "NEVER produce economic numbers" present
- `test_prompt_contains_confirmation_gate` — verify "CONFIRMATION GATE" present
- `test_prompt_contains_tool_definitions` — verify all 4 tool names present
- `test_prompt_version_is_string` — verify version constant format

**Commit:** `[sprint25] implement economist copilot agent with versioned prompt and confirmation gate`

---

## Task 4: EconomistCopilot agent + tool execution

**Files:**
- Create: `src/agents/economist_copilot.py`
- Extend: `tests/agents/test_economist_copilot.py` (tool parsing + confirmation gate tests)

**What to build:**
`EconomistCopilot` class with:
- `__init__(self, llm_client: LLMClient, prompt_version: str = COPILOT_PROMPT_VERSION)`
- `async def process_turn(self, messages: list[dict], user_message: str, context: dict) -> CopilotResponse`
- Tool dispatch methods: `_execute_tool(tool_name, args, context)` → routes to `_lookup_data`, `_build_scenario`, `_run_engine`, `_narrate_results`
- **Confirmation gate logic**: If LLM calls `build_scenario` or `run_engine`, check `context["user_confirmed"]` — if False, return a `PENDING_CONFIRMATION` response with proposed parameters instead of executing
- `CopilotResponse` dataclass: `content: str`, `role: str`, `tool_calls: list[ToolCall]`, `trace_metadata: TraceMetadata | None`, `pending_confirmation: dict | None`, `token_usage: TokenUsage`

**Tests (TDD):**
- `test_confirmation_gate_blocks_unconfirmed_run` — verify run_engine rejected without confirmation
- `test_confirmation_gate_allows_confirmed_run` — verify run_engine proceeds with confirmation
- `test_tool_parse_valid_json` — verify tool call JSON parsing
- `test_tool_parse_invalid_json_fails_closed` — verify malformed tool calls raise error
- `test_copilot_response_has_prompt_version` — verify prompt_version on response

**Commit:** same as Task 3

---

## Task 5: ChatService orchestration

**Files:**
- Create: `src/services/chat.py`
- Create: `tests/services/test_chat.py`

**What to build:**
`ChatService` class orchestrating conversation turns:
- `__init__(self, session_repo, message_repo, copilot_agent)`
- `async def create_session(workspace_id, title?) -> ChatSessionResponse`
- `async def send_message(workspace_id, session_id, content, confirm_scenario?) -> ChatMessageResponse`
  1. Persist user message to DB
  2. Load conversation history from DB
  3. Call `copilot.process_turn(history, content, context)`
  4. If `pending_confirmation` → persist assistant message with confirmation proposal
  5. If confirmed → execute tool pipeline → persist assistant message with trace metadata
  6. Return response with trace
- `async def get_session(workspace_id, session_id) -> ChatSessionDetail`
- `async def list_sessions(workspace_id) -> ListSessionsResponse`

**Tests (TDD):**
- `test_send_message_persists_user_message` — verify DB persistence
- `test_send_message_returns_trace_metadata` — verify trace on results
- `test_confirmation_required_before_run` — service-level gate test
- `test_numbers_only_from_engine` — verify no LLM-invented numbers in response
- `test_session_workspace_isolation` — verify cross-workspace access blocked

**Commit:** `[sprint25] add workspace-scoped chat api and service orchestration`

---

## Task 6: Chat API endpoints

**Files:**
- Create: `src/api/chat.py`
- Modify: `src/api/main.py` — add `chat_router`
- Modify: `src/config/settings.py` — add `COPILOT_MODEL`, `COPILOT_MAX_TOKENS`
- Create: `tests/api/test_chat.py`

**Endpoints:**
```
POST   /v1/workspaces/{workspace_id}/chat/sessions           → CreateSession
GET    /v1/workspaces/{workspace_id}/chat/sessions            → ListSessions
GET    /v1/workspaces/{workspace_id}/chat/sessions/{id}       → GetSession
POST   /v1/workspaces/{workspace_id}/chat/sessions/{id}/messages → SendMessage
```

All endpoints use `require_workspace_member` dependency (same pattern as runs/exports/scenarios).

**Settings additions** (`src/config/settings.py`):
```python
COPILOT_MODEL: str = Field(default="claude-sonnet-4-20250514", description="Model for economist copilot.")
COPILOT_MAX_TOKENS: int = Field(default=4096, description="Max response tokens for copilot.")
```

**Tests (TDD):**
- Auth matrix: 401 (no token), 404 (wrong workspace), 200 (valid member)
- Session CRUD: create, list, get with messages
- Message flow: send user message → receive assistant response with trace
- Workspace isolation: session from workspace A not visible in workspace B
- Confirmation gate: message without confirm returns pending_confirmation
- Error cases: invalid session_id → 404, empty content → 422

**Router registration** (add to `src/api/main.py`):
```python
from src.api.chat import router as chat_router
# ... in workspace-scoped section:
app.include_router(chat_router)
```

**Commit:** same as Task 5

---

## Task 7: Frontend chat UI

**Files:**
- Create: `frontend/src/app/w/[workspaceId]/chat/page.tsx`
- Create: `frontend/src/components/chat/chat-interface.tsx`
- Create: `frontend/src/components/chat/message-bubble.tsx`
- Create: `frontend/src/components/chat/trace-metadata.tsx`
- Create: `frontend/src/components/chat/confirmation-gate.tsx`
- Create: `frontend/src/lib/api/hooks/useChat.ts`
- Modify: `frontend/src/components/layout/sidebar.tsx` — add Chat as first nav item
- Create: `frontend/src/components/chat/__tests__/chat-interface.test.tsx`

**Chat page** (`page.tsx`): Session list sidebar + active chat. Creates session on first message.

**Chat interface** (`chat-interface.tsx`): Message list + input box. Calls `useSendMessage` on submit.

**Message bubble** (`message-bubble.tsx`): Renders user (right-aligned, blue) and assistant (left-aligned, white) messages. Renders tool results inline. Shows trace metadata via `<TraceMetadata>` component.

**Trace metadata** (`trace-metadata.tsx`): Collapsible `<details>` showing run_id, scenario_spec_id, model_version_id, assumptions, confidence.

**Confirmation gate** (`confirmation-gate.tsx`): When assistant response has `pending_confirmation`, renders structured scenario summary with "Approve" / "Edit" / "Reject" buttons. Approve sends `confirm_scenario: true`.

**Hooks** (`useChat.ts`):
- `useCreateSession(workspaceId)` — POST to create session
- `useChatSessions(workspaceId)` — GET list sessions
- `useChatSession(workspaceId, sessionId)` — GET session with messages
- `useSendMessage(workspaceId, sessionId)` — POST send message

**Sidebar** — add `{ label: 'Chat', href: '/chat', icon: MessageSquare }` as first entry in `NAV_ITEMS`.

**Tests** (`chat-interface.test.tsx`):
- Renders message list
- Renders confirmation gate when pending
- Sends message on submit
- Shows trace metadata on results message
- Shows loading state while sending
- Shows error state on failure

**Commit:** `[sprint25] add chat frontend interface with trace metadata and sidebar entry`

---

## Task 8: Docs/evidence/contracts sync

**Files:**
- Regenerate: `openapi.json`
- Update: `docs/ImpactOS_Master_Build_Plan_v2.md` — Sprint 25 row
- Update: `docs/plans/2026-03-03-full-system-completion-master-plan.md` — Sprint 25 entry
- Create: `docs/evidence/sprint25-copilot-evidence.md` — constraint compliance evidence

**OpenAPI regeneration:**
```bash
python -c "import json; from pathlib import Path; from src.api.main import app; Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
```

**Evidence doc** must prove all 6 constraints:
- C-1: DB persistence — migration 020, repository tests
- C-2: Versioned prompt — COPILOT_PROMPT_VERSION constant, prompt_version on messages
- C-3: Confirmation gate — test evidence showing gate blocks unconfirmed runs
- C-4: Trace metadata — test evidence showing trace on every results message
- C-5: LLM never outputs numbers — test evidence + prompt guardrail
- C-6: Existing layers untouched — regression test pass counts match baseline

**Commit:** `[sprint25] refresh sprint25 evidence and openapi`

---

## Execution Order

1. Task 1 + Task 2 together (persistence foundation)
2. Task 3 + Task 4 together (agent + prompt)
3. Task 5 + Task 6 together (service + API)
4. Task 7 (frontend)
5. Task 8 (docs/evidence)
6. Code review + final verification + PR
