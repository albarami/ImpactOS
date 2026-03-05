import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { DriverCard } from '../DriverCard';

// ── Tests ────────────────────────────────────────────────────────────

describe('DriverCard', () => {
  it('renders driver type as a badge', () => {
    render(
      createElement(DriverCard, {
        driverType: 'final_demand',
        description: 'Increase in household consumption',
        impact: 120.5,
        weight: 0.45,
      })
    );

    expect(screen.getByText('final_demand')).toBeInTheDocument();
  });

  it('renders description text', () => {
    render(
      createElement(DriverCard, {
        driverType: 'final_demand',
        description: 'Increase in household consumption',
        impact: 120.5,
        weight: 0.45,
      })
    );

    expect(
      screen.getByText('Increase in household consumption')
    ).toBeInTheDocument();
  });

  it('renders impact value formatted with sign', () => {
    render(
      createElement(DriverCard, {
        driverType: 'final_demand',
        description: 'Positive impact',
        impact: 120.5,
        weight: 0.45,
      })
    );

    expect(screen.getByText('+120.50')).toBeInTheDocument();
  });

  it('renders negative impact value', () => {
    render(
      createElement(DriverCard, {
        driverType: 'import_substitution',
        description: 'Reduced imports',
        impact: -30.2,
        weight: 0.25,
      })
    );

    expect(screen.getByText('-30.20')).toBeInTheDocument();
  });

  it('renders weight as percentage', () => {
    render(
      createElement(DriverCard, {
        driverType: 'final_demand',
        description: 'Test driver',
        impact: 120.5,
        weight: 0.45,
      })
    );

    expect(screen.getByText(/45\.0%/)).toBeInTheDocument();
  });

  it('shows percentage of total when totalVariance is provided', () => {
    render(
      createElement(DriverCard, {
        driverType: 'final_demand',
        description: 'Test driver',
        impact: 120.5,
        weight: 0.45,
        totalVariance: 140.3,
      })
    );

    // 120.5 / 140.3 = ~85.9%
    expect(screen.getByText(/85\.9% of total/i)).toBeInTheDocument();
  });

  it('does not show percentage of total when totalVariance is not provided', () => {
    render(
      createElement(DriverCard, {
        driverType: 'final_demand',
        description: 'Test driver',
        impact: 120.5,
        weight: 0.45,
      })
    );

    expect(screen.queryByText(/of total/i)).not.toBeInTheDocument();
  });

  it('renders sourceField when provided', () => {
    render(
      createElement(DriverCard, {
        driverType: 'final_demand',
        description: 'Test driver',
        impact: 120.5,
        weight: 0.45,
        sourceField: 'demand_vector',
      })
    );

    expect(screen.getByText(/demand_vector/)).toBeInTheDocument();
  });

  it('renders diffSummary when provided', () => {
    render(
      createElement(DriverCard, {
        driverType: 'final_demand',
        description: 'Test driver',
        impact: 120.5,
        weight: 0.45,
        diffSummary: '+12% in sector 3',
      })
    );

    expect(screen.getByText('+12% in sector 3')).toBeInTheDocument();
  });

  it('does not render sourceField or diffSummary when not provided', () => {
    const { container } = render(
      createElement(DriverCard, {
        driverType: 'final_demand',
        description: 'Test driver',
        impact: 120.5,
        weight: 0.45,
      })
    );

    expect(screen.queryByText(/source/i)).not.toBeInTheDocument();
    expect(container.querySelector('[data-testid="diff-summary"]')).toBeNull();
  });
});
