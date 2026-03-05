import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import {
  useChatSessions,
  useChatSession,
  useCreateSession,
  useSendMessage,
  type ChatSessionResponse,
  type ChatMessageResponse,
} from '../useChat';

const mockPost = vi.fn();
const mockGet = vi.fn();

vi.mock('../../client', () => ({
  api: {
    POST: (...args: unknown[]) => mockPost(...args),
    GET: (...args: unknown[]) => mockGet(...args),
  },
}));

const WORKSPACE_ID = 'ws-001';
const SESSION_ID = 'session-001';

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children);
  }
  return { Wrapper, queryClient: qc };
}

function wrapperOnly() {
  return createWrapper().Wrapper;
}

// ── useChatSessions ──────────────────────────────────────────────────

describe('useChatSessions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls api.GET with correct path and params', async () => {
    const response = {
      sessions: [
        {
          session_id: SESSION_ID,
          workspace_id: WORKSPACE_ID,
          title: 'Test',
          created_at: '2026-03-05T10:00:00Z',
          updated_at: '2026-03-05T10:00:00Z',
        },
      ],
    };
    mockGet.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(() => useChatSessions(WORKSPACE_ID), {
      wrapper: wrapperOnly(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockGet).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/chat/sessions',
      expect.objectContaining({
        params: expect.objectContaining({
          path: { workspace_id: WORKSPACE_ID },
        }),
      })
    );
    expect(result.current.data?.sessions).toHaveLength(1);
  });
});

// ── useChatSession ───────────────────────────────────────────────────

describe('useChatSession', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls api.GET with session path', async () => {
    const response = {
      session: {
        session_id: SESSION_ID,
        workspace_id: WORKSPACE_ID,
        title: 'Test',
        created_at: '2026-03-05T10:00:00Z',
        updated_at: '2026-03-05T10:00:00Z',
      },
      messages: [],
    };
    mockGet.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useChatSession(WORKSPACE_ID, SESSION_ID),
      { wrapper: wrapperOnly() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockGet).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/chat/sessions/{session_id}',
      expect.objectContaining({
        params: expect.objectContaining({
          path: { workspace_id: WORKSPACE_ID, session_id: SESSION_ID },
        }),
      })
    );
  });

  it('is disabled when sessionId is null', () => {
    const { result } = renderHook(
      () => useChatSession(WORKSPACE_ID, null),
      { wrapper: wrapperOnly() }
    );

    expect(result.current.fetchStatus).toBe('idle');
    expect(mockGet).not.toHaveBeenCalled();
  });
});

// ── useCreateSession ─────────────────────────────────────────────────

describe('useCreateSession', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls api.POST to create session', async () => {
    const response: ChatSessionResponse = {
      session_id: SESSION_ID,
      workspace_id: WORKSPACE_ID,
      title: 'New Session',
      created_at: '2026-03-05T10:00:00Z',
      updated_at: '2026-03-05T10:00:00Z',
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(() => useCreateSession(WORKSPACE_ID), {
      wrapper: wrapperOnly(),
    });

    await act(async () => {
      result.current.mutate({ title: 'New Session' });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/chat/sessions',
      expect.objectContaining({
        params: { path: { workspace_id: WORKSPACE_ID } },
        body: { title: 'New Session' },
      })
    );
    expect(result.current.data).toEqual(response);
  });
});

// ── useSendMessage ───────────────────────────────────────────────────

describe('useSendMessage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls api.POST with message body', async () => {
    const response: ChatMessageResponse = {
      message_id: 'msg-001',
      role: 'assistant',
      content: 'I can help with that.',
      created_at: '2026-03-05T10:00:00Z',
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useSendMessage(WORKSPACE_ID, SESSION_ID),
      { wrapper: wrapperOnly() }
    );

    await act(async () => {
      result.current.mutate({ content: 'Hello' });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/chat/sessions/{session_id}/messages',
      expect.objectContaining({
        params: expect.objectContaining({
          path: { workspace_id: WORKSPACE_ID, session_id: SESSION_ID },
        }),
        body: { content: 'Hello' },
      })
    );
  });

  it('sends confirm_scenario in body', async () => {
    const response: ChatMessageResponse = {
      message_id: 'msg-002',
      role: 'assistant',
      content: 'Proceeding with scenario.',
      created_at: '2026-03-05T10:00:00Z',
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useSendMessage(WORKSPACE_ID, SESSION_ID),
      { wrapper: wrapperOnly() }
    );

    await act(async () => {
      result.current.mutate({ content: 'Approved', confirm_scenario: true });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const body = mockPost.mock.calls[0][1].body;
    expect(body.confirm_scenario).toBe(true);
  });

  it('invalidates session cache on success', async () => {
    const response: ChatMessageResponse = {
      message_id: 'msg-003',
      role: 'assistant',
      content: 'Done.',
      created_at: '2026-03-05T10:00:00Z',
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { Wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(
      () => useSendMessage(WORKSPACE_ID, SESSION_ID),
      { wrapper: Wrapper }
    );

    await act(async () => {
      result.current.mutate({ content: 'Test' });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['chat-session', WORKSPACE_ID, SESSION_ID],
    });
  });

  it('throws on api error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Session not found' },
    });

    const { result } = renderHook(
      () => useSendMessage(WORKSPACE_ID, SESSION_ID),
      { wrapper: wrapperOnly() }
    );

    await act(async () => {
      result.current.mutate({ content: 'Test' });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
