import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { UploadForm } from '../upload-form';

// ── Mocks ────────────────────────────────────────────────────────────

const mockUploadMutate = vi.fn();
const mockExtractMutate = vi.fn();

vi.mock('@/lib/api/hooks/useDocuments', () => ({
  useUploadDocument: () => ({
    mutateAsync: mockUploadMutate,
    isPending: false,
  }),
  useExtractDocument: () => ({
    mutateAsync: mockExtractMutate,
    isPending: false,
  }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useParams: () => ({ workspaceId: 'ws-001' }),
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

function renderForm() {
  return render(
    createElement(
      createWrapper(),
      null,
      createElement(UploadForm, {
        workspaceId: 'ws-001',
        onUploaded: vi.fn(),
      })
    )
  );
}

// ── Tests ────────────────────────────────────────────────────────────

describe('UploadForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a file input', () => {
    renderForm();
    const fileInput = document.querySelector('input[type="file"]');
    expect(fileInput).toBeInTheDocument();
  });

  it('renders doc_type select', () => {
    renderForm();
    expect(screen.getByText('Document Type')).toBeInTheDocument();
  });

  it('renders source_type select', () => {
    renderForm();
    expect(screen.getByText('Source Type')).toBeInTheDocument();
  });

  it('renders classification select', () => {
    renderForm();
    expect(screen.getByText('Classification')).toBeInTheDocument();
  });

  it('renders language select', () => {
    renderForm();
    expect(screen.getByText('Language')).toBeInTheDocument();
  });

  it('renders a submit button', () => {
    renderForm();
    expect(
      screen.getByRole('button', { name: /upload/i })
    ).toBeInTheDocument();
  });

  it('submit button is disabled when no file is selected', () => {
    renderForm();
    const btn = screen.getByRole('button', { name: /upload/i });
    expect(btn).toBeDisabled();
  });

  it('submit button is enabled after a file is selected', async () => {
    const user = userEvent.setup();
    renderForm();

    const fileInput = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;
    const file = new File(['pdf-content'], 'test.pdf', {
      type: 'application/pdf',
    });

    await user.upload(fileInput, file);

    const btn = screen.getByRole('button', { name: /upload/i });
    expect(btn).toBeEnabled();
  });
});
