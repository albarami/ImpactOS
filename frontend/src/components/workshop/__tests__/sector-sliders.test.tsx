import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { createElement } from 'react';
import { SectorSliders } from '../sector-sliders';
import type { SliderItem } from '@/lib/api/hooks/useWorkshop';

// ── Helpers ──────────────────────────────────────────────────────────

function renderSliders(props?: {
  sectorCodes?: string[];
  sliders?: SliderItem[];
  onChange?: (sliders: SliderItem[]) => void;
  disabled?: boolean;
}) {
  const defaultProps = {
    sectorCodes: props?.sectorCodes ?? ['S01', 'S02', 'S03'],
    sliders: props?.sliders ?? [],
    onChange: props?.onChange ?? vi.fn(),
    disabled: props?.disabled ?? false,
  };

  return render(createElement(SectorSliders, defaultProps));
}

// ── Tests ────────────────────────────────────────────────────────────

describe('SectorSliders', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a slider for each sector code', () => {
    renderSliders({ sectorCodes: ['S01', 'S02', 'S03'] });

    expect(screen.getByLabelText('S01 adjustment')).toBeInTheDocument();
    expect(screen.getByLabelText('S02 adjustment')).toBeInTheDocument();
    expect(screen.getByLabelText('S03 adjustment')).toBeInTheDocument();
  });

  it('renders sector code labels', () => {
    renderSliders({ sectorCodes: ['S01', 'S02'] });

    expect(screen.getByText('S01')).toBeInTheDocument();
    expect(screen.getByText('S02')).toBeInTheDocument();
  });

  it('displays current slider values', () => {
    renderSliders({
      sectorCodes: ['S01', 'S02'],
      sliders: [
        { sector_code: 'S01', pct_delta: 15 },
        { sector_code: 'S02', pct_delta: -20 },
      ],
    });

    expect(screen.getByText('+15%')).toBeInTheDocument();
    expect(screen.getByText('-20%')).toBeInTheDocument();
  });

  it('shows 0% when slider has no value', () => {
    renderSliders({
      sectorCodes: ['S01'],
      sliders: [],
    });

    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('calls onChange when slider value changes', () => {
    const onChange = vi.fn();
    renderSliders({
      sectorCodes: ['S01', 'S02'],
      sliders: [{ sector_code: 'S01', pct_delta: 0 }],
      onChange,
    });

    const slider = screen.getByLabelText('S01 adjustment');
    fireEvent.change(slider, { target: { value: '25' } });

    expect(onChange).toHaveBeenCalledTimes(1);
    const updatedSliders = onChange.mock.calls[0][0] as SliderItem[];
    const s01 = updatedSliders.find((s) => s.sector_code === 'S01');
    expect(s01?.pct_delta).toBe(25);
  });

  it('adds new slider item for sector without existing entry', () => {
    const onChange = vi.fn();
    renderSliders({
      sectorCodes: ['S01', 'S02'],
      sliders: [],
      onChange,
    });

    const slider = screen.getByLabelText('S02 adjustment');
    fireEvent.change(slider, { target: { value: '10' } });

    expect(onChange).toHaveBeenCalledTimes(1);
    const updatedSliders = onChange.mock.calls[0][0] as SliderItem[];
    expect(updatedSliders).toHaveLength(1);
    expect(updatedSliders[0]).toEqual({ sector_code: 'S02', pct_delta: 10 });
  });

  it('shows disabled state correctly', () => {
    renderSliders({
      sectorCodes: ['S01', 'S02'],
      disabled: true,
    });

    const slider1 = screen.getByLabelText('S01 adjustment') as HTMLInputElement;
    const slider2 = screen.getByLabelText('S02 adjustment') as HTMLInputElement;
    expect(slider1.disabled).toBe(true);
    expect(slider2.disabled).toBe(true);
  });

  it('shows empty message when no sector codes provided', () => {
    renderSliders({ sectorCodes: [] });

    expect(
      screen.getByText(/no sectors available/i)
    ).toBeInTheDocument();
  });

  it('preserves other slider values when one changes', () => {
    const onChange = vi.fn();
    renderSliders({
      sectorCodes: ['S01', 'S02'],
      sliders: [
        { sector_code: 'S01', pct_delta: 5 },
        { sector_code: 'S02', pct_delta: -10 },
      ],
      onChange,
    });

    const slider = screen.getByLabelText('S01 adjustment');
    fireEvent.change(slider, { target: { value: '20' } });

    const updatedSliders = onChange.mock.calls[0][0] as SliderItem[];
    const s01 = updatedSliders.find((s) => s.sector_code === 'S01');
    const s02 = updatedSliders.find((s) => s.sector_code === 'S02');
    expect(s01?.pct_delta).toBe(20);
    expect(s02?.pct_delta).toBe(-10);
  });
});
