import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
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
    const acceptButtons = screen.getAllByRole('button', { name: /^accept$/i });
    await user.click(acceptButtons[0]);

    // Status should change
    expect(screen.getByText('accepted')).toBeInTheDocument();

    // Callback should be called with updated decisions (new DecisionEntry format)
    expect(onDecisionsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        'li-001': { action: 'accept' },
      })
    );
  });

  it('clicking Reject updates row status and calls onDecisionsChange', async () => {
    const user = userEvent.setup();
    renderTable();

    // Get the first row's Reject button
    const rejectButtons = screen.getAllByRole('button', { name: /^reject$/i });
    await user.click(rejectButtons[0]);

    // Status should change
    expect(screen.getByText('rejected')).toBeInTheDocument();

    expect(onDecisionsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        'li-001': { action: 'reject' },
      })
    );
  });

  it('renders accept, reject, and override buttons for each row', () => {
    renderTable();

    const acceptButtons = screen.getAllByRole('button', { name: /^accept$/i });
    const rejectButtons = screen.getAllByRole('button', { name: /^reject$/i });
    const overrideButtons = screen.getAllByRole('button', { name: /^override$/i });

    expect(acceptButtons).toHaveLength(3);
    expect(rejectButtons).toHaveLength(3);
    expect(overrideButtons).toHaveLength(3);
  });

  it('renders empty state for no suggestions', () => {
    renderTable([]);

    expect(screen.getByText(/no suggestions/i)).toBeInTheDocument();
  });

  // ── Override UI tests ─────────────────────────────────────────────

  it('clicking Override shows sector input', async () => {
    const user = userEvent.setup();
    renderTable();

    const overrideButtons = screen.getAllByRole('button', { name: /^override$/i });
    await user.click(overrideButtons[0]);

    // Assert text input appears for sector code
    expect(screen.getByLabelText(/override sector code/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/sector code/i)).toBeInTheDocument();
  });

  it('entering sector code and confirming creates override decision', async () => {
    const user = userEvent.setup();
    renderTable();

    // Click Override on first row
    const overrideButtons = screen.getAllByRole('button', { name: /^override$/i });
    await user.click(overrideButtons[0]);

    // Enter sector code
    const input = screen.getByLabelText(/override sector code/i);
    await user.type(input, 'S99');

    // Click Save
    const saveButton = screen.getByRole('button', { name: /save/i });
    await user.click(saveButton);

    // Assert onDecisionsChange was called with override entry
    expect(onDecisionsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        'li-001': { action: 'override', overrideSector: 'S99' },
      })
    );
  });

  it('overridden row shows amber badge with overridden text', async () => {
    const user = userEvent.setup();
    renderTable();

    // Click Override on first row
    const overrideButtons = screen.getAllByRole('button', { name: /^override$/i });
    await user.click(overrideButtons[0]);

    // Enter sector code and confirm
    const input = screen.getByLabelText(/override sector code/i);
    await user.type(input, 'S99');
    const saveButton = screen.getByRole('button', { name: /save/i });
    await user.click(saveButton);

    // Assert status badge shows "overridden" with amber styling
    const overriddenBadge = screen.getByText('overridden');
    expect(overriddenBadge).toBeInTheDocument();
    expect(overriddenBadge.className).toMatch(/amber/);
  });

  it('overridden row shows the new sector code in the Sector column', async () => {
    const user = userEvent.setup();
    renderTable();

    // Click Override on first row
    const overrideButtons = screen.getAllByRole('button', { name: /^override$/i });
    await user.click(overrideButtons[0]);

    // Enter sector code and confirm
    const input = screen.getByLabelText(/override sector code/i);
    await user.type(input, 'S99');
    const saveButton = screen.getByRole('button', { name: /save/i });
    await user.click(saveButton);

    // The sector column for the first row should now show S99 instead of S01
    expect(screen.getByText('S99')).toBeInTheDocument();
  });

  it('cancelling override input hides it without changing decision', async () => {
    const user = userEvent.setup();
    renderTable();

    const overrideButtons = screen.getAllByRole('button', { name: /^override$/i });
    await user.click(overrideButtons[0]);

    // Verify input is visible
    expect(screen.getByLabelText(/override sector code/i)).toBeInTheDocument();

    // Click Cancel
    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    await user.click(cancelButton);

    // Input should be gone
    expect(screen.queryByLabelText(/override sector code/i)).not.toBeInTheDocument();

    // Decision should not have changed (still pending)
    // onDecisionsChange should not have been called
    expect(onDecisionsChange).not.toHaveBeenCalled();
  });
});
