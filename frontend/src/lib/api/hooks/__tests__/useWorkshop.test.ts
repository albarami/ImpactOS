import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import {
  useCreateWorkshopSession,
  useWorkshopSession,
  useWorkshopSessions,
  useWorkshopPreview,
  useCommitWorkshopSession,
  type CreateSessionRequest,
  type WorkshopSessionResponse,
  type WorkshopListResponse,
  type PreviewRequest,
  type PreviewResponse,
  type CommitRequest,
} from '../useWorkshop';

// ── Global fetch mock ─────────────────────────────────────────────────

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const WORKSPACE_ID = 'ws-001';
const SESSION_ID = 'sess-001';

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children);
  };
}

function mockJsonResponse(data: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  };
}

// ── useCreateWorkshopSession ──────────────────────────────────────────

describe('useCreateWorkshopSession', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to workshop/sessions endpoint and returns session data', async () => {
    const response: WorkshopSessionResponse = {
      session_id: SESSION_ID,
      workspace_id: WORKSPACE_ID,
      baseline_run_id: 'run-001',
      slider_config: [{ sector_code: 'S01', pct_delta: 10 }],
      status: 'draft',
      committed_run_id: null,
      config_hash: 'abc123',
      preview_summary: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    mockFetch.mockResolvedValueOnce(mockJsonResponse(response));

    const { result } = renderHook(
      () => useCreateWorkshopSession(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    const request: CreateSessionRequest = {
      baseline_run_id: 'run-001',
      base_shocks: { '2025': [100, 200] },
      sliders: [{ sector_code: 'S01', pct_delta: 10 }],
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(`/v1/workspaces/${WORKSPACE_ID}/workshop/sessions`),
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      })
    );
    expect(result.current.data).toEqual(response);
  });

  it('throws on API error', async () => {
    mockFetch.mockResolvedValueOnce(
      mockJsonResponse({ detail: 'Bad request' }, false, 400)
    );

    const { result } = renderHook(
      () => useCreateWorkshopSession(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      result.current.mutate({
        baseline_run_id: '',
        base_shocks: {},
        sliders: [],
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useWorkshopSession ────────────────────────────────────────────────

describe('useWorkshopSession', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches a workshop session by session_id', async () => {
    const response: WorkshopSessionResponse = {
      session_id: SESSION_ID,
      workspace_id: WORKSPACE_ID,
      baseline_run_id: 'run-001',
      slider_config: [],
      status: 'draft',
      committed_run_id: null,
      config_hash: 'abc123',
      preview_summary: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    mockFetch.mockResolvedValueOnce(mockJsonResponse(response));

    const { result } = renderHook(
      () => useWorkshopSession(WORKSPACE_ID, SESSION_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(
        `/v1/workspaces/${WORKSPACE_ID}/workshop/sessions/${SESSION_ID}`
      ),
      undefined
    );
    expect(result.current.data?.session_id).toBe(SESSION_ID);
  });

  it('is disabled when sessionId is empty', () => {
    const { result } = renderHook(
      () => useWorkshopSession(WORKSPACE_ID, ''),
      { wrapper: createWrapper() }
    );

    expect(result.current.fetchStatus).toBe('idle');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('throws on API error', async () => {
    mockFetch.mockResolvedValueOnce(
      mockJsonResponse({ detail: 'Not found' }, false, 404)
    );

    const { result } = renderHook(
      () => useWorkshopSession(WORKSPACE_ID, SESSION_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useWorkshopSessions ───────────────────────────────────────────────

describe('useWorkshopSessions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches paginated session list', async () => {
    const response: WorkshopListResponse = {
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    };
    mockFetch.mockResolvedValueOnce(mockJsonResponse(response));

    const { result } = renderHook(
      () => useWorkshopSessions(WORKSPACE_ID, 20, 0),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(
        `/v1/workspaces/${WORKSPACE_ID}/workshop/sessions?limit=20&offset=0`
      ),
      undefined
    );
    expect(result.current.data?.items).toEqual([]);
  });

  it('passes custom pagination params', async () => {
    const response: WorkshopListResponse = {
      items: [],
      total: 50,
      limit: 10,
      offset: 20,
    };
    mockFetch.mockResolvedValueOnce(mockJsonResponse(response));

    const { result } = renderHook(
      () => useWorkshopSessions(WORKSPACE_ID, 10, 20),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('limit=10&offset=20'),
      undefined
    );
  });
});

// ── useWorkshopPreview ────────────────────────────────────────────────

describe('useWorkshopPreview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to workshop/preview endpoint', async () => {
    const response: PreviewResponse = {
      result_sets: [
        {
          result_id: 'rs-001',
          metric_type: 'gross_output',
          values: { S01: 1000, S02: 2000 },
        },
      ],
      transformed_shocks: { '2025': [150, 250] },
      ephemeral: true,
    };
    mockFetch.mockResolvedValueOnce(mockJsonResponse(response));

    const { result } = renderHook(
      () => useWorkshopPreview(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    const request: PreviewRequest = {
      baseline_run_id: 'run-001',
      base_shocks: { '2025': [100, 200] },
      sliders: [{ sector_code: 'S01', pct_delta: 5 }],
      model_version_id: 'mv-001',
      base_year: 2020,
      satellite_coefficients: {
        jobs_coeff: [0.1],
        import_ratio: [0.3],
        va_ratio: [0.7],
      },
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(`/v1/workspaces/${WORKSPACE_ID}/workshop/preview`),
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      })
    );
    expect(result.current.data?.ephemeral).toBe(true);
    expect(result.current.data?.result_sets).toHaveLength(1);
  });

  it('throws on API error', async () => {
    mockFetch.mockResolvedValueOnce(
      mockJsonResponse({ detail: 'Engine error' }, false, 500)
    );

    const { result } = renderHook(
      () => useWorkshopPreview(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      result.current.mutate({
        baseline_run_id: '',
        base_shocks: {},
        sliders: [],
        model_version_id: '',
        base_year: 2020,
        satellite_coefficients: {
          jobs_coeff: [],
          import_ratio: [],
          va_ratio: [],
        },
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useCommitWorkshopSession ──────────────────────────────────────────

describe('useCommitWorkshopSession', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to commit endpoint', async () => {
    const response: WorkshopSessionResponse = {
      session_id: SESSION_ID,
      workspace_id: WORKSPACE_ID,
      baseline_run_id: 'run-001',
      slider_config: [],
      status: 'committed',
      committed_run_id: 'run-002',
      config_hash: 'abc123',
      preview_summary: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    mockFetch.mockResolvedValueOnce(mockJsonResponse(response));

    const { result } = renderHook(
      () => useCommitWorkshopSession(WORKSPACE_ID, SESSION_ID),
      { wrapper: createWrapper() }
    );

    const request: CommitRequest = {
      model_version_id: 'mv-001',
      base_year: 2020,
      satellite_coefficients: {
        jobs_coeff: [0.1],
        import_ratio: [0.3],
        va_ratio: [0.7],
      },
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(
        `/v1/workspaces/${WORKSPACE_ID}/workshop/sessions/${SESSION_ID}/commit`
      ),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(request),
      })
    );
    expect(result.current.data?.status).toBe('committed');
  });
});
