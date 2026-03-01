import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { GovernanceStatusDisplay } from '../status-display';
import type {
  GovernanceStatusResponse,
  BlockingReasonsResponse,
} from '@/lib/api/hooks/useGovernance';

// ── Mocks ────────────────────────────────────────────────────────────

let mockStatusData: GovernanceStatusResponse | undefined;
let mockStatusLoading = false;
let mockStatusError = false;

let mockBlockingData: BlockingReasonsResponse | undefined;

vi.mock('@/lib/api/hooks/useGovernance', () => ({
  useGovernanceStatus: () => ({
    data: mockStatusData,
    isLoading: mockStatusLoading,
    isError: mockStatusError,
  }),
  useBlockingReasons: () => ({
    data: mockBlockingData,
    isLoading: false,
    isError: false,
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
      createElement(GovernanceStatusDisplay, {
        workspaceId: props?.workspaceId ?? 'ws-001',
        runId: props?.runId ?? 'run-001',
      })
    )
  );
}

// ── Tests ────────────────────────────────────────────────────────────

describe('GovernanceStatusDisplay', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStatusData = undefined;
    mockStatusLoading = false;
    mockStatusError = false;
    mockBlockingData = undefined;
  });

  it('shows loading skeleton while fetching', () => {
    mockStatusLoading = true;
    renderDisplay();
    expect(screen.getByTestId('governance-loading')).toBeInTheDocument();
  });

  it('shows error message on fetch failure', () => {
    mockStatusError = true;
    renderDisplay();
    expect(
      screen.getByText(/failed to load governance status/i)
    ).toBeInTheDocument();
  });

  it('shows PASS badge when nff_passed is true', () => {
    mockStatusData = {
      run_id: 'run-001',
      claims_total: 5,
      claims_resolved: 5,
      claims_unresolved: 0,
      assumptions_total: 3,
      assumptions_approved: 3,
      nff_passed: true,
    };
    renderDisplay();
    expect(screen.getByText('PASS')).toBeInTheDocument();
  });

  it('shows BLOCKED badge when nff_passed is false', () => {
    mockStatusData = {
      run_id: 'run-001',
      claims_total: 5,
      claims_resolved: 3,
      claims_unresolved: 2,
      assumptions_total: 3,
      assumptions_approved: 1,
      nff_passed: false,
    };
    mockBlockingData = {
      run_id: 'run-001',
      blocking_reasons: [],
    };
    renderDisplay();
    expect(screen.getByText('BLOCKED')).toBeInTheDocument();
  });

  it('shows claims counts', () => {
    mockStatusData = {
      run_id: 'run-001',
      claims_total: 10,
      claims_resolved: 7,
      claims_unresolved: 3,
      assumptions_total: 4,
      assumptions_approved: 2,
      nff_passed: false,
    };
    mockBlockingData = {
      run_id: 'run-001',
      blocking_reasons: [],
    };
    renderDisplay();
    expect(screen.getByText('10')).toBeInTheDocument(); // total
    expect(screen.getByText('7')).toBeInTheDocument(); // resolved
    expect(screen.getByText('3')).toBeInTheDocument(); // unresolved
  });

  it('shows assumptions counts', () => {
    mockStatusData = {
      run_id: 'run-001',
      claims_total: 5,
      claims_resolved: 5,
      claims_unresolved: 0,
      assumptions_total: 6,
      assumptions_approved: 4,
      nff_passed: true,
    };
    renderDisplay();
    expect(screen.getByText('6')).toBeInTheDocument(); // total
    expect(screen.getByText('4')).toBeInTheDocument(); // approved
  });

  it('shows blocking reasons when nff_passed is false', () => {
    mockStatusData = {
      run_id: 'run-001',
      claims_total: 3,
      claims_resolved: 1,
      claims_unresolved: 2,
      assumptions_total: 2,
      assumptions_approved: 1,
      nff_passed: false,
    };
    mockBlockingData = {
      run_id: 'run-001',
      blocking_reasons: [
        {
          claim_id: 'claim-001',
          current_status: 'NEEDS_EVIDENCE',
          reason: 'Claim requires supporting evidence',
        },
        {
          claim_id: 'claim-002',
          current_status: 'EXTRACTED',
          reason: 'Claim not yet reviewed',
        },
      ],
    };
    renderDisplay();
    expect(
      screen.getByText('Claim requires supporting evidence')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Claim not yet reviewed')
    ).toBeInTheDocument();
  });

  it('does not show blocking reasons section when nff_passed is true', () => {
    mockStatusData = {
      run_id: 'run-001',
      claims_total: 5,
      claims_resolved: 5,
      claims_unresolved: 0,
      assumptions_total: 3,
      assumptions_approved: 3,
      nff_passed: true,
    };
    renderDisplay();
    expect(screen.queryByText(/blocking reasons/i)).not.toBeInTheDocument();
  });
});
