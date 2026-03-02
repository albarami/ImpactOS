import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import {
  useUploadDocument,
  useExtractDocument,
  useJobStatus,
  useLineItems,
} from '../useDocuments';

const mockPost = vi.fn();
const mockGet = vi.fn();

vi.mock('../../client', () => ({
  api: {
    POST: (...args: unknown[]) => mockPost(...args),
    GET: (...args: unknown[]) => mockGet(...args),
  },
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const WORKSPACE_ID = 'ws-001';

describe('useUploadDocument', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('uploads a document via POST with multipart form-data', async () => {
    const uploadResponse = {
      doc_id: 'doc-123',
      status: 'uploaded',
      hash_sha256: 'abc123hash',
    };
    mockPost.mockResolvedValueOnce({ data: uploadResponse, error: undefined });

    const { result } = renderHook(() => useUploadDocument(WORKSPACE_ID), {
      wrapper: createWrapper(),
    });

    const formData = new FormData();
    formData.append('file', new Blob(['test']), 'test.pdf');
    formData.append('doc_type', 'BOQ');
    formData.append('source_type', 'CLIENT');
    formData.append('classification', 'INTERNAL');
    formData.append('language', 'en');
    formData.append('uploaded_by', '00000000-0000-7000-8000-000000000001');

    await act(async () => {
      result.current.mutate(formData);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/documents',
      expect.objectContaining({
        params: { path: { workspace_id: WORKSPACE_ID } },
      })
    );
    expect(result.current.data).toEqual(uploadResponse);
  });

  it('throws on API error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Bad request' },
    });

    const { result } = renderHook(() => useUploadDocument(WORKSPACE_ID), {
      wrapper: createWrapper(),
    });

    const formData = new FormData();
    formData.append('file', new Blob(['test']), 'test.pdf');

    await act(async () => {
      result.current.mutate(formData);
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe('useExtractDocument', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('triggers extraction via POST', async () => {
    const extractResponse = { job_id: 'job-456', status: 'QUEUED' };
    mockPost.mockResolvedValueOnce({ data: extractResponse, error: undefined });

    const { result } = renderHook(
      () => useExtractDocument(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      result.current.mutate('doc-123');
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/documents/{doc_id}/extract',
      {
        params: { path: { workspace_id: WORKSPACE_ID, doc_id: 'doc-123' } },
        body: {
          extract_tables: true,
          extract_line_items: true,
          language_hint: 'en',
        },
      }
    );
    expect(result.current.data).toEqual(extractResponse);
  });

  it('throws on API error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Not found' },
    });

    const { result } = renderHook(
      () => useExtractDocument(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      result.current.mutate('doc-missing');
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe('useJobStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches job status when jobId is provided', async () => {
    const jobResponse = {
      job_id: 'job-456',
      doc_id: 'doc-123',
      status: 'RUNNING',
      error_message: null,
    };
    mockGet.mockResolvedValueOnce({ data: jobResponse, error: undefined });

    const { result } = renderHook(
      () => useJobStatus(WORKSPACE_ID, 'job-456'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockGet).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/jobs/{job_id}',
      {
        params: { path: { workspace_id: WORKSPACE_ID, job_id: 'job-456' } },
      }
    );
    expect(result.current.data).toEqual(jobResponse);
  });

  it('is disabled when jobId is null', () => {
    const { result } = renderHook(
      () => useJobStatus(WORKSPACE_ID, null),
      { wrapper: createWrapper() }
    );

    expect(result.current.fetchStatus).toBe('idle');
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('stops polling when status is COMPLETED', async () => {
    const completedResponse = {
      job_id: 'job-456',
      doc_id: 'doc-123',
      status: 'COMPLETED',
      error_message: null,
    };
    mockGet.mockResolvedValue({ data: completedResponse, error: undefined });

    const { result } = renderHook(
      () => useJobStatus(WORKSPACE_ID, 'job-456'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.data?.status).toBe('COMPLETED');
    });
  });

  it('stops polling when status is FAILED', async () => {
    const failedResponse = {
      job_id: 'job-456',
      doc_id: 'doc-123',
      status: 'FAILED',
      error_message: 'Extraction failed',
    };
    mockGet.mockResolvedValue({ data: failedResponse, error: undefined });

    const { result } = renderHook(
      () => useJobStatus(WORKSPACE_ID, 'job-456'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.data?.status).toBe('FAILED');
    });
  });
});

describe('useLineItems', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches line items for a document', async () => {
    const lineItemsResponse = {
      items: [
        {
          line_item_id: 'li-001',
          doc_id: 'doc-123',
          raw_text: 'Steel rebar',
          description: 'Steel rebar for foundations',
          quantity: 100,
          unit: 'ton',
          unit_price: 2500,
          total_value: 250000,
          currency_code: 'SAR',
          year_or_phase: '2026',
          vendor: 'SteelCo',
          category_code: 'C01',
          page_ref: 3,
          evidence_snippet_ids: ['ev-001'],
          completeness_score: 0.95,
          created_at: '2026-01-15T10:00:00Z',
        },
      ],
    };
    mockGet.mockResolvedValueOnce({
      data: lineItemsResponse,
      error: undefined,
    });

    const { result } = renderHook(
      () => useLineItems(WORKSPACE_ID, 'doc-123'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockGet).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/documents/{doc_id}/line-items',
      {
        params: { path: { workspace_id: WORKSPACE_ID, doc_id: 'doc-123' } },
      }
    );
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].description).toBe(
      'Steel rebar for foundations'
    );
  });

  it('throws on API error', async () => {
    mockGet.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Not found' },
    });

    const { result } = renderHook(
      () => useLineItems(WORKSPACE_ID, 'doc-missing'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
