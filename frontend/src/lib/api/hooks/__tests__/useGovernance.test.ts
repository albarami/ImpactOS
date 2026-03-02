import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import {
  useGovernanceStatus,
  useBlockingReasons,
  useExtractClaims,
  useNffCheck,
  useCreateAssumption,
  useApproveAssumption,
  type GovernanceStatusResponse,
  type BlockingReasonsResponse,
  type ExtractClaimsRequest,
  type ExtractClaimsResponse,
  type NffCheckRequest,
  type NffCheckResponse,
  type CreateAssumptionRequest,
  type CreateAssumptionResponse,
  type ApproveAssumptionRequest,
  type ApproveAssumptionResponse,
} from '../useGovernance';

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

// ── useGovernanceStatus ─────────────────────────────────────────────

describe('useGovernanceStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches governance status by run_id', async () => {
    const response: GovernanceStatusResponse = {
      run_id: RUN_ID,
      claims_total: 5,
      claims_resolved: 3,
      claims_unresolved: 2,
      assumptions_total: 4,
      assumptions_approved: 2,
      nff_passed: false,
    };
    mockGet.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useGovernanceStatus(WORKSPACE_ID, RUN_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockGet).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/governance/status/{run_id}',
      {
        params: {
          path: {
            workspace_id: WORKSPACE_ID,
            run_id: RUN_ID,
          },
        },
      }
    );
    expect(result.current.data).toEqual(response);
  });

  it('is disabled when runId is empty', () => {
    const { result } = renderHook(
      () => useGovernanceStatus(WORKSPACE_ID, ''),
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
      () => useGovernanceStatus(WORKSPACE_ID, RUN_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useBlockingReasons ──────────────────────────────────────────────

describe('useBlockingReasons', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches blocking reasons by run_id', async () => {
    const response: BlockingReasonsResponse = {
      run_id: RUN_ID,
      blocking_reasons: [
        {
          claim_id: 'claim-001',
          current_status: 'NEEDS_EVIDENCE',
          reason: 'Claim requires supporting evidence',
        },
      ],
    };
    mockGet.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useBlockingReasons(WORKSPACE_ID, RUN_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockGet).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/governance/blocking-reasons/{run_id}',
      {
        params: {
          path: {
            workspace_id: WORKSPACE_ID,
            run_id: RUN_ID,
          },
        },
      }
    );
    expect(result.current.data?.blocking_reasons).toHaveLength(1);
  });

  it('is disabled when runId is empty', () => {
    const { result } = renderHook(
      () => useBlockingReasons(WORKSPACE_ID, ''),
      { wrapper: createWrapper() }
    );

    expect(result.current.fetchStatus).toBe('idle');
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('throws on API error', async () => {
    mockGet.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Server error' },
    });

    const { result } = renderHook(
      () => useBlockingReasons(WORKSPACE_ID, RUN_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useExtractClaims ────────────────────────────────────────────────

describe('useExtractClaims', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to extract claims endpoint', async () => {
    const response: ExtractClaimsResponse = {
      claims: [
        {
          claim_id: 'claim-001',
          text: 'GDP will grow by 5%',
          claim_type: 'MODEL',
          status: 'EXTRACTED',
        },
      ],
      total: 1,
      needs_evidence_count: 0,
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useExtractClaims(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    const request: ExtractClaimsRequest = {
      draft_text: 'GDP will grow by 5% due to infrastructure investment.',
      run_id: RUN_ID,
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/governance/claims/extract',
      expect.objectContaining({
        params: { path: { workspace_id: WORKSPACE_ID } },
        body: request,
      })
    );
    expect(result.current.data?.claims).toHaveLength(1);
  });

  it('throws on API error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Extraction failed' },
    });

    const { result } = renderHook(
      () => useExtractClaims(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      result.current.mutate({
        draft_text: 'test text',
        run_id: RUN_ID,
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useNffCheck ─────────────────────────────────────────────────────

describe('useNffCheck', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to nff check endpoint', async () => {
    const response: NffCheckResponse = {
      passed: true,
      total_claims: 3,
      blocking_reasons: [],
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useNffCheck(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    const request: NffCheckRequest = {
      claim_ids: ['claim-001', 'claim-002', 'claim-003'],
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/governance/nff/check',
      expect.objectContaining({
        params: { path: { workspace_id: WORKSPACE_ID } },
        body: request,
      })
    );
    expect(result.current.data?.passed).toBe(true);
  });

  it('returns blocking reasons when check fails', async () => {
    const response: NffCheckResponse = {
      passed: false,
      total_claims: 2,
      blocking_reasons: [
        {
          claim_id: 'claim-001',
          current_status: 'NEEDS_EVIDENCE',
          reason: 'No evidence attached',
        },
      ],
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useNffCheck(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      result.current.mutate({ claim_ids: ['claim-001', 'claim-002'] });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.passed).toBe(false);
    expect(result.current.data?.blocking_reasons).toHaveLength(1);
  });
});

// ── useCreateAssumption ─────────────────────────────────────────────

describe('useCreateAssumption', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to create assumption', async () => {
    const response: CreateAssumptionResponse = {
      assumption_id: 'assum-001',
      status: 'DRAFT',
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useCreateAssumption(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    const request: CreateAssumptionRequest = {
      type: 'IMPORT_SHARE',
      value: 0.35,
      units: 'ratio',
      justification: 'Based on 2024 import data',
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/governance/assumptions',
      expect.objectContaining({
        params: { path: { workspace_id: WORKSPACE_ID } },
        body: request,
      })
    );
    expect(result.current.data?.assumption_id).toBe('assum-001');
  });

  it('throws on API error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Validation error' },
    });

    const { result } = renderHook(
      () => useCreateAssumption(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      result.current.mutate({
        type: 'PHASING',
        value: 0.5,
        units: '%',
        justification: 'test',
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useApproveAssumption ────────────────────────────────────────────

describe('useApproveAssumption', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to approve assumption', async () => {
    const response: ApproveAssumptionResponse = {
      assumption_id: 'assum-001',
      status: 'APPROVED',
      range_min: 0.3,
      range_max: 0.4,
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useApproveAssumption(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    const request: ApproveAssumptionRequest = {
      assumption_id: 'assum-001',
      range_min: 0.3,
      range_max: 0.4,
      actor: '00000000-0000-7000-8000-000000000001',
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/governance/assumptions/{assumption_id}/approve',
      expect.objectContaining({
        params: {
          path: {
            workspace_id: WORKSPACE_ID,
            assumption_id: 'assum-001',
          },
        },
        body: {
          range_min: 0.3,
          range_max: 0.4,
          actor: '00000000-0000-7000-8000-000000000001',
        },
      })
    );
    expect(result.current.data?.status).toBe('APPROVED');
  });

  it('throws on API error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Not found' },
    });

    const { result } = renderHook(
      () => useApproveAssumption(WORKSPACE_ID),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      result.current.mutate({
        assumption_id: 'assum-bad',
        range_min: 0.1,
        range_max: 0.2,
        actor: '00000000-0000-7000-8000-000000000001',
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
