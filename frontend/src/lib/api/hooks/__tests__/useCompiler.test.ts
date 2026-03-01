import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import {
  useCompile,
  useCompilationStatus,
  useBulkDecisions,
  useCompilationData,
  type CompileRequest,
  type CompileResponse,
  type CompilationStatusResponse,
  type BulkDecisionsRequest,
  type BulkDecisionsResponse,
} from '../useCompiler';

const mockPost = vi.fn();
const mockGet = vi.fn();

vi.mock('../../client', () => ({
  api: {
    POST: (...args: unknown[]) => mockPost(...args),
    GET: (...args: unknown[]) => mockGet(...args),
  },
}));

const WORKSPACE_ID = 'ws-001';
const COMPILATION_ID = 'comp-001';

function createWrapper(queryClient?: QueryClient) {
  const qc =
    queryClient ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children);
  };
}

// ── useCompile ─────────────────────────────────────────────────────────

describe('useCompile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to compile endpoint and returns suggestions', async () => {
    const compileResponse: CompileResponse = {
      compilation_id: COMPILATION_ID,
      suggestions: [
        {
          line_item_id: 'li-001',
          sector_code: 'S01',
          confidence: 0.92,
          explanation: 'High confidence mapping to construction sector',
        },
      ],
      high_confidence: 1,
      medium_confidence: 0,
      low_confidence: 0,
    };
    mockPost.mockResolvedValueOnce({ data: compileResponse, error: undefined });

    const { result } = renderHook(() => useCompile(WORKSPACE_ID), {
      wrapper: createWrapper(),
    });

    const request: CompileRequest = {
      scenario_name: 'Test Scenario',
      base_model_version_id: 'mv-001',
      base_year: 2020,
      start_year: 2025,
      end_year: 2030,
      document_id: 'doc-001',
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/compiler/compile',
      expect.objectContaining({
        params: { path: { workspace_id: WORKSPACE_ID } },
        body: request,
      })
    );
    expect(result.current.data).toEqual(compileResponse);
  });

  it('caches the compile response by compilation_id', async () => {
    const compileResponse: CompileResponse = {
      compilation_id: COMPILATION_ID,
      suggestions: [
        {
          line_item_id: 'li-001',
          sector_code: 'S01',
          confidence: 0.92,
          explanation: 'Mapped to construction',
        },
      ],
      high_confidence: 1,
      medium_confidence: 0,
      low_confidence: 0,
    };
    mockPost.mockResolvedValueOnce({ data: compileResponse, error: undefined });

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const wrapper = createWrapper(queryClient);

    const { result } = renderHook(() => useCompile(WORKSPACE_ID), {
      wrapper,
    });

    const request: CompileRequest = {
      scenario_name: 'Test Scenario',
      base_model_version_id: 'mv-001',
      base_year: 2020,
      start_year: 2025,
      end_year: 2030,
      document_id: 'doc-001',
    };

    await act(async () => {
      await result.current.mutateAsync(request);
    });

    // Verify that the cache contains the compilation data
    const cached = queryClient.getQueryData<CompileResponse>([
      'compilation',
      COMPILATION_ID,
    ]);
    expect(cached).toEqual(compileResponse);
  });

  it('throws on API error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Validation error' },
    });

    const { result } = renderHook(() => useCompile(WORKSPACE_ID), {
      wrapper: createWrapper(),
    });

    const request: CompileRequest = {
      scenario_name: 'Bad Scenario',
      base_model_version_id: 'mv-001',
      base_year: 2020,
      start_year: 2025,
      end_year: 2030,
      document_id: 'doc-001',
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useCompilationStatus ───────────────────────────────────────────────

describe('useCompilationStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches compilation status', async () => {
    const statusResponse: CompilationStatusResponse = {
      compilation_id: COMPILATION_ID,
      total_suggestions: 10,
      high_confidence: 5,
      medium_confidence: 3,
      low_confidence: 2,
      assumption_drafts: 1,
    };
    mockGet.mockResolvedValueOnce({ data: statusResponse, error: undefined });

    const { result } = renderHook(
      () => useCompilationStatus(WORKSPACE_ID, COMPILATION_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockGet).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/compiler/{compilation_id}/status',
      {
        params: {
          path: {
            workspace_id: WORKSPACE_ID,
            compilation_id: COMPILATION_ID,
          },
        },
      }
    );
    expect(result.current.data).toEqual(statusResponse);
  });

  it('throws on API error', async () => {
    mockGet.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Not found' },
    });

    const { result } = renderHook(
      () => useCompilationStatus(WORKSPACE_ID, COMPILATION_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useBulkDecisions ───────────────────────────────────────────────────

describe('useBulkDecisions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('submits bulk decisions via POST', async () => {
    const decisionsResponse: BulkDecisionsResponse = {
      accepted: 3,
      rejected: 1,
      total: 4,
    };
    mockPost.mockResolvedValueOnce({
      data: decisionsResponse,
      error: undefined,
    });

    const { result } = renderHook(
      () => useBulkDecisions(WORKSPACE_ID, COMPILATION_ID),
      { wrapper: createWrapper() }
    );

    const request: BulkDecisionsRequest = {
      decisions: [
        { line_item_id: 'li-001', action: 'accept' },
        { line_item_id: 'li-002', action: 'accept' },
        { line_item_id: 'li-003', action: 'accept' },
        {
          line_item_id: 'li-004',
          action: 'reject',
          note: 'Incorrect sector mapping',
        },
      ],
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions',
      expect.objectContaining({
        params: {
          path: {
            workspace_id: WORKSPACE_ID,
            compilation_id: COMPILATION_ID,
          },
        },
        body: request,
      })
    );
    expect(result.current.data).toEqual(decisionsResponse);
  });

  it('supports override_sector_code in decisions', async () => {
    const decisionsResponse: BulkDecisionsResponse = {
      accepted: 1,
      rejected: 0,
      total: 1,
    };
    mockPost.mockResolvedValueOnce({
      data: decisionsResponse,
      error: undefined,
    });

    const { result } = renderHook(
      () => useBulkDecisions(WORKSPACE_ID, COMPILATION_ID),
      { wrapper: createWrapper() }
    );

    const request: BulkDecisionsRequest = {
      decisions: [
        {
          line_item_id: 'li-001',
          action: 'accept',
          override_sector_code: 'S99',
        },
      ],
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions',
      expect.objectContaining({
        body: request,
      })
    );
  });

  it('throws on API error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Bad request' },
    });

    const { result } = renderHook(
      () => useBulkDecisions(WORKSPACE_ID, COMPILATION_ID),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      result.current.mutate({ decisions: [] });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useCompilationData ─────────────────────────────────────────────────

describe('useCompilationData', () => {
  it('returns undefined when cache is empty', () => {
    const queryClient = new QueryClient();
    const wrapper = createWrapper(queryClient);

    const { result } = renderHook(
      () => useCompilationData(COMPILATION_ID),
      { wrapper }
    );

    expect(result.current).toBeUndefined();
  });

  it('returns cached compilation data', () => {
    const queryClient = new QueryClient();
    const compileResponse: CompileResponse = {
      compilation_id: COMPILATION_ID,
      suggestions: [
        {
          line_item_id: 'li-001',
          sector_code: 'S01',
          confidence: 0.92,
          explanation: 'Construction sector',
        },
      ],
      high_confidence: 1,
      medium_confidence: 0,
      low_confidence: 0,
    };

    queryClient.setQueryData(['compilation', COMPILATION_ID], compileResponse);

    const wrapper = createWrapper(queryClient);

    const { result } = renderHook(
      () => useCompilationData(COMPILATION_ID),
      { wrapper }
    );

    expect(result.current).toEqual(compileResponse);
  });
});
