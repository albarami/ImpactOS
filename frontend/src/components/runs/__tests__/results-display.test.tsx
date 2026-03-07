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
    // 1500000 + 750000 = 2250000 (may appear in headline and executive summary)
    const totalImpactEl = screen.getByTestId('total-impact-value');
    expect(totalImpactEl).toHaveTextContent(/2,250,000/);
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

  // ── P6-3: Currency Label ────────────────────────────────────────────

  it('shows SAR currency label with total impact (P6-3)', () => {
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
    const impactEl = screen.getByTestId('total-impact-value');
    expect(impactEl).toBeInTheDocument();
    expect(impactEl).toHaveTextContent(/SAR/);
  });

  // ── P6-2: Executive Summary ─────────────────────────────────────────

  it('shows executive summary section when multiple metric types present (P6-2)', () => {
    mockRunData = {
      run_id: 'run-001',
      result_sets: [
        {
          result_id: 'rs-001',
          metric_type: 'total_output',
          values: { S01: 1500000, S02: 750000 },
        },
        {
          result_id: 'rs-002',
          metric_type: 'value_added',
          values: { S01: 900000, S02: 450000 },
        },
        {
          result_id: 'rs-003',
          metric_type: 'employment',
          values: { S01: 500, S02: 300 },
        },
      ],
      snapshot: { run_id: 'run-001', model_version_id: 'mv-001' },
    };
    renderDisplay();
    const summary = screen.getByTestId('executive-summary');
    expect(summary).toBeInTheDocument();
  });

  it('shows GDP impact in executive summary (P6-2)', () => {
    mockRunData = {
      run_id: 'run-001',
      result_sets: [
        {
          result_id: 'rs-001',
          metric_type: 'value_added',
          values: { S01: 900000, S02: 450000 },
        },
      ],
      snapshot: { run_id: 'run-001', model_version_id: 'mv-001' },
    };
    renderDisplay();
    // GDP Impact label should appear
    expect(screen.getByText(/GDP Impact/i)).toBeInTheDocument();
    // 900000 + 450000 = 1350000 (appears in both headline and executive summary)
    const matches = screen.getAllByText(/1,350,000/);
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('shows total jobs in executive summary (P6-2)', () => {
    mockRunData = {
      run_id: 'run-001',
      result_sets: [
        {
          result_id: 'rs-001',
          metric_type: 'employment',
          values: { S01: 500, S02: 300 },
        },
      ],
      snapshot: { run_id: 'run-001', model_version_id: 'mv-001' },
    };
    renderDisplay();
    // Jobs Created label should appear (in executive summary and/or workforce panel)
    const jobsLabels = screen.getAllByText(/Jobs Created/i);
    expect(jobsLabels.length).toBeGreaterThanOrEqual(1);
    // 500 + 300 = 800 (appears in headline and executive summary)
    const matches = screen.getAllByText('800');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  // ── P6-3: Denomination from snapshot ──────────────────────────────

  it('shows denomination scale from snapshot (P6-3)', () => {
    mockRunData = {
      run_id: 'run-001',
      result_sets: [
        {
          result_id: 'rs-001',
          metric_type: 'total_output',
          values: { S01: 1500000 },
        },
      ],
      snapshot: {
        run_id: 'run-001',
        model_version_id: 'mv-001',
        model_denomination: 'SAR_MILLIONS',
      },
    };
    renderDisplay();
    // Should show denomination scale info, not just "SAR"
    const impactEl = screen.getByTestId('total-impact-value');
    expect(impactEl).toHaveTextContent(/Millions/i);
  });

  it('total impact only sums total_output, not employment or imports (P6-3)', () => {
    mockRunData = {
      run_id: 'run-001',
      result_sets: [
        {
          result_id: 'rs-001',
          metric_type: 'total_output',
          values: { S01: 1000000, S02: 500000 },
        },
        {
          result_id: 'rs-002',
          metric_type: 'employment',
          values: { S01: 500, S02: 300 },
        },
        {
          result_id: 'rs-003',
          metric_type: 'imports',
          values: { S01: 200000, S02: 100000 },
        },
      ],
      snapshot: {
        run_id: 'run-001',
        model_version_id: 'mv-001',
        model_denomination: 'SAR_MILLIONS',
      },
    };
    renderDisplay();
    const impactEl = screen.getByTestId('total-impact-value');
    // Total impact = 1,000,000 + 500,000 = 1,500,000 (only total_output)
    // NOT 1,000,000 + 500,000 + 500 + 300 + 200,000 + 100,000
    expect(impactEl).toHaveTextContent(/1,500,000/);
  });
});
