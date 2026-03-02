import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { BulkControls } from '../bulk-controls';
import type { Suggestion, DecisionMap } from '../decision-table';

// ── Mocks ────────────────────────────────────────────────────────────

const mockMutateAsync = vi.fn();

vi.mock('@/lib/api/hooks/useCompiler', () => ({
  useBulkDecisions: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// ── Test data ────────────────────────────────────────────────────────

const SUGGESTIONS: Suggestion[] = [
  {
    line_item_id: 'li-001',
    sector_code: 'S01',
    confidence: 0.92,
    explanation: 'Construction',
  },
  {
    line_item_id: 'li-002',
    sector_code: 'S05',
    confidence: 0.65,
    explanation: 'Manufacturing',
  },
  {
    line_item_id: 'li-003',
    sector_code: 'S12',
    confidence: 0.3,
    explanation: 'Services',
  },
];

// ── Helpers ──────────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function renderControls(decisions?: DecisionMap) {
  const defaultDecisions: DecisionMap = {
    'li-001': { action: 'accept' },
    'li-002': { action: 'reject' },
    'li-003': { action: 'pending' },
  };

  return render(
    createElement(
      createWrapper(),
      null,
      createElement(BulkControls, {
        workspaceId: 'ws-001',
        compilationId: 'comp-001',
        suggestions: SUGGESTIONS,
        decisions: decisions ?? defaultDecisions,
        onSubmitted: vi.fn(),
      })
    )
  );
}

// ── Tests ────────────────────────────────────────────────────────────

describe('BulkControls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Accept All button', () => {
    renderControls();
    expect(
      screen.getByRole('button', { name: /accept all/i })
    ).toBeInTheDocument();
  });

  it('renders Reject All button', () => {
    renderControls();
    expect(
      screen.getByRole('button', { name: /reject all/i })
    ).toBeInTheDocument();
  });

  it('renders Submit Decisions button', () => {
    renderControls();
    expect(
      screen.getByRole('button', { name: /submit decisions/i })
    ).toBeInTheDocument();
  });

  it('shows decision counts', () => {
    renderControls();
    expect(screen.getByText(/1 accepted/i)).toBeInTheDocument();
    expect(screen.getByText(/1 rejected/i)).toBeInTheDocument();
    expect(screen.getByText(/1 pending/i)).toBeInTheDocument();
  });

  it('Accept All shows confirmation dialog', async () => {
    const user = userEvent.setup();
    renderControls();

    await user.click(screen.getByRole('button', { name: /accept all/i }));

    // AlertDialog should appear
    expect(screen.getByText(/are you sure/i)).toBeInTheDocument();
    expect(screen.getByText(/accept all 3 suggestions/i)).toBeInTheDocument();
  });

  it('Reject All shows confirmation dialog', async () => {
    const user = userEvent.setup();
    renderControls();

    await user.click(screen.getByRole('button', { name: /reject all/i }));

    expect(screen.getByText(/are you sure/i)).toBeInTheDocument();
    expect(screen.getByText(/reject all 3 suggestions/i)).toBeInTheDocument();
  });

  it('confirming Accept All calls the bulk decisions API', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      accepted: 3,
      rejected: 0,
      total: 3,
    });

    renderControls();

    await user.click(screen.getByRole('button', { name: /accept all/i }));
    // Click the confirm button inside AlertDialog
    const confirmBtn = screen.getByRole('button', { name: /confirm/i });
    await user.click(confirmBtn);

    expect(mockMutateAsync).toHaveBeenCalledWith({
      decisions: [
        { line_item_id: 'li-001', action: 'accept' },
        { line_item_id: 'li-002', action: 'accept' },
        { line_item_id: 'li-003', action: 'accept' },
      ],
    });
  });

  it('Submit Decisions sends current decisions mix', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      accepted: 1,
      rejected: 1,
      total: 2,
    });

    const decisions: DecisionMap = {
      'li-001': { action: 'accept' },
      'li-002': { action: 'reject' },
      'li-003': { action: 'pending' },
    };

    renderControls(decisions);

    await user.click(
      screen.getByRole('button', { name: /submit decisions/i })
    );

    // Only non-pending decisions should be submitted
    expect(mockMutateAsync).toHaveBeenCalledWith({
      decisions: [
        { line_item_id: 'li-001', action: 'accept' },
        { line_item_id: 'li-002', action: 'reject' },
      ],
    });
  });

  it('Submit Decisions sends override entries with override_sector_code', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      accepted: 2,
      rejected: 1,
      total: 3,
    });

    const decisions: DecisionMap = {
      'li-001': { action: 'accept' },
      'li-002': { action: 'reject' },
      'li-003': { action: 'override', overrideSector: 'S99' },
    };

    renderControls(decisions);

    await user.click(
      screen.getByRole('button', { name: /submit decisions/i })
    );

    expect(mockMutateAsync).toHaveBeenCalledWith({
      decisions: [
        { line_item_id: 'li-001', action: 'accept' },
        { line_item_id: 'li-002', action: 'reject' },
        { line_item_id: 'li-003', action: 'accept', override_sector_code: 'S99' },
      ],
    });
  });

  it('shows override count in summary text', () => {
    const decisions: DecisionMap = {
      'li-001': { action: 'accept' },
      'li-002': { action: 'override', overrideSector: 'S99' },
      'li-003': { action: 'pending' },
    };

    renderControls(decisions);
    expect(screen.getByText(/1 overridden/i)).toBeInTheDocument();
  });

  it('disables Submit Decisions when no decisions are made', () => {
    const allPending: DecisionMap = {
      'li-001': { action: 'pending' },
      'li-002': { action: 'pending' },
      'li-003': { action: 'pending' },
    };
    renderControls(allPending);

    expect(
      screen.getByRole('button', { name: /submit decisions/i })
    ).toBeDisabled();
  });
});
