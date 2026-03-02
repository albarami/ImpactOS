import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { ResultsDisplay } from '../results-display';
import type { RunResponse } from '@/lib/api/hooks/useRuns';

// ── Mocks ────────────────────────────────────────────────────────────

let mockRunData: RunResponse | undefined;
let mockIsLoading = false;
let mockIsError = false;

vi.mock('@/lib/api/hooks/useRuns', () => ({
  useRunResults: () => ({
    data: mockRunData,
    isLoading: mockIsLoading,
    isError: mockIsError,
  }),
}));

// ── Helpers ──────────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function renderDisplay(props?: { workspaceId?: string; runId?: string }) {
  return render(
    createElement(
      createWrapper(),
      null,
      createElement(ResultsDisplay, {
        workspaceId: props?.workspaceId ?? 'ws-001',
        runId: props?.runId ?? 'run-001',
      })
    )
  );
}

// ── Tests ────────────────────────────────────────────────────────────

describe('ResultsDisplay', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRunData = undefined;
    mockIsLoading = false;
    mockIsError = false;
  });

  it('shows loading skeleton while fetching', () => {
    mockIsLoading = true;
    renderDisplay();
    expect(screen.getByTestId('results-loading')).toBeInTheDocument();
  });

  it('shows error message on fetch failure', () => {
    mockIsError = true;
    renderDisplay();
    expect(screen.getByText(/failed to load run results/i)).toBeInTheDocument();
  });

  it('shows run ID when data loads', () => {
    mockRunData = {
      run_id: 'run-001',
      result_sets: [
        {
          result_id: 'rs-001',
          metric_type: 'gross_output',
          values: { S01: 1500000, S02: 750000 },
        },
      ],
      snapshot: { run_id: 'run-001', model_version_id: 'mv-001' },
    };
    renderDisplay();
    expect(screen.getByText(/run-001/i)).toBeInTheDocument();
  });

  it('shows headline card with total impact', () => {
    mockRunData = {
      run_id: 'run-001',
      result_sets: [
        {
          result_id: 'rs-001',
          metric_type: 'gross_output',
          values: { S01: 1500000, S02: 750000 },
        },
      ],
      snapshot: { run_id: 'run-001', model_version_id: 'mv-001' },
    };
    renderDisplay();
    // Total impact = sum of all values across all result sets
    // 1500000 + 750000 = 2250000
    expect(screen.getByText(/2,250,000/)).toBeInTheDocument();
  });

  it('shows result sets table with metric types', () => {
    mockRunData = {
      run_id: 'run-001',
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
      snapshot: { run_id: 'run-001', model_version_id: 'mv-001' },
    };
    renderDisplay();
    expect(screen.getByText('gross_output')).toBeInTheDocument();
    expect(screen.getByText('value_added')).toBeInTheDocument();
  });

  it('shows sector values in result sets table', () => {
    mockRunData = {
      run_id: 'run-001',
      result_sets: [
        {
          result_id: 'rs-001',
          metric_type: 'gross_output',
          values: { S01: 1500000 },
        },
      ],
      snapshot: { run_id: 'run-001', model_version_id: 'mv-001' },
    };
    renderDisplay();
    expect(screen.getByText('S01')).toBeInTheDocument();
    // Value appears in both headline total and table cell
    const valueElements = screen.getAllByText('1,500,000');
    expect(valueElements.length).toBeGreaterThanOrEqual(1);
  });

  it('shows model version from snapshot', () => {
    mockRunData = {
      run_id: 'run-001',
      result_sets: [],
      snapshot: { run_id: 'run-001', model_version_id: 'mv-001' },
    };
    renderDisplay();
    expect(screen.getByText(/mv-001/)).toBeInTheDocument();
  });
});
