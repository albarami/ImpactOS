import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { RunForm } from '../run-form';

// ── Mocks ────────────────────────────────────────────────────────────

const mockMutateAsync = vi.fn();
const mockPush = vi.fn();

vi.mock('@/lib/api/hooks/useRuns', () => ({
  useCreateRun: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

// ── Helpers ──────────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function renderForm(props?: { workspaceId?: string }) {
  return render(
    createElement(
      createWrapper(),
      null,
      createElement(RunForm, {
        workspaceId: props?.workspaceId ?? 'ws-001',
      })
    )
  );
}

/**
 * Helper to set textarea value — userEvent.type treats brackets as
 * keyboard modifiers, so we use fireEvent.change for JSON inputs.
 */
function setTextareaValue(element: HTMLElement, value: string) {
  fireEvent.change(element, { target: { value } });
}

// ── Tests ────────────────────────────────────────────────────────────

describe('RunForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders model version input', () => {
    renderForm();
    expect(screen.getByLabelText(/model version/i)).toBeInTheDocument();
  });

  it('renders base year input', () => {
    renderForm();
    expect(screen.getByLabelText(/base year/i)).toBeInTheDocument();
  });

  it('renders annual shocks textarea', () => {
    renderForm();
    expect(screen.getByLabelText(/annual shocks/i)).toBeInTheDocument();
  });

  it('renders satellite coefficients textarea', () => {
    renderForm();
    expect(screen.getByLabelText(/satellite coefficients/i)).toBeInTheDocument();
  });

  it('renders deflators textarea (optional)', () => {
    renderForm();
    expect(screen.getByLabelText(/deflators/i)).toBeInTheDocument();
  });

  it('renders submit button', () => {
    renderForm();
    expect(
      screen.getByRole('button', { name: /run/i })
    ).toBeInTheDocument();
  });

  it('shows JSON validation error for invalid annual_shocks', async () => {
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/model version/i), 'mv-001');
    setTextareaValue(screen.getByLabelText(/annual shocks/i), 'not valid json');

    const btn = screen.getByRole('button', { name: /run/i });
    await user.click(btn);

    expect(
      screen.getByText(/invalid json in annual shocks/i)
    ).toBeInTheDocument();
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it('shows JSON validation error for invalid satellite_coefficients', async () => {
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/model version/i), 'mv-001');
    setTextareaValue(
      screen.getByLabelText(/annual shocks/i),
      '{"2025": [100]}'
    );
    setTextareaValue(
      screen.getByLabelText(/satellite coefficients/i),
      'not valid json'
    );

    const btn = screen.getByRole('button', { name: /run/i });
    await user.click(btn);

    expect(
      screen.getByText(/invalid json in satellite coefficients/i)
    ).toBeInTheDocument();
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it('submits valid form and navigates to run results', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      run_id: 'run-001',
      result_sets: [],
      snapshot: { run_id: 'run-001', model_version_id: 'mv-001' },
    });

    renderForm();

    await user.type(screen.getByLabelText(/model version/i), 'mv-001');
    await user.clear(screen.getByLabelText(/base year/i));
    await user.type(screen.getByLabelText(/base year/i), '2020');

    setTextareaValue(
      screen.getByLabelText(/annual shocks/i),
      '{"2025": [100, 200]}'
    );
    setTextareaValue(
      screen.getByLabelText(/satellite coefficients/i),
      '{"jobs_coeff": [0.1, 0.2], "import_ratio": [0.3, 0.4], "va_ratio": [0.7, 0.6]}'
    );

    const btn = screen.getByRole('button', { name: /run/i });
    await user.click(btn);

    expect(mockMutateAsync).toHaveBeenCalledWith({
      model_version_id: 'mv-001',
      base_year: 2020,
      annual_shocks: { '2025': [100, 200] },
      satellite_coefficients: {
        jobs_coeff: [0.1, 0.2],
        import_ratio: [0.3, 0.4],
        va_ratio: [0.7, 0.6],
      },
    });

    expect(mockPush).toHaveBeenCalledWith('/w/ws-001/runs/run-001');
  });

  it('includes optional deflators when provided', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      run_id: 'run-002',
      result_sets: [],
      snapshot: { run_id: 'run-002', model_version_id: 'mv-001' },
    });

    renderForm();

    await user.type(screen.getByLabelText(/model version/i), 'mv-001');

    setTextareaValue(
      screen.getByLabelText(/annual shocks/i),
      '{"2025": [100]}'
    );
    setTextareaValue(
      screen.getByLabelText(/satellite coefficients/i),
      '{"jobs_coeff": [0.1], "import_ratio": [0.3], "va_ratio": [0.7]}'
    );
    setTextareaValue(
      screen.getByLabelText(/deflators/i),
      '{"2025": 1.02}'
    );

    const btn = screen.getByRole('button', { name: /run/i });
    await user.click(btn);

    expect(mockMutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        deflators: { '2025': 1.02 },
      })
    );

    expect(mockPush).toHaveBeenCalledWith('/w/ws-001/runs/run-002');
  });

  it('shows API error on failure', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockRejectedValueOnce(new Error('Engine failed'));

    renderForm();

    await user.type(screen.getByLabelText(/model version/i), 'mv-001');

    setTextareaValue(
      screen.getByLabelText(/annual shocks/i),
      '{"2025": [100]}'
    );
    setTextareaValue(
      screen.getByLabelText(/satellite coefficients/i),
      '{"jobs_coeff": [0.1], "import_ratio": [0.3], "va_ratio": [0.7]}'
    );

    const btn = screen.getByRole('button', { name: /run/i });
    await user.click(btn);

    expect(await screen.findByText(/engine failed/i)).toBeInTheDocument();
  });
});
