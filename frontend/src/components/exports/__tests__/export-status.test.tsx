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

function renderDisplay(props?: {
  workspaceId?: string;
  exportId?: string;
  blockingReasons?: string[];
}) {
  return render(
    createElement(
      createWrapper(),
      null,
      createElement(ExportStatusDisplay, {
        workspaceId: props?.workspaceId ?? 'ws-001',
        exportId: props?.exportId ?? 'exp-001',
        blockingReasons: props?.blockingReasons,
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

  it('shows download buttons for each format when COMPLETED (P6-6)', () => {
    mockStatusData = {
      export_id: 'exp-001',
      run_id: 'run-001',
      mode: 'SANDBOX',
      status: 'COMPLETED',
      checksums: { excel: 'sha256:abc123', pptx: 'sha256:def456' },
    };
    renderDisplay();

    // Download buttons should appear for each format
    expect(screen.getByTestId('export-download-buttons')).toBeInTheDocument();
    const excelLink = screen.getByTestId('download-excel');
    expect(excelLink).toBeInTheDocument();
    expect(excelLink).toHaveAttribute(
      'href',
      '/api/v1/workspaces/ws-001/exports/exp-001/download/excel'
    );
    expect(excelLink).toHaveTextContent(/excel/i);

    const pptxLink = screen.getByTestId('download-pptx');
    expect(pptxLink).toBeInTheDocument();
    expect(pptxLink).toHaveAttribute(
      'href',
      '/api/v1/workspaces/ws-001/exports/exp-001/download/pptx'
    );
    expect(pptxLink).toHaveTextContent(/pptx/i);
  });

  it('does not show Phase 3B placeholder (P6-6)', () => {
    mockStatusData = {
      export_id: 'exp-001',
      run_id: 'run-001',
      mode: 'SANDBOX',
      status: 'COMPLETED',
      checksums: { excel: 'sha256:abc123' },
    };
    renderDisplay();
    expect(
      screen.queryByText(/phase 3b/i)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/download not yet available/i)
    ).not.toBeInTheDocument();
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

  it('renders blocking reasons list when provided', () => {
    mockStatusData = {
      export_id: 'exp-002',
      run_id: 'run-001',
      mode: 'GOVERNED',
      status: 'BLOCKED',
      checksums: {},
    };
    renderDisplay({
      blockingReasons: ['Unresolved claims exist', 'Assumptions not approved'],
    });
    expect(screen.getByTestId('blocking-reasons')).toBeInTheDocument();
    expect(screen.getByText('Unresolved claims exist')).toBeInTheDocument();
    expect(screen.getByText('Assumptions not approved')).toBeInTheDocument();
  });

  it('shows generic BLOCKED message when no blocking reasons provided', () => {
    mockStatusData = {
      export_id: 'exp-002',
      run_id: 'run-001',
      mode: 'GOVERNED',
      status: 'BLOCKED',
      checksums: {},
    };
    renderDisplay();
    expect(
      screen.getByText(/unresolved governance issues/i)
    ).toBeInTheDocument();
    expect(screen.queryByTestId('blocking-reasons')).not.toBeInTheDocument();
  });

  it('shows generic BLOCKED message when blocking reasons is empty', () => {
    mockStatusData = {
      export_id: 'exp-002',
      run_id: 'run-001',
      mode: 'GOVERNED',
      status: 'BLOCKED',
      checksums: {},
    };
    renderDisplay({ blockingReasons: [] });
    expect(
      screen.getByText(/unresolved governance issues/i)
    ).toBeInTheDocument();
    expect(screen.queryByTestId('blocking-reasons')).not.toBeInTheDocument();
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
    expect(screen.getByText('Generating export...')).toBeInTheDocument();
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
    expect(screen.getByText('Generating export...')).toBeInTheDocument();
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
