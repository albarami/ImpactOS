import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { ChatInterface } from '../chat-interface';
import type {
  ChatMessageResponse,
  TraceMetadata,
} from '@/lib/api/hooks/useChat';

// ── Global mocks ─────────────────────────────────────────────────────

// jsdom does not implement scrollIntoView
Element.prototype.scrollIntoView = vi.fn();

// ── Mocks ────────────────────────────────────────────────────────────

const mockMutate = vi.fn();
const mockUseChatSession = vi.fn();
const mockUseSendMessage = vi.fn();

vi.mock('@/lib/api/hooks/useChat', () => ({
  useChatSession: (...args: unknown[]) => mockUseChatSession(...args),
  useSendMessage: (...args: unknown[]) => mockUseSendMessage(...args),
  hasPendingConfirmation: (msg: ChatMessageResponse) => {
    if (msg.role !== 'assistant') return false;
    return !!msg.trace_metadata?.pending_confirmation;
  },
  getPendingToolCall: (msg: ChatMessageResponse) => {
    const pc = msg.trace_metadata?.pending_confirmation;
    if (!pc) return null;
    return { tool_name: pc.tool, arguments: pc.arguments };
  },
}));

// ── Test data ────────────────────────────────────────────────────────

function makeMessage(
  overrides: Partial<ChatMessageResponse> & { message_id: string; role: 'user' | 'assistant' }
): ChatMessageResponse {
  return {
    content: '',
    created_at: '2026-03-05T10:00:00Z',
    ...overrides,
  };
}

const USER_MESSAGE = makeMessage({
  message_id: 'msg-001',
  role: 'user',
  content: 'What is the GDP impact of increasing construction by 10%?',
});

const ASSISTANT_MESSAGE = makeMessage({
  message_id: 'msg-002',
  role: 'assistant',
  content: 'Based on the I-O model, a 10% increase in construction would...',
});

const TRACE: TraceMetadata = {
  run_id: 'run-abc',
  scenario_spec_id: 'spec-001',
  scenario_spec_version: 3,
  model_version_id: 'mv-001',
  assumptions: ['Linear coefficients', 'Open economy'],
  confidence: 'HIGH',
  confidence_reasons: ['Well-calibrated model'],
};

const ASSISTANT_WITH_TRACE = makeMessage({
  message_id: 'msg-003',
  role: 'assistant',
  content: 'The simulation results show a positive GDP impact.',
  trace_metadata: TRACE,
});

const ASSISTANT_PENDING = makeMessage({
  message_id: 'msg-004',
  role: 'assistant',
  content: 'I would like to build a scenario. Please confirm.',
  trace_metadata: {
    pending_confirmation: {
      tool: 'build_scenario',
      arguments: { sector: 'S01', shock_pct: 10 },
    },
  },
});

// ── Helpers ──────────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function renderChatInterface() {
  return render(
    createElement(
      createWrapper(),
      null,
      createElement(ChatInterface, {
        workspaceId: 'ws-001',
        sessionId: 'session-001',
      })
    )
  );
}

function setupDefaultMocks(
  messages: ChatMessageResponse[] = [USER_MESSAGE, ASSISTANT_MESSAGE],
  mutationOverrides: Record<string, unknown> = {}
) {
  mockUseChatSession.mockReturnValue({
    data: {
      session: {
        session_id: 'session-001',
        workspace_id: 'ws-001',
        title: 'Test Session',
        created_at: '2026-03-05T10:00:00Z',
        updated_at: '2026-03-05T10:00:00Z',
      },
      messages,
    },
    isLoading: false,
    error: null,
  });

  mockUseSendMessage.mockReturnValue({
    mutate: mockMutate,
    isPending: false,
    isError: false,
    error: null,
    ...mutationOverrides,
  });
}

// ── Tests ────────────────────────────────────────────────────────────

