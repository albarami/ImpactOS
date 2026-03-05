import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement } from 'react';
import { RunSelector } from '../RunSelector';

// ── Fixtures ──────────────────────────────────────────────────────────

const sampleRuns = [
  { run_id: 'run-001', label: 'Baseline 2025', created_at: '2025-06-01T10:00:00Z' },
  { run_id: 'run-002', label: 'Scenario A', created_at: '2025-06-02T14:30:00Z' },
  { run_id: 'run-003', created_at: '2025-06-03T09:15:00Z' },
];

// ── Tests ────────────────────────────────────────────────────────────

describe('RunSelector', () => {
  const mockOnCompare = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders two select dropdowns with ARIA labels', () => {
    render(
      createElement(RunSelector, {
        runs: sampleRuns,
        onCompare: mockOnCompare,
      })
    );

    expect(screen.getByLabelText(/run a/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/run b/i)).toBeInTheDocument();
  });

  it('renders run options in both dropdowns', () => {
    render(
      createElement(RunSelector, {
        runs: sampleRuns,
        onCompare: mockOnCompare,
      })
    );

    const selectA = screen.getByLabelText(/run a/i);
    const selectB = screen.getByLabelText(/run b/i);

    // Each select should have a placeholder option + 3 runs
    expect(selectA.querySelectorAll('option').length).toBe(4);
    expect(selectB.querySelectorAll('option').length).toBe(4);
  });

  it('shows run label when available, falls back to run_id', () => {
    render(
      createElement(RunSelector, {
        runs: sampleRuns,
        onCompare: mockOnCompare,
      })
    );

    // run-003 has no label, should show run_id
    expect(screen.getAllByText(/Baseline 2025/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/run-003/).length).toBeGreaterThan(0);
  });

  it('renders Compare button', () => {
    render(
      createElement(RunSelector, {
        runs: sampleRuns,
        onCompare: mockOnCompare,
      })
    );

    expect(
      screen.getByRole('button', { name: /compare/i })
    ).toBeInTheDocument();
  });

  it('Compare button is disabled when no runs are selected', () => {
    render(
      createElement(RunSelector, {
        runs: sampleRuns,
        onCompare: mockOnCompare,
      })
    );

    expect(
      screen.getByRole('button', { name: /compare/i })
    ).toBeDisabled();
  });

  it('Compare button is disabled when same run selected for both', async () => {
    const user = userEvent.setup();
    render(
      createElement(RunSelector, {
        runs: sampleRuns,
        onCompare: mockOnCompare,
      })
    );

    await user.selectOptions(screen.getByLabelText(/run a/i), 'run-001');
    await user.selectOptions(screen.getByLabelText(/run b/i), 'run-001');

    expect(
      screen.getByRole('button', { name: /compare/i })
    ).toBeDisabled();
  });

  it('Compare button is enabled when different runs are selected', async () => {
    const user = userEvent.setup();
    render(
      createElement(RunSelector, {
        runs: sampleRuns,
        onCompare: mockOnCompare,
      })
    );

    await user.selectOptions(screen.getByLabelText(/run a/i), 'run-001');
    await user.selectOptions(screen.getByLabelText(/run b/i), 'run-002');

    expect(
      screen.getByRole('button', { name: /compare/i })
    ).toBeEnabled();
  });

  it('calls onCompare with selected run IDs when button clicked', async () => {
    const user = userEvent.setup();
    render(
      createElement(RunSelector, {
        runs: sampleRuns,
        onCompare: mockOnCompare,
      })
    );

    await user.selectOptions(screen.getByLabelText(/run a/i), 'run-001');
    await user.selectOptions(screen.getByLabelText(/run b/i), 'run-002');
    await user.click(screen.getByRole('button', { name: /compare/i }));

    expect(mockOnCompare).toHaveBeenCalledWith('run-001', 'run-002');
  });

  it('shows loading state when loading prop is true', () => {
    render(
      createElement(RunSelector, {
        runs: sampleRuns,
        onCompare: mockOnCompare,
        loading: true,
      })
    );

    const btn = screen.getByRole('button', { name: /comparing/i });
    expect(btn).toBeDisabled();
  });

  it('does not call onCompare when only one run is selected', async () => {
    const user = userEvent.setup();
    render(
      createElement(RunSelector, {
        runs: sampleRuns,
        onCompare: mockOnCompare,
      })
    );

    await user.selectOptions(screen.getByLabelText(/run a/i), 'run-001');

    // Button should still be disabled since Run B is not selected
    expect(
      screen.getByRole('button', { name: /compare/i })
    ).toBeDisabled();
  });
});
