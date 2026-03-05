import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

// ── Types ──────────────────────────────────────────────────────────────

export interface ToolCall {
  tool_name: string;
  arguments: Record<string, unknown>;
  result?: Record<string, unknown> | null;
}

export interface PendingConfirmation {
  tool: string;
  arguments: Record<string, unknown>;
}

export interface TraceMetadata {
  run_id?: string | null;
  scenario_spec_id?: string | null;
  scenario_spec_version?: number | null;
  model_version_id?: string | null;
  io_table?: string | null;
  multiplier_type?: string | null;
  assumptions?: string[];
  confidence?: string | null;
  confidence_reasons?: string[];
  pending_confirmation?: PendingConfirmation | null;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
}

export interface ChatMessageResponse {
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
  tool_calls?: ToolCall[] | null;
  trace_metadata?: TraceMetadata | null;
  prompt_version?: string | null;
  model_provider?: string | null;
  model_id?: string | null;
  token_usage?: TokenUsage | null;
  created_at: string;
}

export interface ChatSessionResponse {
  session_id: string;
  workspace_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

interface ChatSessionsListResponse {
  sessions: ChatSessionResponse[];
}

interface ChatSessionDetailResponse {
  session: ChatSessionResponse;
  messages: ChatMessageResponse[];
}

// ── Fetch helper ───────────────────────────────────────────────────────

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function chatFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`Chat API error: ${res.status}`);
  return res.json();
}

// ── Hooks ──────────────────────────────────────────────────────────────

/**
 * List chat sessions for a workspace.
 */
export function useChatSessions(workspaceId: string) {
  return useQuery<ChatSessionsListResponse>({
    queryKey: ['chat-sessions', workspaceId],
    queryFn: () =>
      chatFetch<ChatSessionsListResponse>(
        `/v1/workspaces/${workspaceId}/chat/sessions?limit=50&offset=0`
      ),
  });
}

/**
 * Fetch a single chat session with its messages.
 * Enabled only when sessionId is non-null.
 */
export function useChatSession(
  workspaceId: string,
  sessionId: string | null
) {
  return useQuery<ChatSessionDetailResponse>({
    queryKey: ['chat-session', workspaceId, sessionId],
    queryFn: () =>
      chatFetch<ChatSessionDetailResponse>(
        `/v1/workspaces/${workspaceId}/chat/sessions/${sessionId}`
      ),
    enabled: !!sessionId,
  });
}

/**
 * Create a new chat session.
 */
export function useCreateSession(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation<ChatSessionResponse, Error, { title?: string }>({
    mutationFn: (body) =>
      chatFetch<ChatSessionResponse>(
        `/v1/workspaces/${workspaceId}/chat/sessions`,
        {
          method: 'POST',
          body: JSON.stringify(body),
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['chat-sessions', workspaceId],
      });
    },
  });
}

/**
 * Send a message to a chat session.
 */
export function useSendMessage(
  workspaceId: string,
  sessionId: string | null
) {
  const queryClient = useQueryClient();

  return useMutation<
    ChatMessageResponse,
    Error,
    { content: string; confirm_scenario?: boolean }
  >({
    mutationFn: (body) =>
      chatFetch<ChatMessageResponse>(
        `/v1/workspaces/${workspaceId}/chat/sessions/${sessionId}/messages`,
        {
          method: 'POST',
          body: JSON.stringify(body),
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['chat-session', workspaceId, sessionId],
      });
    },
  });
}

// ── Helpers ────────────────────────────────────────────────────────────

/**
 * Check whether a message has a pending confirmation gate.
 *
 * The backend stores pending_confirmation inside trace_metadata
 * when a gated tool (build_scenario, run_engine) is blocked.
 */
export function hasPendingConfirmation(
  message: ChatMessageResponse
): boolean {
  if (message.role !== 'assistant') return false;
  return !!message.trace_metadata?.pending_confirmation;
}

/**
 * Extract the pending tool call from trace_metadata.pending_confirmation.
 * Returns a ToolCall-shaped object for the confirmation gate UI.
 */
export function getPendingToolCall(
  message: ChatMessageResponse
): ToolCall | null {
  const pc = message.trace_metadata?.pending_confirmation;
  if (!pc) return null;
  return {
    tool_name: pc.tool,
    arguments: pc.arguments,
  };
}
