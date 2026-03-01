import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { ClaimExtraction } from '../claim-extraction';
import type { ExtractClaimsResponse } from '@/lib/api/hooks/useGovernance';

// ── Mocks ────────────────────────────────────────────────────────────

const mockMutateAsync = vi.fn();
let mockIsPending = false;

vi.mock('@/lib/api/hooks/useGovernance', () => ({
  useExtractClaims: () => ({
    mutateAsync: mockMutateAsync,
    isPending: mockIsPending,
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

function renderForm(props?: { workspaceId?: string; runId?: string }) {
  return render(
    createElement(
      createWrapper(),
      null,
      createElement(ClaimExtraction, {
        workspaceId: props?.workspaceId ?? 'ws-001',
        runId: props?.runId ?? 'run-001',
      })
    )
  );
}

// ── Tests ────────────────────────────────────────────────────────────

describe('ClaimExtraction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsPending = false;
  });

  it('renders draft text textarea', () => {
    renderForm();
    expect(screen.getByLabelText(/draft text/i)).toBeInTheDocument();
  });

  it('renders run ID info', () => {
    renderForm({ runId: 'run-042' });
    expect(screen.getByText(/run-042/)).toBeInTheDocument();
  });

  it('renders extract claims button', () => {
    renderForm();
    expect(
      screen.getByRole('button', { name: /extract claims/i })
    ).toBeInTheDocument();
  });

  it('requires draft text to submit', async () => {
    const user = userEvent.setup();
    renderForm();

    const btn = screen.getByRole('button', { name: /extract claims/i });
    await user.click(btn);

    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it('submits extraction and shows results table', async () => {
    const user = userEvent.setup();
    const response: ExtractClaimsResponse = {
      claims: [
        {
          claim_id: 'claim-001',
          text: 'GDP will grow by 5% annually',
          claim_type: 'MODEL',
          status: 'EXTRACTED',
        },
        {
          claim_id: 'claim-002',
          text: 'Import share is 35%',
          claim_type: 'ASSUMPTION',
          status: 'NEEDS_EVIDENCE',
        },
      ],
      total: 2,
      needs_evidence_count: 1,
    };
    mockMutateAsync.mockResolvedValueOnce(response);

    renderForm();

    const textarea = screen.getByLabelText(/draft text/i);
    await user.type(textarea, 'GDP will grow by 5% annually. Import share is 35%.');

    const btn = screen.getByRole('button', { name: /extract claims/i });
    await user.click(btn);

    expect(mockMutateAsync).toHaveBeenCalledWith({
      draft_text: 'GDP will grow by 5% annually. Import share is 35%.',
      run_id: 'run-001',
    });

    // Claims table should appear — use getAllByText since text also in textarea
    const gdpMatches = await screen.findAllByText(/GDP will grow/);
    expect(gdpMatches.length).toBeGreaterThanOrEqual(1);
    const importMatches = screen.getAllByText(/Import share/);
    expect(importMatches.length).toBeGreaterThanOrEqual(1);

    // Type badges
    expect(screen.getByText('MODEL')).toBeInTheDocument();
    expect(screen.getByText('ASSUMPTION')).toBeInTheDocument();

    // Status
    expect(screen.getByText('EXTRACTED')).toBeInTheDocument();
    expect(screen.getByText('NEEDS_EVIDENCE')).toBeInTheDocument();
  });

  it('shows error message on extraction failure', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockRejectedValueOnce(new Error('Extraction failed'));

    renderForm();

    const textarea = screen.getByLabelText(/draft text/i);
    await user.type(textarea, 'Some draft text');

    const btn = screen.getByRole('button', { name: /extract claims/i });
    await user.click(btn);

    expect(
      await screen.findByText(/extraction failed/i)
    ).toBeInTheDocument();
  });

  it('shows total and needs_evidence_count summary', async () => {
    const user = userEvent.setup();
    const response: ExtractClaimsResponse = {
      claims: [
        {
          claim_id: 'claim-001',
          text: 'Test claim',
          claim_type: 'SOURCE_FACT',
          status: 'EXTRACTED',
        },
      ],
      total: 1,
      needs_evidence_count: 0,
    };
    mockMutateAsync.mockResolvedValueOnce(response);

    renderForm();

    await user.type(screen.getByLabelText(/draft text/i), 'test');
    await user.click(screen.getByRole('button', { name: /extract claims/i }));

    expect(await screen.findByText(/1 claim/i)).toBeInTheDocument();
  });
});
