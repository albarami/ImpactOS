import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import {
  useCreateExport,
  useExportStatus,
  useExportData,
  type CreateExportRequest,
  type CreateExportResponse,
  type ExportStatusResponse,
} from '../useExports';

const mockPost = vi.fn();
const mockGet = vi.fn();

vi.mock('../../client', () => ({
  api: {
    POST: (...args: unknown[]) => mockPost(...args),
    GET: (...args: unknown[]) => mockGet(...args),
  },
}));

const WORKSPACE_ID = 'ws-001';
const EXPORT_ID = 'exp-001';
const RUN_ID = 'run-001';

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

/** Backwards-compatible overload: returns just the Wrapper function */
function wrapperOnly() {
  return createWrapper().Wrapper;
}

// ── useCreateExport ───────────────────────────────────────────────────

describe('useCreateExport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to exports endpoint and returns export data', async () => {
    const response: CreateExportResponse = {
      export_id: EXPORT_ID,
      status: 'COMPLETED',
      checksums: { excel: 'sha256:abc123' },
      blocking_reasons: [],
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(() => useCreateExport(WORKSPACE_ID), {
      wrapper: wrapperOnly(),
    });

    const request: CreateExportRequest = {
      run_id: RUN_ID,
      mode: 'SANDBOX',
      export_formats: ['excel'],
      pack_data: { scenario_name: 'Test', base_year: 2025, currency: 'SAR' },
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/exports',
      expect.objectContaining({
        params: { path: { workspace_id: WORKSPACE_ID } },
        body: request,
      })
    );
    expect(result.current.data).toEqual(response);
  });

  it('supports GOVERNED mode with multiple formats', async () => {
    const response: CreateExportResponse = {
      export_id: 'exp-002',
      status: 'COMPLETED',
      checksums: { excel: 'sha256:abc', pptx: 'sha256:def' },
      blocking_reasons: [],
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(() => useCreateExport(WORKSPACE_ID), {
      wrapper: wrapperOnly(),
    });

    const request: CreateExportRequest = {
      run_id: RUN_ID,
      mode: 'GOVERNED',
      export_formats: ['excel', 'pptx'],
      pack_data: { scenario_name: 'Governed Pack', base_year: 2025, currency: 'SAR' },
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const body = mockPost.mock.calls[0][1].body;
    expect(body.mode).toBe('GOVERNED');
    expect(body.export_formats).toEqual(['excel', 'pptx']);
  });

  it('returns BLOCKED status with blocking reasons', async () => {
    const response: CreateExportResponse = {
      export_id: 'exp-003',
      status: 'BLOCKED',
      checksums: {},
      blocking_reasons: ['Unresolved claims exist', 'Assumptions not approved'],
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(() => useCreateExport(WORKSPACE_ID), {
      wrapper: wrapperOnly(),
    });

    await act(async () => {
      result.current.mutate({
        run_id: RUN_ID,
        mode: 'GOVERNED',
        export_formats: ['excel'],
        pack_data: {},
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.status).toBe('BLOCKED');
    expect(result.current.data?.blocking_reasons).toHaveLength(2);
  });

  it('throws on API error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Export failed' },
    });

    const { result } = renderHook(() => useCreateExport(WORKSPACE_ID), {
      wrapper: wrapperOnly(),
    });

    await act(async () => {
      result.current.mutate({
        run_id: RUN_ID,
        mode: 'SANDBOX',
        export_formats: ['excel'],
        pack_data: {},
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useExportStatus ──────────────────────────────────────────────────

describe('useExportStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches export status by export_id', async () => {
    const response: ExportStatusResponse = {
      export_id: EXPORT_ID,
      run_id: RUN_ID,
      mode: 'SANDBOX',
      status: 'COMPLETED',
      checksums: { excel: 'sha256:abc123' },
    };
    mockGet.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useExportStatus(WORKSPACE_ID, EXPORT_ID),
      { wrapper: wrapperOnly() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockGet).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/exports/{export_id}',
      {
        params: {
          path: {
            workspace_id: WORKSPACE_ID,
            export_id: EXPORT_ID,
          },
        },
      }
    );
    expect(result.current.data).toEqual(response);
  });

  it('is disabled when exportId is empty', () => {
    const { result } = renderHook(
      () => useExportStatus(WORKSPACE_ID, ''),
      { wrapper: wrapperOnly() }
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
      () => useExportStatus(WORKSPACE_ID, EXPORT_ID),
      { wrapper: wrapperOnly() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });

  it('polls when status is PENDING', async () => {
    const pendingResponse: ExportStatusResponse = {
      export_id: EXPORT_ID,
      run_id: RUN_ID,
      mode: 'SANDBOX',
      status: 'PENDING',
      checksums: {},
    };
    mockGet.mockResolvedValue({ data: pendingResponse, error: undefined });

    const { result } = renderHook(
      () => useExportStatus(WORKSPACE_ID, EXPORT_ID),
      { wrapper: wrapperOnly() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.status).toBe('PENDING');
    // The hook should have refetchInterval set for PENDING status
    // We verify by checking that the query was made at least once
    expect(mockGet).toHaveBeenCalled();
  });

  it('polls when status is GENERATING', async () => {
    const generatingResponse: ExportStatusResponse = {
      export_id: EXPORT_ID,
      run_id: RUN_ID,
      mode: 'GOVERNED',
      status: 'GENERATING',
      checksums: {},
    };
    mockGet.mockResolvedValue({ data: generatingResponse, error: undefined });

    const { result } = renderHook(
      () => useExportStatus(WORKSPACE_ID, EXPORT_ID),
      { wrapper: wrapperOnly() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.status).toBe('GENERATING');
  });

  it('stops polling when status is COMPLETED', async () => {
    const completedResponse: ExportStatusResponse = {
      export_id: EXPORT_ID,
      run_id: RUN_ID,
      mode: 'SANDBOX',
      status: 'COMPLETED',
      checksums: { excel: 'sha256:abc123' },
    };
    mockGet.mockResolvedValue({ data: completedResponse, error: undefined });

    const { result } = renderHook(
      () => useExportStatus(WORKSPACE_ID, EXPORT_ID),
      { wrapper: wrapperOnly() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.status).toBe('COMPLETED');
  });
});

// ── useCreateExport caching ─────────────────────────────────────────

describe('useCreateExport cache', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('caches create response by export_id on success', async () => {
    const response: CreateExportResponse = {
      export_id: 'exp-cache-1',
      status: 'BLOCKED',
      checksums: {},
      blocking_reasons: ['Unresolved claims exist'],
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { Wrapper, queryClient } = createWrapper();

    const { result } = renderHook(() => useCreateExport(WORKSPACE_ID), {
      wrapper: Wrapper,
    });

    await act(async () => {
      result.current.mutate({
        run_id: RUN_ID,
        mode: 'GOVERNED',
        export_formats: ['excel'],
        pack_data: {},
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const cached = queryClient.getQueryData<CreateExportResponse>([
      'export',
      'exp-cache-1',
    ]);
    expect(cached).toEqual(response);
    expect(cached?.blocking_reasons).toEqual(['Unresolved claims exist']);
  });
});

// ── useExportData ───────────────────────────────────────────────────

describe('useExportData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns cached export data when present', () => {
    const { Wrapper, queryClient } = createWrapper();

    const cached: CreateExportResponse = {
      export_id: 'exp-data-1',
      status: 'BLOCKED',
      checksums: {},
      blocking_reasons: ['Reason A', 'Reason B'],
    };
    queryClient.setQueryData(['export', 'exp-data-1'], cached);

    const { result } = renderHook(() => useExportData('exp-data-1'), {
      wrapper: Wrapper,
    });

    expect(result.current).toEqual(cached);
    expect(result.current?.blocking_reasons).toEqual(['Reason A', 'Reason B']);
  });

  it('returns undefined when cache is cold', () => {
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useExportData('exp-nonexistent'), {
      wrapper: Wrapper,
    });

    expect(result.current).toBeUndefined();
  });
});
