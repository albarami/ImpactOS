import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { ScenarioCompileForm } from '../compile-form';
import type { CompileResponse, DecisionMap } from '@/lib/api/hooks/useCompiler';

// ── Mocks ────────────────────────────────────────────────────────────

const mockCompileMutateAsync = vi.fn();
let mockCompilationData: CompileResponse | undefined;
let mockCachedDecisions: DecisionMap | undefined;

vi.mock('@/lib/api/hooks/useScenarios', () => ({
  useCompileScenario: () => ({
    mutateAsync: mockCompileMutateAsync,
    isPending: false,
  }),
}));

vi.mock('@/lib/api/hooks/useCompiler', () => ({
  useCompilationData: () => mockCompilationData,
  useCompilationDecisions: () => mockCachedDecisions,
}));

// ── Helpers ──────────────────────────────────────────────────────────

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function createWrapper(queryClient?: QueryClient) {
  const qc = queryClient ?? createQueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children);
  };
}

function renderForm(props?: {
  workspaceId?: string;
  scenarioId?: string;
  compilationId?: string;
}) {
  return render(
    createElement(
      createWrapper(),
      null,
      createElement(ScenarioCompileForm, {
        workspaceId: props?.workspaceId ?? 'ws-001',
        scenarioId: props?.scenarioId ?? 'sc-001',
        compilationId: props?.compilationId,
      })
    )
  );
}

const COMPILATION_DATA: CompileResponse = {
  compilation_id: 'comp-001',
  suggestions: [
    {
      line_item_id: 'li-001',
      sector_code: 'S01',
      confidence: 0.92,
      explanation: 'High confidence mapping to construction',
    },
    {
      line_item_id: 'li-002',
      sector_code: 'S02',
      confidence: 0.45,
      explanation: 'Low confidence mapping to services',
    },
    {
      line_item_id: 'li-003',
      sector_code: 'S03',
      confidence: 0.78,
      explanation: 'Medium confidence mapping',
    },
  ],
  high_confidence: 1,
  medium_confidence: 1,
  low_confidence: 1,
};

// ── Tests ────────────────────────────────────────────────────────────

