import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { WaterfallChart } from '../WaterfallChart';
import type { BridgeDriverResponse } from '@/lib/api/hooks/useVarianceBridges';

// ── Fixtures ──────────────────────────────────────────────────────────

const sampleDrivers: BridgeDriverResponse[] = [
  {
    driver_type: 'final_demand',
    description: 'Increase in household consumption',
    impact: 120.5,
    raw_magnitude: 150.0,
    weight: 0.45,
    source_field: 'demand_vector',
    diff_summary: '+12% in sector 3',
  },
  {
    driver_type: 'import_substitution',
    description: 'Reduced imports in manufacturing',
    impact: -30.2,
    raw_magnitude: 40.0,
    weight: 0.25,
    source_field: null,
    diff_summary: null,
  },
  {
    driver_type: 'technology_coefficient',
    description: 'Updated A-matrix coefficients',
    impact: 50.0,
    raw_magnitude: 60.0,
    weight: 0.3,
    source_field: 'a_matrix',
    diff_summary: 'Row 5 changed',
  },
];

// ── Tests ────────────────────────────────────────────────────────────

describe('WaterfallChart', () => {
  it('renders start value bar', () => {
    render(
      createElement(WaterfallChart, {
        startValue: 1000,
        endValue: 1140.3,
        totalVariance: 140.3,
        drivers: sampleDrivers,
      })
    );

    expect(screen.getByText(/start/i)).toBeInTheDocument();
    expect(screen.getByText('1,000.00')).toBeInTheDocument();
  });

  it('renders end value bar', () => {
    render(
      createElement(WaterfallChart, {
        startValue: 1000,
        endValue: 1140.3,
        totalVariance: 140.3,
        drivers: sampleDrivers,
      })
    );

    expect(screen.getByText(/end/i)).toBeInTheDocument();
    expect(screen.getByText('1,140.30')).toBeInTheDocument();
  });

  it('renders a bar for each driver', () => {
    render(
      createElement(WaterfallChart, {
        startValue: 1000,
        endValue: 1140.3,
        totalVariance: 140.3,
        drivers: sampleDrivers,
      })
    );

    expect(screen.getByText('final_demand')).toBeInTheDocument();
    expect(screen.getByText('import_substitution')).toBeInTheDocument();
    expect(screen.getByText('technology_coefficient')).toBeInTheDocument();
  });

  it('marks positive drivers with data-positive attribute', () => {
    render(
      createElement(WaterfallChart, {
        startValue: 1000,
        endValue: 1140.3,
        totalVariance: 140.3,
        drivers: sampleDrivers,
      })
    );

    const positiveBars = document.querySelectorAll('[data-positive]');
    // final_demand (+120.5) and technology_coefficient (+50.0) are positive
    expect(positiveBars.length).toBe(2);
  });

  it('marks negative drivers with data-negative attribute', () => {
    render(
      createElement(WaterfallChart, {
        startValue: 1000,
        endValue: 1140.3,
        totalVariance: 140.3,
        drivers: sampleDrivers,
      })
    );

    const negativeBars = document.querySelectorAll('[data-negative]');
    // import_substitution (-30.2) is negative
    expect(negativeBars.length).toBe(1);
  });

  it('displays impact values for each driver', () => {
    render(
      createElement(WaterfallChart, {
        startValue: 1000,
        endValue: 1140.3,
        totalVariance: 140.3,
        drivers: sampleDrivers,
      })
    );

    expect(screen.getByText('+120.50')).toBeInTheDocument();
    expect(screen.getByText('-30.20')).toBeInTheDocument();
    expect(screen.getByText('+50.00')).toBeInTheDocument();
  });

  it('shows "No variance detected" when drivers are empty', () => {
    render(
      createElement(WaterfallChart, {
        startValue: 1000,
        endValue: 1000,
        totalVariance: 0,
        drivers: [],
      })
    );

    expect(screen.getByText(/no variance detected/i)).toBeInTheDocument();
  });

  it('has accessible ARIA labels on bars', () => {
    render(
      createElement(WaterfallChart, {
        startValue: 1000,
        endValue: 1140.3,
        totalVariance: 140.3,
        drivers: sampleDrivers,
      })
    );

    expect(
      screen.getByLabelText(/start value: 1,000.00/i)
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/end value: 1,140.30/i)
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/final_demand: \+120.50/i)
    ).toBeInTheDocument();
  });
});
