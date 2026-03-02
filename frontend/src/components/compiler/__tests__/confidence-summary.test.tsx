import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { ConfidenceSummary } from '../confidence-summary';

// ── Tests ────────────────────────────────────────────────────────────

describe('ConfidenceSummary', () => {
  function renderSummary(props?: Partial<Parameters<typeof ConfidenceSummary>[0]>) {
    const defaults = {
      highConfidence: 5,
      mediumConfidence: 3,
      lowConfidence: 2,
      accepted: 4,
      rejected: 1,
      pending: 5,
    };

    return render(
      createElement(ConfidenceSummary, { ...defaults, ...props })
    );
  }

  it('renders confidence text', () => {
    renderSummary();

    expect(screen.getByText(/5 high/)).toBeInTheDocument();
    expect(screen.getByText(/3 medium/)).toBeInTheDocument();
    expect(screen.getByText(/2 low/)).toBeInTheDocument();
  });

  it('renders decision counts', () => {
    renderSummary();

    expect(screen.getByText(/4 accepted/)).toBeInTheDocument();
    expect(screen.getByText(/1 rejected/)).toBeInTheDocument();
    expect(screen.getByText(/5 pending/)).toBeInTheDocument();
  });

  it('renders the stacked bar', () => {
    renderSummary();

    const bar = screen.getByTestId('confidence-bar');
    expect(bar).toBeInTheDocument();
  });

  it('renders green segment for high confidence', () => {
    renderSummary();

    const segment = screen.getByTestId('bar-high');
    expect(segment).toBeInTheDocument();
    expect(segment.className).toMatch(/green/);
  });

  it('renders amber segment for medium confidence', () => {
    renderSummary();

    const segment = screen.getByTestId('bar-medium');
    expect(segment).toBeInTheDocument();
    expect(segment.className).toMatch(/amber/);
  });

  it('renders red segment for low confidence', () => {
    renderSummary();

    const segment = screen.getByTestId('bar-low');
    expect(segment).toBeInTheDocument();
    expect(segment.className).toMatch(/red/);
  });

  it('handles zero total gracefully', () => {
    renderSummary({
      highConfidence: 0,
      mediumConfidence: 0,
      lowConfidence: 0,
      accepted: 0,
      rejected: 0,
      pending: 0,
    });

    expect(screen.getByText(/0 high/)).toBeInTheDocument();
  });
});
