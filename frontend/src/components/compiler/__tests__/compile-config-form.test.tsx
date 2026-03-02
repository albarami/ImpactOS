import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { CompileConfigForm } from '../compile-config-form';

// ── Mocks ────────────────────────────────────────────────────────────

const mockMutateAsync = vi.fn();
const mockPush = vi.fn();

vi.mock('@/lib/api/hooks/useCompiler', () => ({
  useCompile: () => ({
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

function renderForm(props?: { workspaceId?: string; documentId?: string }) {
  return render(
    createElement(
      createWrapper(),
      null,
      createElement(CompileConfigForm, {
        workspaceId: props?.workspaceId ?? 'ws-001',
        documentId: props?.documentId ?? 'doc-001',
      })
    )
  );
}

// ── Tests ────────────────────────────────────────────────────────────

describe('CompileConfigForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders scenario name input', () => {
    renderForm();
    expect(screen.getByLabelText(/scenario name/i)).toBeInTheDocument();
  });

  it('renders model version input with helper text', () => {
    renderForm();
    expect(screen.getByLabelText(/model version/i)).toBeInTheDocument();
    expect(screen.getByText(/enter model version uuid/i)).toBeInTheDocument();
  });

  it('renders base year input', () => {
    renderForm();
    expect(screen.getByLabelText(/base year/i)).toBeInTheDocument();
  });

  it('renders start year input', () => {
    renderForm();
    expect(screen.getByLabelText(/start year/i)).toBeInTheDocument();
  });

  it('renders end year input', () => {
    renderForm();
    expect(screen.getByLabelText(/end year/i)).toBeInTheDocument();
  });

  it('displays document ID as info text', () => {
    renderForm({ documentId: 'doc-abc-123' });
    expect(screen.getByText('doc-abc-123')).toBeInTheDocument();
  });

  it('renders a submit button', () => {
    renderForm();
    expect(
      screen.getByRole('button', { name: /compile/i })
    ).toBeInTheDocument();
  });

  it('submit button is disabled when scenario name is empty', () => {
    renderForm();
    const btn = screen.getByRole('button', { name: /compile/i });
    expect(btn).toBeDisabled();
  });

  it('calls mutateAsync on form submission and navigates on success', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      compilation_id: 'comp-001',
      suggestions: [],
      high_confidence: 0,
      medium_confidence: 0,
      low_confidence: 0,
    });

    renderForm();

    // Fill in all required fields
    await user.type(screen.getByLabelText(/scenario name/i), 'My Scenario');
    await user.type(screen.getByLabelText(/model version/i), 'mv-001');
    await user.clear(screen.getByLabelText(/base year/i));
    await user.type(screen.getByLabelText(/base year/i), '2020');
    await user.clear(screen.getByLabelText(/start year/i));
    await user.type(screen.getByLabelText(/start year/i), '2025');
    await user.clear(screen.getByLabelText(/end year/i));
    await user.type(screen.getByLabelText(/end year/i), '2030');

    // Submit
    const btn = screen.getByRole('button', { name: /compile/i });
    expect(btn).toBeEnabled();
    await user.click(btn);

    expect(mockMutateAsync).toHaveBeenCalledWith({
      scenario_name: 'My Scenario',
      base_model_version_id: 'mv-001',
      base_year: 2020,
      start_year: 2025,
      end_year: 2030,
      document_id: 'doc-001',
    });

    expect(mockPush).toHaveBeenCalledWith('/w/ws-001/compilations/comp-001');
  });

  it('shows validation error when end year is before start year', async () => {
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/scenario name/i), 'Test');
    await user.type(screen.getByLabelText(/model version/i), 'mv-001');
    await user.clear(screen.getByLabelText(/base year/i));
    await user.type(screen.getByLabelText(/base year/i), '2020');
    await user.clear(screen.getByLabelText(/start year/i));
    await user.type(screen.getByLabelText(/start year/i), '2030');
    await user.clear(screen.getByLabelText(/end year/i));
    await user.type(screen.getByLabelText(/end year/i), '2025');

    const btn = screen.getByRole('button', { name: /compile/i });
    await user.click(btn);

    expect(
      screen.getByText(/end year must be greater than or equal to start year/i)
    ).toBeInTheDocument();
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });
});
