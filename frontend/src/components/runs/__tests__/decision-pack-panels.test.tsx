import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { SectorBreakdownsPanel } from '../sector-breakdowns-panel';
import { WorkforcePanel } from '../workforce-panel';
import { FeasibilityPanel } from '../feasibility-panel';
import { ScenarioSuitePanel } from '../scenario-suite-panel';
import { QualitativeRisksPanel } from '../qualitative-risks-panel';
import { SensitivityEnvelopePanel } from '../sensitivity-envelope-panel';
import { DepthEngineTracePanel } from '../depth-engine-trace-panel';

describe('SectorBreakdownsPanel', () => {
  it('renders direct and indirect breakdown cards', () => {
    const breakdowns = {
      direct: { SEC01: 500000, SEC02: 300000 },
      indirect: { SEC01: 100000, SEC02: 150000 },
      employment: { SEC01: 50, SEC02: 30 },
    };
    render(createElement(SectorBreakdownsPanel, { breakdowns }));
    expect(screen.getAllByText(/breakdown/i)).toHaveLength(3);
    expect(screen.getByText('Direct Breakdown')).toBeInTheDocument();
    expect(screen.getByText('Indirect Breakdown')).toBeInTheDocument();
  });
});

describe('WorkforcePanel', () => {
  it('renders saudization split and sector rows', () => {
    render(createElement(WorkforcePanel, {
      workforce: {
        total_jobs: 230,
        total_saudi_ready: 80,
        total_saudi_trainable: 50,
        total_expat_reliant: 100,
        has_saudization_split: true,
        per_sector: [
          {
            sector_code: 'SEC01',
            total_jobs: 150,
            saudi_ready_jobs: 50,
            saudi_trainable_jobs: 30,
            expat_reliant_jobs: 70,
          },
        ],
      },
    }));
    expect(screen.getByText('SEC01')).toBeInTheDocument();
    expect(screen.getAllByText(/Saudi-ready/i)).toHaveLength(2);
    expect(screen.getAllByText(/Expat-reliant/i)).toHaveLength(2);
  });
});

describe('FeasibilityPanel', () => {
  it('shows feasible output alongside unconstrained', () => {
    render(createElement(FeasibilityPanel, {
      unconstrained: { SEC01: 1000000 },
      feasible: { SEC01: 800000 },
      gap: { SEC01: 200000 },
    }));
    expect(screen.getByText(/Feasible/i)).toBeInTheDocument();
    expect(screen.getByText('SEC01')).toBeInTheDocument();
  });
});

describe('ScenarioSuitePanel', () => {
  it('renders headline output and muhasaba status from persisted suite runs', () => {
    render(createElement(ScenarioSuitePanel, {
      runs: [
        {
          scenario_spec_id: 'sc-1',
          scenario_spec_version: 1,
          run_id: 'run-1',
          direction_id: 'dir-1',
          name: 'Base Case',
          mode: 'GOVERNED',
          is_contrarian: false,
          multiplier: 1.0,
          headline_output: -25000000,
          employment: -82000,
          muhasaba_status: 'SURVIVED',
          sensitivities: ['volume'],
        },
      ],
      denomination: 'SAR',
    }));
    expect(screen.getByText('Base Case')).toBeInTheDocument();
    expect(screen.getByText('SURVIVED')).toBeInTheDocument();
    expect(screen.getByText(/25,000,000/)).toBeInTheDocument();
  });
});

describe('QualitativeRisksPanel', () => {
  it('renders disclosure tier and not-modelled label', () => {
    render(createElement(QualitativeRisksPanel, {
      risks: [
        {
          risk_id: 'r1',
          label: 'Border congestion',
          description: 'Not modelled in deterministic IO.',
          disclosure_tier: 'TIER1',
          not_modeled: true,
          affected_sectors: ['S1'],
          trigger_conditions: ['peak season'],
          expected_direction: 'negative',
        },
      ],
    }));
    expect(screen.getByText('Border congestion')).toBeInTheDocument();
    expect(screen.getByText('TIER1')).toBeInTheDocument();
    expect(screen.getByText(/NOT MODELLED IN IO FRAMEWORK/i)).toBeInTheDocument();
  });
});

describe('SensitivityEnvelopePanel', () => {
  it('renders low, central, and high estimates from suite runs', () => {
    render(createElement(SensitivityEnvelopePanel, {
      runs: [
        {
          scenario_spec_id: 'sc-low',
          scenario_spec_version: 1,
          run_id: 'run-low',
          direction_id: 'dir-low',
          name: 'Low',
          mode: 'GOVERNED',
          is_contrarian: false,
          multiplier: 0.8,
          headline_output: -32000000,
          employment: -90000,
          muhasaba_status: 'SURVIVED',
          sensitivities: ['volume'],
        },
        {
          scenario_spec_id: 'sc-mid',
          scenario_spec_version: 1,
          run_id: 'run-mid',
          direction_id: 'dir-mid',
          name: 'Base',
          mode: 'GOVERNED',
          is_contrarian: false,
          multiplier: 1.0,
          headline_output: -25000000,
          employment: -82000,
          muhasaba_status: 'SURVIVED',
          sensitivities: ['volume'],
        },
        {
          scenario_spec_id: 'sc-high',
          scenario_spec_version: 1,
          run_id: 'run-high',
          direction_id: 'dir-high',
          name: 'High',
          mode: 'GOVERNED',
          is_contrarian: false,
          multiplier: 1.2,
          headline_output: -18000000,
          employment: -70000,
          muhasaba_status: 'SURVIVED',
          sensitivities: ['volume'],
        },
      ],
      denomination: 'SAR',
    }));
    expect(screen.getByTestId('envelope-range')).toBeInTheDocument();
    expect(screen.getByText(/Dominant sensitivity driver/i)).toBeInTheDocument();
  });
});

describe('DepthEngineTracePanel', () => {
  it('renders step details when expanded', () => {
    render(createElement(DepthEngineTracePanel, {
      planId: 'plan-1',
      steps: [
        {
          step: 1,
          step_name: 'KHAWATIR',
          generation_mode: 'LLM',
          duration_ms: 1200,
          input_tokens: 500,
          output_tokens: 800,
          details: { candidate_count: 5, label_counts: 'insight=4,nafs=1' },
        },
      ],
    }));
    fireEvent.click(screen.getByRole('button', { name: /show trace details/i }));
    expect(screen.getByText('KHAWATIR')).toBeInTheDocument();
    expect(screen.getByText(/candidate_count/i)).toBeInTheDocument();
  });
});
