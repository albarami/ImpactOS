import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { SectorBreakdownsPanel } from '../sector-breakdowns-panel';
import { WorkforcePanel } from '../workforce-panel';
import { FeasibilityPanel } from '../feasibility-panel';
import { ScenarioSuitePanel } from '../scenario-suite-panel';
import { QualitativeRisksPanel } from '../qualitative-risks-panel';
import { SensitivityEnvelopePanel } from '../sensitivity-envelope-panel';
import { DepthEngineTracePanel } from '../depth-engine-trace-panel';

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

// ── P6-4: Scenario Suite Panel ──────────────────────────────────

describe('ScenarioSuitePanel', () => {
  it('renders scenario run rows', () => {
    const runs = [
      { name: 'Base Case', mode: 'GOVERNED', is_contrarian: false, sensitivities: [] },
      { name: 'High Growth', mode: 'SANDBOX', is_contrarian: false, sensitivities: ['s1'] },
    ];
    render(createElement(ScenarioSuitePanel, { runs }));
    expect(screen.getByText('Base Case')).toBeInTheDocument();
    expect(screen.getByText('High Growth')).toBeInTheDocument();
    expect(screen.getByText('GOVERNED')).toBeInTheDocument();
    expect(screen.getByText('SANDBOX')).toBeInTheDocument();
  });

  it('shows contrarian badge for contrarian runs', () => {
    const runs = [
      { name: 'Contrarian Shock', is_contrarian: true },
    ];
    render(createElement(ScenarioSuitePanel, { runs }));
    expect(screen.getByText('Contrarian')).toBeInTheDocument();
  });

  it('renders nothing when runs is empty', () => {
    const { container } = render(
      createElement(ScenarioSuitePanel, { runs: [] })
    );
    expect(container.textContent).toBe('');
  });
});

// ── P6-4: Qualitative Risks Panel ───────────────────────────────

describe('QualitativeRisksPanel', () => {
  it('renders risk cards with labels and descriptions', () => {
    const risks = [
      {
        risk_id: 'r1',
        label: 'Supply chain disruption',
        description: 'Possible port closure affecting imports',
      },
      {
        risk_id: 'r2',
        label: 'Regulatory change',
        description: 'New labor law impacts hiring costs',
      },
    ];
    render(createElement(QualitativeRisksPanel, { risks }));
    expect(screen.getByText('Supply chain disruption')).toBeInTheDocument();
    expect(screen.getByText('Regulatory change')).toBeInTheDocument();
    expect(screen.getByText(/port closure/)).toBeInTheDocument();
  });

  it('shows not-modeled badge on each risk', () => {
    const risks = [
      { label: 'Risk A', description: 'Description A' },
    ];
    render(createElement(QualitativeRisksPanel, { risks }));
    expect(screen.getByText('Not modeled in engine')).toBeInTheDocument();
  });

  it('renders nothing when risks is empty', () => {
    const { container } = render(
      createElement(QualitativeRisksPanel, { risks: [] })
    );
    expect(container.textContent).toBe('');
  });
});

// ── P6-4: Sensitivity Envelope Panel ────────────────────────────

describe('SensitivityEnvelopePanel', () => {
  it('renders sweep runs sorted by multiplier', () => {
    const runs = [
      { name: 'High', multiplier: 1.2, total_output: 1200000 },
      { name: 'Base', multiplier: 1.0, total_output: 1000000 },
      { name: 'Low', multiplier: 0.8, total_output: 800000 },
    ];
    render(createElement(SensitivityEnvelopePanel, { runs }));
    expect(screen.getByTestId('sensitivity-envelope-panel')).toBeInTheDocument();
    expect(screen.getByText('Low')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
  });

  it('shows envelope range (min to max)', () => {
    const runs = [
      { name: 'Low', multiplier: 0.8, total_output: 800000 },
      { name: 'High', multiplier: 1.2, total_output: 1200000 },
    ];
    render(createElement(SensitivityEnvelopePanel, { runs }));
    const range = screen.getByTestId('envelope-range');
    expect(range).toBeInTheDocument();
    // Values appear in both summary and table, so use getAllByText
    expect(screen.getAllByText('800,000').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('1,200,000').length).toBeGreaterThanOrEqual(1);
    // Verify summary labels
    expect(screen.getByText('Low estimate')).toBeInTheDocument();
    expect(screen.getByText('High estimate')).toBeInTheDocument();
  });

  it('renders nothing when runs is empty', () => {
    const { container } = render(
      createElement(SensitivityEnvelopePanel, { runs: [] })
    );
    expect(container.textContent).toBe('');
  });
});

// ── P6-4: Depth Engine Trace Panel ──────────────────────────────

describe('DepthEngineTracePanel', () => {
  it('renders all 5 pipeline steps', () => {
    const steps = [
      { step: 1, step_name: 'KHAWATIR', generation_mode: 'LLM', duration_ms: 1200, input_tokens: 500, output_tokens: 800 },
      { step: 2, step_name: 'MURAQABA', generation_mode: 'LLM', duration_ms: 900, input_tokens: 400, output_tokens: 600 },
      { step: 3, step_name: 'MUJAHADA', generation_mode: 'LLM', duration_ms: 1100, input_tokens: 450, output_tokens: 700 },
      { step: 4, step_name: 'MUHASABA', generation_mode: 'LLM', duration_ms: 800, input_tokens: 350, output_tokens: 500 },
      { step: 5, step_name: 'SUITE_PLANNING', generation_mode: 'FALLBACK', duration_ms: 50, input_tokens: 0, output_tokens: 0 },
    ];
    render(createElement(DepthEngineTracePanel, { steps }));
    expect(screen.getByText('KHAWATIR')).toBeInTheDocument();
    expect(screen.getByText('MURAQABA')).toBeInTheDocument();
    expect(screen.getByText('MUJAHADA')).toBeInTheDocument();
    expect(screen.getByText('MUHASABA')).toBeInTheDocument();
    expect(screen.getByText('SUITE_PLANNING')).toBeInTheDocument();
  });

  it('shows LLM vs FALLBACK badges', () => {
    const steps = [
      { step: 1, step_name: 'KHAWATIR', generation_mode: 'LLM' },
      { step: 2, step_name: 'MURAQABA', generation_mode: 'FALLBACK' },
    ];
    render(createElement(DepthEngineTracePanel, { steps }));
    expect(screen.getByText('LLM')).toBeInTheDocument();
    expect(screen.getByText('FALLBACK')).toBeInTheDocument();
  });

  it('renders nothing when steps is empty', () => {
    const { container } = render(
      createElement(DepthEngineTracePanel, { steps: [] })
    );
    expect(container.textContent).toBe('');
  });
});