describe('ScenarioCompileForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCompilationData = undefined;
    mockCachedDecisions = undefined;
  });

  it('renders compile form heading', () => {
    renderForm();
    expect(screen.getByText(/compile scenario/i)).toBeInTheDocument();
  });

  it('renders document ID input when no compilationId', () => {
    renderForm();
    expect(screen.getByLabelText(/document id/i)).toBeInTheDocument();
  });

  it('renders phasing editor with default entry', () => {
    renderForm();
    expect(screen.getByText(/phasing/i)).toBeInTheDocument();
    // Should have at least one year input and share input
    const yearInputs = screen.getAllByPlaceholderText(/year/i);
    expect(yearInputs.length).toBeGreaterThanOrEqual(1);
  });

  it('renders submit button', () => {
    renderForm();
    expect(
      screen.getByRole('button', { name: /compile/i })
    ).toBeInTheDocument();
  });

  // ── With compilation data ──────────────────────────────────────────

  describe('with compilationId and cached data', () => {
    beforeEach(() => {
      mockCompilationData = COMPILATION_DATA;
    });

    it('shows decisions summary table from compilation cache', () => {
      renderForm({ compilationId: 'comp-001' });
      // Should show line item IDs in summary
      expect(screen.getByText('li-001')).toBeInTheDocument();
      expect(screen.getByText('li-002')).toBeInTheDocument();
      expect(screen.getByText('li-003')).toBeInTheDocument();
    });

    it('shows sector codes in the summary', () => {
      renderForm({ compilationId: 'comp-001' });
      expect(screen.getByText('S01')).toBeInTheDocument();
      expect(screen.getByText('S02')).toBeInTheDocument();
      expect(screen.getByText('S03')).toBeInTheDocument();
    });

    it('shows decision types (APPROVED/EXCLUDED) in summary', () => {
      renderForm({ compilationId: 'comp-001' });
      // By default all items from compiler are "accept" -> APPROVED
      const approvedBadges = screen.getAllByText('APPROVED');
      expect(approvedBadges.length).toBeGreaterThanOrEqual(1);
    });

    it('shows warning when no cached decisions exist', () => {
      mockCachedDecisions = undefined;
      renderForm({ compilationId: 'comp-001' });
      expect(
        screen.getByText(/no review decisions found/i)
      ).toBeInTheDocument();
    });

    it('does not show warning when cached decisions exist', () => {
      mockCachedDecisions = {
        'li-001': { action: 'accept' },
        'li-002': { action: 'reject' },
        'li-003': { action: 'accept' },
      };
      renderForm({ compilationId: 'comp-001' });
      expect(
        screen.queryByText(/no review decisions found/i)
      ).not.toBeInTheDocument();
    });

    it('maps decisions correctly on submit', async () => {
      const user = userEvent.setup();
      mockCompileMutateAsync.mockResolvedValueOnce({
        scenario_spec_id: 'sc-001',
        version: 2,
        shock_items: [],
      });

      renderForm({ compilationId: 'comp-001' });

      const btn = screen.getByRole('button', { name: /compile/i });
      await user.click(btn);

      expect(mockCompileMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          decisions: expect.arrayContaining([
            expect.objectContaining({
              line_item_id: 'li-001',
              decision_type: 'APPROVED',
              final_sector_code: 'S01',
              decided_by: '00000000-0000-7000-8000-000000000001',
            }),
          ]),
          phasing: expect.any(Object),
        })
      );
    });

    it('shows shock items table after successful compile', async () => {
      const user = userEvent.setup();
      mockCompileMutateAsync.mockResolvedValueOnce({
        scenario_spec_id: 'sc-001',
        version: 2,
        shock_items: [
          {
            shock_type: 'FinalDemandShock',
            sector_code: 'S01',
            value: 1000000,
            year: '2025',
          },
        ],
      });

      renderForm({ compilationId: 'comp-001' });

      const btn = screen.getByRole('button', { name: /compile/i });
      await user.click(btn);

      expect(
        await screen.findByText('FinalDemandShock')
      ).toBeInTheDocument();
      expect(screen.getByText('1000000')).toBeInTheDocument();
    });
  });

  // ── With cached F-3A decisions ───────────────────────────────────

  describe('with cached F-3A decisions', () => {
    beforeEach(() => {
      mockCompilationData = COMPILATION_DATA;
    });

    it('reads cached F-3A decisions and maps them correctly', async () => {
      const user = userEvent.setup();
      // Set up cached decisions: one accept, one reject, one override
      mockCachedDecisions = {
        'li-001': { action: 'accept' },
        'li-002': { action: 'reject' },
        'li-003': { action: 'override', overrideSector: 'S99' },
      };

      mockCompileMutateAsync.mockResolvedValueOnce({
        scenario_spec_id: 'sc-001',
        version: 2,
        shock_items: [],
      });

      renderForm({ compilationId: 'comp-001' });

      // Verify summary table shows correct decision types
      expect(screen.getByText('APPROVED')).toBeInTheDocument();
      expect(screen.getByText('EXCLUDED')).toBeInTheDocument();
      expect(screen.getByText('OVERRIDDEN')).toBeInTheDocument();

      // Verify the override sector code is shown
      expect(screen.getByText('S99')).toBeInTheDocument();

      // Submit the form
      const btn = screen.getByRole('button', { name: /compile/i });
      await user.click(btn);

      // Verify the decisions sent to the API
      expect(mockCompileMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          decisions: expect.arrayContaining([
            expect.objectContaining({
              line_item_id: 'li-001',
              decision_type: 'APPROVED',
              final_sector_code: 'S01',
            }),
            expect.objectContaining({
              line_item_id: 'li-002',
              decision_type: 'EXCLUDED',
              final_sector_code: null,
            }),
            expect.objectContaining({
              line_item_id: 'li-003',
              decision_type: 'OVERRIDDEN',
              final_sector_code: 'S99',
            }),
          ]),
        })
      );
    });

    it('pending cached decisions default to APPROVED', async () => {
      const user = userEvent.setup();
      mockCachedDecisions = {
        'li-001': { action: 'pending' },
        'li-002': { action: 'accept' },
        'li-003': { action: 'accept' },
      };

      mockCompileMutateAsync.mockResolvedValueOnce({
        scenario_spec_id: 'sc-001',
        version: 2,
        shock_items: [],
      });

      renderForm({ compilationId: 'comp-001' });

      const btn = screen.getByRole('button', { name: /compile/i });
      await user.click(btn);

      // li-001 has 'pending', which is NOT in overrides, so defaults to accept/APPROVED
      expect(mockCompileMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          decisions: expect.arrayContaining([
            expect.objectContaining({
              line_item_id: 'li-001',
              decision_type: 'APPROVED',
              final_sector_code: 'S01',
            }),
          ]),
        })
      );
    });
  });

  // ── Without compilation data ───────────────────────────────────────

  describe('without compilationId', () => {
    it('shows no compilation message when no compilationId', () => {
      renderForm();
      expect(
        screen.getByText(/no compilation data/i)
      ).toBeInTheDocument();
    });

    it('allows manual document ID input and submits with empty decisions', async () => {
      const user = userEvent.setup();
      mockCompileMutateAsync.mockResolvedValueOnce({
        scenario_spec_id: 'sc-001',
        version: 2,
        shock_items: [],
      });

      renderForm();

      await user.type(screen.getByLabelText(/document id/i), 'doc-123');

      const btn = screen.getByRole('button', { name: /compile/i });
      await user.click(btn);

      expect(mockCompileMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          document_id: 'doc-123',
          decisions: [],
          phasing: expect.any(Object),
        })
      );
    });
  });

  // ── Phasing editor ─────────────────────────────────────────────────

  describe('phasing editor', () => {
    it('adds a new phasing entry when add button is clicked', async () => {
      const user = userEvent.setup();
      renderForm();

      const addBtn = screen.getByRole('button', { name: /add year/i });
      await user.click(addBtn);

      const yearInputs = screen.getAllByPlaceholderText(/year/i);
      expect(yearInputs.length).toBe(2);
    });

    it('removes a phasing entry when remove button is clicked', async () => {
      const user = userEvent.setup();
      renderForm();

      // Add a second entry
      const addBtn = screen.getByRole('button', { name: /add year/i });
      await user.click(addBtn);

      const removeButtons = screen.getAllByRole('button', { name: /remove/i });
      await user.click(removeButtons[0]);

      const yearInputs = screen.getAllByPlaceholderText(/year/i);
      expect(yearInputs.length).toBe(1);
    });

    it('shows phasing validation error when shares do not sum to 1.0', async () => {
      const user = userEvent.setup();
      mockCompilationData = COMPILATION_DATA;
      renderForm({ compilationId: 'comp-001' });

      // Change the share to something other than 1.0
      const shareInputs = screen.getAllByPlaceholderText(/share/i);
      await user.clear(shareInputs[0]);
      await user.type(shareInputs[0], '0.5');

      const btn = screen.getByRole('button', { name: /compile/i });
      await user.click(btn);

      expect(
        screen.getByText(/phasing shares must sum to 1\.0/i)
      ).toBeInTheDocument();
      expect(mockCompileMutateAsync).not.toHaveBeenCalled();
    });
  });
});