describe('ChatInterface', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders message list with user and assistant messages', () => {
    setupDefaultMocks();
    renderChatInterface();

    expect(
      screen.getByText('What is the GDP impact of increasing construction by 10%?')
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Based on the I-O model, a 10% increase in construction would...'
      )
    ).toBeInTheDocument();
  });

  it('renders confirmation gate when last message has pending tool call', () => {
    setupDefaultMocks([USER_MESSAGE, ASSISTANT_PENDING]);
    renderChatInterface();

    expect(screen.getByText('Confirmation Required')).toBeInTheDocument();
    expect(screen.getByText('build_scenario')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
  });

  it('sends message on submit', async () => {
    setupDefaultMocks();
    const user = userEvent.setup();
    renderChatInterface();

    const input = screen.getByLabelText('Chat message input');
    await user.type(input, 'Run the simulation');

    const sendButton = screen.getByRole('button', { name: /send message/i });
    await user.click(sendButton);

    expect(mockMutate).toHaveBeenCalledWith({
      content: 'Run the simulation',
    });
  });

  it('shows trace metadata on assistant message with trace data', () => {
    setupDefaultMocks([USER_MESSAGE, ASSISTANT_WITH_TRACE]);
    renderChatInterface();

    expect(screen.getByText('Trace Details')).toBeInTheDocument();
  });

  it('shows loading state while sending', () => {
    setupDefaultMocks([USER_MESSAGE], { isPending: true });
    renderChatInterface();

    expect(screen.getByTestId('sending-indicator')).toBeInTheDocument();
    expect(screen.getByText('Thinking...')).toBeInTheDocument();
  });

  it('shows error state on send failure', () => {
    setupDefaultMocks([USER_MESSAGE], {
      isError: true,
      error: new Error('Network timeout'),
    });
    renderChatInterface();

    expect(screen.getByTestId('send-error')).toBeInTheDocument();
    expect(
      screen.getByText(/failed to send message: network timeout/i)
    ).toBeInTheDocument();
  });

  it('shows loading skeleton while session is loading', () => {
    mockUseChatSession.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    });
    mockUseSendMessage.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isError: false,
      error: null,
    });

    renderChatInterface();

    expect(screen.getByTestId('chat-loading')).toBeInTheDocument();
  });

  it('shows session error state', () => {
    mockUseChatSession.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Session not found'),
    });
    mockUseSendMessage.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isError: false,
      error: null,
    });

    renderChatInterface();

    expect(
      screen.getByText('Failed to load chat session')
    ).toBeInTheDocument();
    expect(screen.getByText('Session not found')).toBeInTheDocument();
  });

  it('sends Enter key to submit (without shift)', async () => {
    setupDefaultMocks();
    const user = userEvent.setup();
    renderChatInterface();

    const input = screen.getByLabelText('Chat message input');
    await user.type(input, 'Hello copilot');
    await user.keyboard('{Enter}');

    expect(mockMutate).toHaveBeenCalledWith({
      content: 'Hello copilot',
    });
  });

  it('does not send on Enter+Shift', async () => {
    setupDefaultMocks();
    const user = userEvent.setup();
    renderChatInterface();

    const input = screen.getByLabelText('Chat message input');
    await user.type(input, 'Multiline');
    await user.keyboard('{Shift>}{Enter}{/Shift}');

    expect(mockMutate).not.toHaveBeenCalled();
  });

  it('disables send button when input is empty', () => {
    setupDefaultMocks();
    renderChatInterface();

    const sendButton = screen.getByRole('button', { name: /send message/i });
    expect(sendButton).toBeDisabled();
  });

  it('shows empty state when no messages', () => {
    setupDefaultMocks([]);
    renderChatInterface();

    expect(
      screen.getByText('Send a message to start the conversation.')
    ).toBeInTheDocument();
  });

  it('calls approve with confirm_scenario: true', async () => {
    setupDefaultMocks([USER_MESSAGE, ASSISTANT_PENDING]);
    const user = userEvent.setup();
    renderChatInterface();

    await user.click(screen.getByRole('button', { name: /approve/i }));

    expect(mockMutate).toHaveBeenCalledWith({
      content: 'Approved. Please proceed.',
      confirm_scenario: true,
    });
  });

  // ── Tool Execution Visibility Tests ─────────────────────────────────

  it('renders executed tool results with success badge', () => {
    const msgWithSuccessTool = makeMessage({
      message_id: 'msg-010',
      role: 'assistant',
      content: 'I ran the engine for you.',
      tool_calls: [
        {
          tool_name: 'run_engine',
          arguments: { scenario_id: 'sc-01' },
          result: {
            status: 'success',
            reason_code: 'ok',
            retryable: false,
            latency_ms: 320,
            result: { gdp_impact: 1.5 },
          },
        },
      ],
    });

    setupDefaultMocks([USER_MESSAGE, msgWithSuccessTool]);
    renderChatInterface();

    expect(screen.getByText('success')).toBeInTheDocument();
    expect(screen.getByTestId('tool-status-badge-success')).toBeInTheDocument();
  });

  it('renders executed tool results with error badge and error_summary', () => {
    const msgWithErrorTool = makeMessage({
      message_id: 'msg-011',
      role: 'assistant',
      content: 'The engine run failed.',
      tool_calls: [
        {
          tool_name: 'run_engine',
          arguments: { scenario_id: 'sc-02' },
          result: {
            status: 'error',
            reason_code: 'engine_timeout',
            retryable: true,
            latency_ms: 5000,
            error_summary: 'Engine timed out after 5s',
          },
        },
      ],
    });

    setupDefaultMocks([USER_MESSAGE, msgWithErrorTool]);
    renderChatInterface();

    expect(screen.getByText('error')).toBeInTheDocument();
    expect(screen.getByTestId('tool-status-badge-error')).toBeInTheDocument();
    expect(screen.getByText('Engine timed out after 5s')).toBeInTheDocument();
  });

  it('renders executed tool results with blocked badge and reason_code', () => {
    const msgWithBlockedTool = makeMessage({
      message_id: 'msg-012',
      role: 'assistant',
      content: 'The tool was blocked by governance.',
      tool_calls: [
        {
          tool_name: 'build_scenario',
          arguments: { sector: 'S01' },
          result: {
            status: 'blocked',
            reason_code: 'governance_hold',
            retryable: false,
            latency_ms: 10,
          },
        },
      ],
    });

    setupDefaultMocks([USER_MESSAGE, msgWithBlockedTool]);
    renderChatInterface();

    expect(screen.getByText('blocked')).toBeInTheDocument();
    expect(screen.getByTestId('tool-status-badge-blocked')).toBeInTheDocument();
    expect(screen.getByText('governance_hold')).toBeInTheDocument();
  });

  it('renders deep link for run_id in trace metadata', () => {
    setupDefaultMocks([USER_MESSAGE, ASSISTANT_WITH_TRACE]);
    renderChatInterface();

    const runLink = screen.getByTestId('trace-run-link');
    expect(runLink).toBeInTheDocument();
    expect(runLink).toHaveAttribute('href', '/w/ws-001/runs/run-abc');
  });
});
