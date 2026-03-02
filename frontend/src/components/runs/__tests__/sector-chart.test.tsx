import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { SectorChart } from '../sector-chart';

// Mock recharts — rendering in jsdom doesn't produce SVG properly.
// We mock the module to render simple text placeholders.
vi.mock('recharts', () => {
  const MockBarChart = ({
    children,
    data,
  }: {
    children: React.ReactNode;
    data: Array<{ sector: string; value: number }>;
  }) =>
    createElement(
      'div',
      { 'data-testid': 'bar-chart' },
      data.map((d) =>
        createElement('span', { key: d.sector }, `${d.sector}: ${d.value}`)
      ),
      children
    );

  const MockBar = () => createElement('div', { 'data-testid': 'bar' });
  const MockXAxis = () => createElement('div', { 'data-testid': 'x-axis' });
  const MockYAxis = () => createElement('div', { 'data-testid': 'y-axis' });
  const MockTooltip = () =>
    createElement('div', { 'data-testid': 'tooltip' });
  const MockResponsiveContainer = ({
    children,
  }: {
    children: React.ReactNode;
  }) => createElement('div', { 'data-testid': 'responsive-container' }, children);

  return {
    BarChart: MockBarChart,
    Bar: MockBar,
    XAxis: MockXAxis,
    YAxis: MockYAxis,
    Tooltip: MockTooltip,
    ResponsiveContainer: MockResponsiveContainer,
  };
});

// ── Tests ────────────────────────────────────────────────────────────

describe('SectorChart', () => {
  it('renders a bar chart', () => {
    render(
      createElement(SectorChart, {
        data: { S01: 1500000, S02: 750000 },
      })
    );
    expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
  });

  it('sorts sectors by value descending', () => {
    render(
      createElement(SectorChart, {
        data: { S01: 500, S02: 1000, S03: 750 },
      })
    );
    const spans = screen.getAllByText(/S0\d/);
    // S02 (1000) should come first, then S03 (750), then S01 (500)
    expect(spans[0].textContent).toContain('S02');
    expect(spans[1].textContent).toContain('S03');
    expect(spans[2].textContent).toContain('S01');
  });

  it('displays sector codes and values', () => {
    render(
      createElement(SectorChart, {
        data: { S01: 1500000, S02: 750000 },
      })
    );
    expect(screen.getByText(/S01: 1500000/)).toBeInTheDocument();
    expect(screen.getByText(/S02: 750000/)).toBeInTheDocument();
  });

  it('renders empty state when no data', () => {
    render(createElement(SectorChart, { data: {} }));
    expect(screen.getByText(/no sector data/i)).toBeInTheDocument();
  });

  it('renders a responsive container', () => {
    render(
      createElement(SectorChart, {
        data: { S01: 100 },
      })
    );
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
  });
});
