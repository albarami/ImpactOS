import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import {
  useCreateRun,
  useRunResults,
  useWorkspaceRuns,
  type CreateRunRequest,
  type RunResponse,
  type ListRunsResponse,
} from '../useRuns';

const mockPost = vi.fn();
const mockGet = vi.fn();

vi.mock('../../client', () => ({
  api: {
    POST: (...args: unknown[]) => mockPost(...args),
    GET: (...args: unknown[]) => mockGet(...args),
  },
}));

const WORKSPACE_ID = 'ws-001';
const RUN_ID = 'run-001';

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

// ── useCreateRun ──────────────────────────────────────────────────────

describe('useCreateRun', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to engine/runs endpoint and returns run data', async () => {
    const response: RunResponse = {
      run_id: RUN_ID,
      result_sets: [
        {
          result_id: 'rs-001',
          metric_type: 'gross_output',
          values: { S01: 1500000, S02: 750000 },
        },
      ],
      snapshot: {
        run_id: RUN_ID,
        model_version_id: 'mv-001',
      },
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(() => useCreateRun(WORKSPACE_ID), {
      wrapper: createWrapper(),
    });

    const request: CreateRunRequest = {
      model_version_id: 'mv-001',
      annual_shocks: { '2025': [100, 200, 300] },
      base_year: 2020,
      satellite_coefficients: {
        jobs_coeff: [0.1, 0.2, 0.3],
        import_ratio: [0.3, 0.4, 0.5],
        va_ratio: [0.7, 0.6, 0.5],
      },
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/engine/runs',
      expect.objectContaining({
        params: { path: { workspace_id: WORKSPACE_ID } },
        body: request,
      })
    );
    expect(result.current.data).toEqual(response);
  });

  it('supports optional deflators', async () => {
    const response: RunResponse = {
      run_id: RUN_ID,
      result_sets: [],
      snapshot: { run_id: RUN_ID, model_version_id: 'mv-001' },
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(() => useCreateRun(WORKSPACE_ID), {
      wrapper: createWrapper(),
    });

    const request: CreateRunRequest = {
      model_version_id: 'mv-001',
      annual_shocks: { '2025': [100] },
      base_year: 2020,
      satellite_coefficients: {
        jobs_coeff: [0.1],
        import_ratio: [0.3],
        va_ratio: [0.7],
      },
      deflators: { '2025': 1.02 },
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const body = mockPost.mock.calls[0][1].body;
    expect(body.deflators).toEqual({ '2025': 1.02 });
  });

  it('throws on API error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Model not found' },
    });

    const { result } = renderHook(() => useCreateRun(WORKSPACE_ID), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        model_version_id: 'mv-bad',
        annual_shocks: {},
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

// ── useRunResults ─────────────────────────────────────────────────────

describe('useRunResults', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches run results by run_id', async () => {
    const response: RunResponse = {
      run_id: RUN_ID,
      result_sets: [
        {
          result_id: 'rs-001',
          metric_type: 'gross_output',
          values: { S01: 1500000, S02: 750000 },
        },
        {
          result_id: 'rs-002',
          metric_type: 'value_added',
          values: { S01: 900000, S02: 450000 },
        },
      ],
      snapshot: {
        run_id: RUN_ID,
        model_version_id: 'mv-001',
      },
    };
    mockGet.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useRunResults(WORKSPACE_ID, RUN_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockGet).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/engine/runs/{run_id}',
      {
        params: {
          path: {
            workspace_id: WORKSPACE_ID,
            run_id: RUN_ID,
          },
        },
      }
    );
    expect(result.current.data?.result_sets).toHaveLength(2);
    expect(result.current.data?.run_id).toBe(RUN_ID);
  });

  it('is disabled when runId is empty', () => {
    const { result } = renderHook(
      () => useRunResults(WORKSPACE_ID, ''),
      { wrapper: createWrapper() }
    );

    expect(result.current.fetchStatus).toBe('idle');
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('throws on API error', async () => {
    mockGet.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Not found' },
    });

    const { result } = renderHook(
      () => useRunResults(WORKSPACE_ID, RUN_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useWorkspaceRuns (Sprint 24 — I-4) ───────────────────────────────

describe('useWorkspaceRuns', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches workspace runs list', async () => {
    const response: ListRunsResponse = {
      runs: [
        {
          run_id: 'run-001',
          model_version_id: 'mv-001',
          created_at: '2025-06-01T10:00:00Z',
        },
        {
          run_id: 'run-002',
          model_version_id: 'mv-001',
          created_at: '2025-06-02T14:30:00Z',
        },
      ],
    };
    mockGet.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useWorkspaceRuns(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockGet).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/engine/runs',
      {
        params: { path: { workspace_id: WORKSPACE_ID } },
      }
    );
    expect(result.current.data?.runs).toHaveLength(2);
    expect(result.current.data?.runs[0].run_id).toBe('run-001');
  });

  it('is disabled when workspaceId is empty', () => {
    const { result } = renderHook(
      () => useWorkspaceRuns(''),
      { wrapper: createWrapper() }
    );

    expect(result.current.fetchStatus).toBe('idle');
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('throws on API error', async () => {
    mockGet.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Workspace not found' },
    });

    const { result } = renderHook(
      () => useWorkspaceRuns(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });

  it('handles empty runs list', async () => {
    const response: ListRunsResponse = { runs: [] };
    mockGet.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useWorkspaceRuns(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.runs).toHaveLength(0);
  });
});
