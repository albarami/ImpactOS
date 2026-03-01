import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { ScenarioCreateForm } from '../create-form';

// ── Mocks ────────────────────────────────────────────────────────────

const mockMutateAsync = vi.fn();
const mockPush = vi.fn();

vi.mock('@/lib/api/hooks/useScenarios', () => ({
  useCreateScenario: () => ({
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

function renderForm(props?: { workspaceId?: string; compilationId?: string }) {
  return render(
    createElement(
      createWrapper(),
      null,
      createElement(ScenarioCreateForm, {
        workspaceId: props?.workspaceId ?? 'ws-001',
        compilationId: props?.compilationId,
      })
    )
  );
}

// ── Tests ────────────────────────────────────────────────────────────

describe('ScenarioCreateForm', () => {
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

  it('renders a submit button', () => {
    renderForm();
    expect(
      screen.getByRole('button', { name: /create scenario/i })
    ).toBeInTheDocument();
  });

  it('submit button is disabled when scenario name is empty', () => {
    renderForm();
    const btn = screen.getByRole('button', { name: /create scenario/i });
    expect(btn).toBeDisabled();
  });

  it('calls mutateAsync on form submission and navigates on success', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      scenario_spec_id: 'sc-001',
      version: 1,
      name: 'My Scenario',
    });

    renderForm();

    await user.type(screen.getByLabelText(/scenario name/i), 'My Scenario');
    await user.type(screen.getByLabelText(/model version/i), 'mv-001');
    await user.clear(screen.getByLabelText(/base year/i));
    await user.type(screen.getByLabelText(/base year/i), '2020');
    await user.clear(screen.getByLabelText(/start year/i));
    await user.type(screen.getByLabelText(/start year/i), '2025');
    await user.clear(screen.getByLabelText(/end year/i));
    await user.type(screen.getByLabelText(/end year/i), '2030');

    const btn = screen.getByRole('button', { name: /create scenario/i });
    expect(btn).toBeEnabled();
    await user.click(btn);

    expect(mockMutateAsync).toHaveBeenCalledWith({
      name: 'My Scenario',
      base_model_version_id: 'mv-001',
      base_year: 2020,
      start_year: 2025,
      end_year: 2030,
    });

    expect(mockPush).toHaveBeenCalledWith('/w/ws-001/scenarios/sc-001');
  });

  it('includes compilationId in redirect URL when provided', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      scenario_spec_id: 'sc-001',
      version: 1,
      name: 'My Scenario',
    });

    renderForm({ compilationId: 'comp-123' });

    await user.type(screen.getByLabelText(/scenario name/i), 'My Scenario');
    await user.type(screen.getByLabelText(/model version/i), 'mv-001');
    await user.clear(screen.getByLabelText(/base year/i));
    await user.type(screen.getByLabelText(/base year/i), '2020');
    await user.clear(screen.getByLabelText(/start year/i));
    await user.type(screen.getByLabelText(/start year/i), '2025');
    await user.clear(screen.getByLabelText(/end year/i));
    await user.type(screen.getByLabelText(/end year/i), '2030');

    const btn = screen.getByRole('button', { name: /create scenario/i });
    await user.click(btn);

    expect(mockPush).toHaveBeenCalledWith(
      '/w/ws-001/scenarios/sc-001?compilationId=comp-123'
    );
  });

  it('redirects without compilationId when not provided', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockResolvedValueOnce({
      scenario_spec_id: 'sc-001',
      version: 1,
      name: 'My Scenario',
    });

    renderForm();

    await user.type(screen.getByLabelText(/scenario name/i), 'My Scenario');
    await user.type(screen.getByLabelText(/model version/i), 'mv-001');
    await user.clear(screen.getByLabelText(/base year/i));
    await user.type(screen.getByLabelText(/base year/i), '2020');
    await user.clear(screen.getByLabelText(/start year/i));
    await user.type(screen.getByLabelText(/start year/i), '2025');
    await user.clear(screen.getByLabelText(/end year/i));
    await user.type(screen.getByLabelText(/end year/i), '2030');

    const btn = screen.getByRole('button', { name: /create scenario/i });
    await user.click(btn);

    // URL should NOT contain compilationId
    expect(mockPush).toHaveBeenCalledWith('/w/ws-001/scenarios/sc-001');
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

    const btn = screen.getByRole('button', { name: /create scenario/i });
    await user.click(btn);

    expect(
      screen.getByText(/end year must be greater than or equal to start year/i)
    ).toBeInTheDocument();
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it('shows API error on failure', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockRejectedValueOnce(new Error('Server error'));

    renderForm();

    await user.type(screen.getByLabelText(/scenario name/i), 'Fail Scenario');
    await user.type(screen.getByLabelText(/model version/i), 'mv-001');

    const btn = screen.getByRole('button', { name: /create scenario/i });
    await user.click(btn);

    expect(await screen.findByText(/server error/i)).toBeInTheDocument();
  });
});
