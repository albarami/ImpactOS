import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { AssumptionCreate } from '../assumption-create';
import { AssumptionApprove } from '../assumption-approve';

// ── Mocks ────────────────────────────────────────────────────────────

const mockCreateMutateAsync = vi.fn();
const mockApproveMutateAsync = vi.fn();
let mockCreatePending = false;
let mockApprovePending = false;

vi.mock('@/lib/api/hooks/useGovernance', () => ({
  useCreateAssumption: () => ({
    mutateAsync: mockCreateMutateAsync,
    isPending: mockCreatePending,
  }),
  useApproveAssumption: () => ({
    mutateAsync: mockApproveMutateAsync,
    isPending: mockApprovePending,
  }),
}));

vi.mock('@/lib/auth', () => ({
  DEV_USER_ID: '00000000-0000-7000-8000-000000000001',
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

// ── AssumptionCreate Tests ──────────────────────────────────────────

describe('AssumptionCreate', () => {
  const mockOnCreated = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockCreatePending = false;
  });

  function renderCreateForm(props?: { workspaceId?: string }) {
    return render(
      createElement(
        createWrapper(),
        null,
        createElement(AssumptionCreate, {
          workspaceId: props?.workspaceId ?? 'ws-001',
          onCreated: mockOnCreated,
        })
      )
    );
  }

  it('renders type select field', () => {
    renderCreateForm();
    expect(screen.getByLabelText(/type/i)).toBeInTheDocument();
  });

  it('renders value input', () => {
    renderCreateForm();
    expect(screen.getByLabelText(/^value$/i)).toBeInTheDocument();
  });

  it('renders units input', () => {
    renderCreateForm();
    expect(screen.getByLabelText(/units/i)).toBeInTheDocument();
  });

  it('renders justification textarea', () => {
    renderCreateForm();
    expect(screen.getByLabelText(/justification/i)).toBeInTheDocument();
  });

  it('renders create assumption button', () => {
    renderCreateForm();
    expect(
      screen.getByRole('button', { name: /create assumption/i })
    ).toBeInTheDocument();
  });

  it('submits form and calls onCreated', async () => {
    const user = userEvent.setup();
    mockCreateMutateAsync.mockResolvedValueOnce({
      assumption_id: 'assum-001',
      status: 'DRAFT',
    });

    renderCreateForm();

    // Fill in the native select
    const typeSelect = screen.getByLabelText(/type/i);
    await user.selectOptions(typeSelect, 'IMPORT_SHARE');

    const valueInput = screen.getByLabelText(/^value$/i);
    await user.clear(valueInput);
    await user.type(valueInput, '0.35');

    await user.type(screen.getByLabelText(/units/i), 'ratio');
    await user.type(
      screen.getByLabelText(/justification/i),
      'Based on import data'
    );

    await user.click(
      screen.getByRole('button', { name: /create assumption/i })
    );

    expect(mockCreateMutateAsync).toHaveBeenCalledWith({
      type: 'IMPORT_SHARE',
      value: 0.35,
      units: 'ratio',
      justification: 'Based on import data',
    });
    expect(mockOnCreated).toHaveBeenCalledWith('assum-001');
  });

  it('shows error message on failure', async () => {
    const user = userEvent.setup();
    mockCreateMutateAsync.mockRejectedValueOnce(
      new Error('Validation failed')
    );

    renderCreateForm();

    const typeSelect = screen.getByLabelText(/type/i);
    await user.selectOptions(typeSelect, 'PHASING');

    const valueInput = screen.getByLabelText(/^value$/i);
    await user.clear(valueInput);
    await user.type(valueInput, '0.5');

    await user.type(screen.getByLabelText(/units/i), '%');
    await user.type(screen.getByLabelText(/justification/i), 'test');

    await user.click(
      screen.getByRole('button', { name: /create assumption/i })
    );

    expect(
      await screen.findByText(/validation failed/i)
    ).toBeInTheDocument();
  });
});

// ── AssumptionApprove Tests ─────────────────────────────────────────

describe('AssumptionApprove', () => {
  const mockOnApproved = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockApprovePending = false;
  });

  function renderApproveForm(props?: {
    workspaceId?: string;
    assumptionId?: string;
  }) {
    return render(
      createElement(
        createWrapper(),
        null,
        createElement(AssumptionApprove, {
          workspaceId: props?.workspaceId ?? 'ws-001',
          assumptionId: props?.assumptionId ?? 'assum-001',
          onApproved: mockOnApproved,
        })
      )
    );
  }

  it('renders range_min input', () => {
    renderApproveForm();
    expect(screen.getByLabelText(/range min/i)).toBeInTheDocument();
  });

  it('renders range_max input', () => {
    renderApproveForm();
    expect(screen.getByLabelText(/range max/i)).toBeInTheDocument();
  });

  it('renders approve button', () => {
    renderApproveForm();
    expect(
      screen.getByRole('button', { name: /approve/i })
    ).toBeInTheDocument();
  });

  it('submits approval with actor as DEV_USER_ID', async () => {
    const user = userEvent.setup();
    mockApproveMutateAsync.mockResolvedValueOnce({
      assumption_id: 'assum-001',
      status: 'APPROVED',
      range_min: 0.3,
      range_max: 0.4,
    });

    renderApproveForm({ assumptionId: 'assum-001' });

    const minInput = screen.getByLabelText(/range min/i);
    await user.clear(minInput);
    await user.type(minInput, '0.3');

    const maxInput = screen.getByLabelText(/range max/i);
    await user.clear(maxInput);
    await user.type(maxInput, '0.4');

    await user.click(screen.getByRole('button', { name: /approve/i }));

    expect(mockApproveMutateAsync).toHaveBeenCalledWith({
      assumption_id: 'assum-001',
      range_min: 0.3,
      range_max: 0.4,
      actor: '00000000-0000-7000-8000-000000000001',
    });
    expect(mockOnApproved).toHaveBeenCalled();
  });

  it('validates range_max >= range_min', async () => {
    const user = userEvent.setup();

    renderApproveForm();

    const minInput = screen.getByLabelText(/range min/i);
    await user.clear(minInput);
    await user.type(minInput, '0.5');

    const maxInput = screen.getByLabelText(/range max/i);
    await user.clear(maxInput);
    await user.type(maxInput, '0.3');

    await user.click(screen.getByRole('button', { name: /approve/i }));

    expect(
      screen.getByText(/range max must be .* range min/i)
    ).toBeInTheDocument();
    expect(mockApproveMutateAsync).not.toHaveBeenCalled();
  });

  it('shows error message on failure', async () => {
    const user = userEvent.setup();
    mockApproveMutateAsync.mockRejectedValueOnce(
      new Error('Approval failed')
    );

    renderApproveForm();

    const minInput = screen.getByLabelText(/range min/i);
    await user.clear(minInput);
    await user.type(minInput, '0.1');

    const maxInput = screen.getByLabelText(/range max/i);
    await user.clear(maxInput);
    await user.type(maxInput, '0.2');

    await user.click(screen.getByRole('button', { name: /approve/i }));

    expect(
      await screen.findByText(/approval failed/i)
    ).toBeInTheDocument();
  });
});
