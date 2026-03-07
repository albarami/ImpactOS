import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { SectorBreakdownsPanel } from '../sector-breakdowns-panel';
import { WorkforcePanel } from '../workforce-panel';
import { FeasibilityPanel } from '../feasibility-panel';

// ── P6-4: Decision Pack surface component tests ──────────────────

describe('SectorBreakdownsPanel', () => {
  it('renders direct and indirect breakdown cards', () => {
    const breakdowns = {
      direct: { SEC01: 500000, SEC02: 300000, SEC03: 200000 },
      indirect: { SEC01: 100000, SEC02: 150000, SEC03: 80000 },
      employment: { SEC01: 50, SEC02: 30, SEC03: 20 },
    };
    render(createElement(SectorBreakdownsPanel, { breakdowns }));
    expect(screen.getByText(/Direct Breakdown/)).toBeInTheDocument();
    expect(screen.getByText(/Indirect Breakdown/)).toBeInTheDocument();
  });

  it('shows sector values for each breakdown', () => {
    const breakdowns = {
      direct: { SEC01: 500000 },
      indirect: { SEC01: 100000 },
    };
    render(createElement(SectorBreakdownsPanel, { breakdowns }));
    // SEC01 appears in both direct and indirect tables
    const sectorCells = screen.getAllByText('SEC01');
    expect(sectorCells.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('500,000')).toBeInTheDocument();
  });

  it('renders nothing when breakdowns is empty', () => {
    const { container } = render(
      createElement(SectorBreakdownsPanel, { breakdowns: {} })
    );
    expect(container.textContent).toBe('');
  });
});

describe('WorkforcePanel', () => {
  it('renders employment data by sector', () => {
    const employment = { SEC01: 150, SEC02: 80, SEC03: 45 };
    render(createElement(WorkforcePanel, { employment }));
    expect(screen.getByText('SEC01')).toBeInTheDocument();
    expect(screen.getByText('150')).toBeInTheDocument();
  });

  it('shows total jobs headline', () => {
    const employment = { SEC01: 150, SEC02: 80 };
    render(createElement(WorkforcePanel, { employment }));
    // 150 + 80 = 230
    expect(screen.getByText(/230/)).toBeInTheDocument();
    expect(screen.getByText(/total jobs/i)).toBeInTheDocument();
  });

  it('renders nothing when employment is empty', () => {
    const { container } = render(
      createElement(WorkforcePanel, { employment: {} })
    );
    expect(container.textContent).toBe('');
  });
});

describe('FeasibilityPanel', () => {
  it('shows feasible output alongside unconstrained', () => {
    const unconstrained = { SEC01: 1000000, SEC02: 500000 };
    const feasible = { SEC01: 800000, SEC02: 500000 };
    const gap = { SEC01: 200000, SEC02: 0 };
    render(
      createElement(FeasibilityPanel, { unconstrained, feasible, gap })
    );
    expect(screen.getByText(/feasible/i)).toBeInTheDocument();
    expect(screen.getByText('SEC01')).toBeInTheDocument();
  });

  it('highlights binding constraints with positive gap', () => {
    const unconstrained = { SEC01: 1000000 };
    const feasible = { SEC01: 800000 };
    const gap = { SEC01: 200000 };
    render(
      createElement(FeasibilityPanel, { unconstrained, feasible, gap })
    );
    // Gap of 200000 should be visible
    expect(screen.getByText('200,000')).toBeInTheDocument();
  });

  it('renders nothing when no feasibility data provided', () => {
    const { container } = render(
      createElement(FeasibilityPanel, {
        unconstrained: {},
        feasible: {},
        gap: {},
      })
    );
    expect(container.textContent).toBe('');
  });
});
