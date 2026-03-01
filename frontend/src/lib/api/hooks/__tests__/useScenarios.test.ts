import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import {
  useCreateScenario,
  useCompileScenario,
  useScenarioVersions,
  type CreateScenarioRequest,
  type CreateScenarioResponse,
  type ScenarioCompileRequest,
  type ScenarioCompileResponse,
  type VersionsResponse,
} from '../useScenarios';

const mockPost = vi.fn();
const mockGet = vi.fn();

vi.mock('../../client', () => ({
  api: {
    POST: (...args: unknown[]) => mockPost(...args),
    GET: (...args: unknown[]) => mockGet(...args),
  },
}));

const WORKSPACE_ID = 'ws-001';
const SCENARIO_ID = 'sc-001';

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

// ── useCreateScenario ─────────────────────────────────────────────────

describe('useCreateScenario', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to scenarios endpoint and returns scenario data', async () => {
    const response: CreateScenarioResponse = {
      scenario_spec_id: SCENARIO_ID,
      version: 1,
      name: 'Test Scenario',
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(() => useCreateScenario(WORKSPACE_ID), {
      wrapper: createWrapper(),
    });

    const request: CreateScenarioRequest = {
      name: 'Test Scenario',
      base_model_version_id: 'mv-001',
      base_year: 2020,
      start_year: 2025,
      end_year: 2030,
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/scenarios',
      expect.objectContaining({
        params: { path: { workspace_id: WORKSPACE_ID } },
        body: request,
      })
    );
    expect(result.current.data).toEqual(response);
  });

  it('throws on API error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Validation error' },
    });

    const { result } = renderHook(() => useCreateScenario(WORKSPACE_ID), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        name: 'Bad',
        base_model_version_id: 'mv-001',
        base_year: 2020,
        start_year: 2025,
        end_year: 2030,
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useCompileScenario ────────────────────────────────────────────────

describe('useCompileScenario', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls POST to compile endpoint with decisions and phasing', async () => {
    const response: ScenarioCompileResponse = {
      scenario_spec_id: SCENARIO_ID,
      version: 2,
      shock_items: [
        {
          shock_type: 'FinalDemandShock',
          sector_code: 'S01',
          value: 1000000,
          year: '2025',
        },
      ],
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useCompileScenario(WORKSPACE_ID, SCENARIO_ID),
      { wrapper: createWrapper() }
    );

    const request: ScenarioCompileRequest = {
      document_id: 'doc-001',
      decisions: [
        {
          line_item_id: 'li-001',
          final_sector_code: 'S01',
          decision_type: 'APPROVED',
          decided_by: '00000000-0000-7000-8000-000000000001',
          suggested_confidence: 0.92,
        },
        {
          line_item_id: 'li-002',
          final_sector_code: null,
          decision_type: 'EXCLUDED',
          decided_by: '00000000-0000-7000-8000-000000000001',
          suggested_confidence: 0.3,
        },
      ],
      phasing: { '2025': 0.5, '2026': 0.5 },
      default_domestic_share: 0.65,
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/compile',
      expect.objectContaining({
        params: {
          path: {
            workspace_id: WORKSPACE_ID,
            scenario_id: SCENARIO_ID,
          },
        },
        body: request,
      })
    );
    expect(result.current.data).toEqual(response);
  });

  it('includes EXCLUDED decisions for rejected items', async () => {
    const response: ScenarioCompileResponse = {
      scenario_spec_id: SCENARIO_ID,
      version: 2,
      shock_items: [],
    };
    mockPost.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useCompileScenario(WORKSPACE_ID, SCENARIO_ID),
      { wrapper: createWrapper() }
    );

    const request: ScenarioCompileRequest = {
      decisions: [
        {
          line_item_id: 'li-001',
          final_sector_code: null,
          decision_type: 'EXCLUDED',
          decided_by: '00000000-0000-7000-8000-000000000001',
        },
      ],
      phasing: { '2025': 1.0 },
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Verify rejected item included with EXCLUDED type and null sector
    const body = mockPost.mock.calls[0][1].body;
    expect(body.decisions[0].decision_type).toBe('EXCLUDED');
    expect(body.decisions[0].final_sector_code).toBeNull();
  });

  it('throws on API error', async () => {
    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Compile failed' },
    });

    const { result } = renderHook(
      () => useCompileScenario(WORKSPACE_ID, SCENARIO_ID),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      result.current.mutate({
        decisions: [],
        phasing: { '2025': 1.0 },
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ── useScenarioVersions ───────────────────────────────────────────────

describe('useScenarioVersions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches scenario versions', async () => {
    const response: VersionsResponse = {
      versions: [
        { version: 1, updated_at: '2026-01-15T10:00:00Z' },
        { version: 2, updated_at: '2026-01-16T12:00:00Z' },
      ],
    };
    mockGet.mockResolvedValueOnce({ data: response, error: undefined });

    const { result } = renderHook(
      () => useScenarioVersions(WORKSPACE_ID, SCENARIO_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockGet).toHaveBeenCalledWith(
      '/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/versions',
      {
        params: {
          path: {
            workspace_id: WORKSPACE_ID,
            scenario_id: SCENARIO_ID,
          },
        },
      }
    );
    expect(result.current.data?.versions).toHaveLength(2);
  });

  it('throws on API error', async () => {
    mockGet.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Not found' },
    });

    const { result } = renderHook(
      () => useScenarioVersions(WORKSPACE_ID, SCENARIO_ID),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
