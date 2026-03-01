import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement } from 'react';
import { DecisionTable, type Suggestion, type DecisionMap } from '../decision-table';

// ── Test data ────────────────────────────────────────────────────────

const SUGGESTIONS: Suggestion[] = [
  {
    line_item_id: 'li-001',
    sector_code: 'S01',
    confidence: 0.92,
    explanation: 'High confidence mapping to construction sector',
  },
  {
    line_item_id: 'li-002',
    sector_code: 'S05',
    confidence: 0.65,
    explanation: 'Medium confidence mapping to manufacturing',
  },
  {
    line_item_id: 'li-003',
    sector_code: 'S12',
    confidence: 0.3,
    explanation: 'Low confidence mapping to services',
  },
];

// ── Tests ────────────────────────────────────────────────────────────

describe('DecisionTable', () => {
  let onDecisionsChange: (decisions: DecisionMap) => void;

  beforeEach(() => {
    vi.clearAllMocks();
    onDecisionsChange = vi.fn<(decisions: DecisionMap) => void>();
  });

  function renderTable(suggestions = SUGGESTIONS) {
    return render(
      createElement(DecisionTable, {
        suggestions,
        onDecisionsChange,
      })
    );
  }

  it('renders column headers', () => {
    renderTable();

    expect(screen.getByText('Line Item')).toBeInTheDocument();
    expect(screen.getByText('Explanation')).toBeInTheDocument();
    expect(screen.getByText('Confidence')).toBeInTheDocument();
    expect(screen.getByText('Sector')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Action')).toBeInTheDocument();
  });

  it('renders suggestion rows', () => {
    renderTable();

    expect(screen.getByText('li-001')).toBeInTheDocument();
    expect(screen.getByText('li-002')).toBeInTheDocument();
    expect(screen.getByText('li-003')).toBeInTheDocument();
  });

  it('renders explanation text', () => {
    renderTable();

    expect(
      screen.getByText('High confidence mapping to construction sector')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Medium confidence mapping to manufacturing')
    ).toBeInTheDocument();
  });

  it('renders sector codes', () => {
    renderTable();

    expect(screen.getByText('S01')).toBeInTheDocument();
    expect(screen.getByText('S05')).toBeInTheDocument();
    expect(screen.getByText('S12')).toBeInTheDocument();
  });

  it('renders confidence badges with correct colors', () => {
    renderTable();

    // High confidence (>= 0.8) should be green
    const highBadge = screen.getByText('92%');
    expect(highBadge).toBeInTheDocument();
    expect(highBadge.className).toMatch(/green/);

    // Medium confidence (>= 0.5) should be amber
    const medBadge = screen.getByText('65%');
    expect(medBadge).toBeInTheDocument();
    expect(medBadge.className).toMatch(/amber/);

    // Low confidence (< 0.5) should be red
    const lowBadge = screen.getByText('30%');
    expect(lowBadge).toBeInTheDocument();
    expect(lowBadge.className).toMatch(/red/);
  });

  it('all rows start with pending status', () => {
    renderTable();

    const pendingBadges = screen.getAllByText('pending');
    expect(pendingBadges).toHaveLength(3);
  });

  it('clicking Accept updates row status and calls onDecisionsChange', async () => {
    const user = userEvent.setup();
    renderTable();

    // Get the first row's Accept button
    const acceptButtons = screen.getAllByRole('button', { name: /accept/i });
    await user.click(acceptButtons[0]);

    // Status should change
    expect(screen.getByText('accepted')).toBeInTheDocument();

    // Callback should be called with updated decisions
    expect(onDecisionsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        'li-001': 'accept',
      })
    );
  });

  it('clicking Reject updates row status and calls onDecisionsChange', async () => {
    const user = userEvent.setup();
    renderTable();

    // Get the first row's Reject button
    const rejectButtons = screen.getAllByRole('button', { name: /reject/i });
    await user.click(rejectButtons[0]);

    // Status should change
    expect(screen.getByText('rejected')).toBeInTheDocument();

    expect(onDecisionsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        'li-001': 'reject',
      })
    );
  });

  it('renders accept and reject buttons for each row', () => {
    renderTable();

    const acceptButtons = screen.getAllByRole('button', { name: /accept/i });
    const rejectButtons = screen.getAllByRole('button', { name: /reject/i });

    expect(acceptButtons).toHaveLength(3);
    expect(rejectButtons).toHaveLength(3);
  });

  it('renders empty state for no suggestions', () => {
    renderTable([]);

    expect(screen.getByText(/no suggestions/i)).toBeInTheDocument();
  });
});
