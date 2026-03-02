import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { ExportForm } from '../export-form';

// ── Mocks ────────────────────────────────────────────────────────────

const mockMutateAsync = vi.fn();
const mockPush = vi.fn();

vi.mock('@/lib/api/hooks/useExports', () => ({
  useCreateExport: () => ({
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

function renderForm(props?: { workspaceId?: string; runId?: string }) {
  return render(
    createElement(
      createWrapper(),
      null,
      createElement(ExportForm, {
        workspaceId: props?.workspaceId ?? 'ws-001',
        runId: props?.runId ?? 'run-001',
      })
    )
  );
}

function setTextareaValue(element: HTMLElement, value: string) {
  fireEvent.change(element, { target: { value } });
}

// ── Tests ────────────────────────────────────────────────────────────

describe('ExportForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders run_id as read-only text', () => {
    renderForm();
    expect(screen.getByText('run-001')).toBeInTheDocument();
  });

  it('renders mode select with SANDBOX and GOVERNED options', () => {
    renderForm();
    const select = screen.getByLabelText(/mode/i) as HTMLSelectElement;
    expect(select).toBeInTheDocument();

    const options = select.querySelectorAll('option');
    const optionValues = Array.from(options).map((o) => o.value);
    expect(optionValues).toContain('SANDBOX');
    expect(optionValues).toContain('GOVERNED');
  });

  it('renders format checkboxes for excel and pptx', () => {
    renderForm();
    expect(screen.getByLabelText(/excel/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/pptx/i)).toBeInTheDocument();
  });

  it('renders pack_data textarea', () => {
    renderForm();
    expect(screen.getByLabelText(/pack data/i)).toBeInTheDocument();
  });

  it('renders submit button', () => {
    renderForm();
    expect(
      screen.getByRole('button', { name: /create export/i })
    ).toBeInTheDocument();
  });

  it('submit button is disabled when no format selected', () => {
    renderForm();
    const btn = screen.getByRole('button', { name: /create export/i });
    expect(btn).toBeDisabled();
  });

  it('submit button is enabled when at least one format is selected', async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByLabelText(/excel/i));

    const btn = screen.getByRole('button', { name: /create export/i });
    expect(btn).toBeEnabled();
  });

  it('submits with correct payload and navigates on success', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      export_id: 'exp-001',
      status: 'COMPLETED',
      checksums: { excel: 'sha256:abc' },
      blocking_reasons: [],
    });

    renderForm();

    // Select excel format
    await user.click(screen.getByLabelText(/excel/i));

    // Set pack_data
    setTextareaValue(
      screen.getByLabelText(/pack data/i),
      '{"scenario_name": "Test", "base_year": 2025, "currency": "SAR"}'
    );

    // Submit
    const btn = screen.getByRole('button', { name: /create export/i });
    await user.click(btn);

    expect(mockMutateAsync).toHaveBeenCalledWith({
      run_id: 'run-001',
      mode: 'SANDBOX',
      export_formats: ['excel'],
      pack_data: { scenario_name: 'Test', base_year: 2025, currency: 'SAR' },
    });

    expect(mockPush).toHaveBeenCalledWith('/w/ws-001/exports/exp-001');
  });

  it('submits with GOVERNED mode when selected', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      export_id: 'exp-002',
      status: 'COMPLETED',
      checksums: {},
      blocking_reasons: [],
    });

    renderForm();

    // Change mode to GOVERNED
    await user.selectOptions(screen.getByLabelText(/mode/i), 'GOVERNED');

    // Select both formats
    await user.click(screen.getByLabelText(/excel/i));
    await user.click(screen.getByLabelText(/pptx/i));

    // Set pack_data
    setTextareaValue(screen.getByLabelText(/pack data/i), '{}');

    const btn = screen.getByRole('button', { name: /create export/i });
    await user.click(btn);

    expect(mockMutateAsync).toHaveBeenCalledWith({
      run_id: 'run-001',
      mode: 'GOVERNED',
      export_formats: ['excel', 'pptx'],
      pack_data: {},
    });
  });

  it('shows JSON validation error for invalid pack_data', async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByLabelText(/excel/i));
    setTextareaValue(screen.getByLabelText(/pack data/i), 'not valid json');

    const btn = screen.getByRole('button', { name: /create export/i });
    await user.click(btn);

    expect(
      screen.getByText(/invalid json in pack data/i)
    ).toBeInTheDocument();
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it('treats empty pack_data as empty object', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      export_id: 'exp-003',
      status: 'COMPLETED',
      checksums: {},
      blocking_reasons: [],
    });

    renderForm();

    await user.click(screen.getByLabelText(/excel/i));

    const btn = screen.getByRole('button', { name: /create export/i });
    await user.click(btn);

    expect(mockMutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        pack_data: {},
      })
    );
  });

  it('shows API error on failure', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockRejectedValueOnce(new Error('Export creation failed'));

    renderForm();

    await user.click(screen.getByLabelText(/excel/i));

    const btn = screen.getByRole('button', { name: /create export/i });
    await user.click(btn);

    expect(
      await screen.findByText(/export creation failed/i)
    ).toBeInTheDocument();
  });
});
