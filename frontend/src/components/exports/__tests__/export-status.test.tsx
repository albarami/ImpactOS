import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { ExportStatusDisplay } from '../export-status';
import type { ExportStatusResponse } from '@/lib/api/hooks/useExports';

// ── Mocks ────────────────────────────────────────────────────────────

let mockStatusData: ExportStatusResponse | undefined;
let mockStatusLoading = false;
let mockStatusError = false;

vi.mock('@/lib/api/hooks/useExports', () => ({
  useExportStatus: () => ({
    data: mockStatusData,
    isLoading: mockStatusLoading,
    isError: mockStatusError,
  }),
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

function renderDisplay(props?: { workspaceId?: string; exportId?: string }) {
  return render(
    createElement(
      createWrapper(),
      null,
      createElement(ExportStatusDisplay, {
        workspaceId: props?.workspaceId ?? 'ws-001',
        exportId: props?.exportId ?? 'exp-001',
      })
    )
  );
}

// ── Tests ────────────────────────────────────────────────────────────

describe('ExportStatusDisplay', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStatusData = undefined;
    mockStatusLoading = false;
    mockStatusError = false;
  });

  it('shows loading skeleton while fetching', () => {
    mockStatusLoading = true;
    renderDisplay();
    expect(screen.getByTestId('export-loading')).toBeInTheDocument();
  });

  it('shows error message on fetch failure', () => {
    mockStatusError = true;
    renderDisplay();
    expect(
      screen.getByText(/failed to load export status/i)
    ).toBeInTheDocument();
  });

  // ── COMPLETED ────────────────────────────────────────────────────

  it('shows green COMPLETED badge when status is COMPLETED', () => {
    mockStatusData = {
      export_id: 'exp-001',
      run_id: 'run-001',
      mode: 'SANDBOX',
      status: 'COMPLETED',
      checksums: { excel: 'sha256:abc123' },
    };
    renderDisplay();
    expect(screen.getByText('COMPLETED')).toBeInTheDocument();
  });

  it('shows checksums table for COMPLETED export', () => {
    mockStatusData = {
      export_id: 'exp-001',
      run_id: 'run-001',
      mode: 'SANDBOX',
      status: 'COMPLETED',
      checksums: { excel: 'sha256:abc123', pptx: 'sha256:def456' },
    };
    renderDisplay();
    expect(screen.getByText('excel')).toBeInTheDocument();
    expect(screen.getByText('sha256:abc123')).toBeInTheDocument();
    expect(screen.getByText('pptx')).toBeInTheDocument();
    expect(screen.getByText('sha256:def456')).toBeInTheDocument();
  });

  it('shows Phase 3B message for COMPLETED export', () => {
    mockStatusData = {
      export_id: 'exp-001',
      run_id: 'run-001',
      mode: 'SANDBOX',
      status: 'COMPLETED',
      checksums: { excel: 'sha256:abc123' },
    };
    renderDisplay();
    expect(
      screen.getByText(/download not yet available/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/phase 3b/i)).toBeInTheDocument();
  });

  // ── BLOCKED ──────────────────────────────────────────────────────

  it('shows red BLOCKED badge when status is BLOCKED', () => {
    mockStatusData = {
      export_id: 'exp-002',
      run_id: 'run-001',
      mode: 'GOVERNED',
      status: 'BLOCKED',
      checksums: {},
    };
    renderDisplay();
    expect(screen.getByText('BLOCKED')).toBeInTheDocument();
  });

  // ── FAILED ───────────────────────────────────────────────────────

  it('shows red FAILED badge when status is FAILED', () => {
    mockStatusData = {
      export_id: 'exp-003',
      run_id: 'run-001',
      mode: 'SANDBOX',
      status: 'FAILED',
      checksums: {},
    };
    renderDisplay();
    expect(screen.getByText('FAILED')).toBeInTheDocument();
    expect(screen.getByText(/export generation failed/i)).toBeInTheDocument();
  });

  // ── PENDING ──────────────────────────────────────────────────────

  it('shows amber PENDING badge with loading indicator', () => {
    mockStatusData = {
      export_id: 'exp-004',
      run_id: 'run-001',
      mode: 'SANDBOX',
      status: 'PENDING',
      checksums: {},
    };
    renderDisplay();
    expect(screen.getByText('PENDING')).toBeInTheDocument();
    expect(screen.getByTestId('export-polling')).toBeInTheDocument();
  });

  // ── GENERATING ───────────────────────────────────────────────────

  it('shows amber GENERATING badge with loading indicator', () => {
    mockStatusData = {
      export_id: 'exp-005',
      run_id: 'run-001',
      mode: 'GOVERNED',
      status: 'GENERATING',
      checksums: {},
    };
    renderDisplay();
    expect(screen.getByText('GENERATING')).toBeInTheDocument();
    expect(screen.getByTestId('export-polling')).toBeInTheDocument();
  });

  // ── Metadata ─────────────────────────────────────────────────────

  it('displays export_id and run_id', () => {
    mockStatusData = {
      export_id: 'exp-001',
      run_id: 'run-001',
      mode: 'SANDBOX',
      status: 'COMPLETED',
      checksums: {},
    };
    renderDisplay();
    expect(screen.getByText('exp-001')).toBeInTheDocument();
    expect(screen.getByText('run-001')).toBeInTheDocument();
  });

  it('displays mode', () => {
    mockStatusData = {
      export_id: 'exp-001',
      run_id: 'run-001',
      mode: 'GOVERNED',
      status: 'COMPLETED',
      checksums: {},
    };
    renderDisplay();
    expect(screen.getByText('GOVERNED')).toBeInTheDocument();
  });
});
