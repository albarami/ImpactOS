import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { ExtractionStatus } from '../extraction-status';

// ── Mocks ────────────────────────────────────────────────────────────

const mockUseJobStatus = vi.fn();

vi.mock('@/lib/api/hooks/useDocuments', () => ({
  useJobStatus: (...args: unknown[]) => mockUseJobStatus(...args),
}));

// ── Tests ────────────────────────────────────────────────────────────

describe('ExtractionStatus', () => {
  const onComplete = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when jobId is null', () => {
    mockUseJobStatus.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });

    const { container } = render(
      createElement(ExtractionStatus, {
        workspaceId: 'ws-001',
        jobId: null,
        onComplete,
      })
    );

    expect(container.innerHTML).toBe('');
  });

  it('shows "Queued" state with skeleton', () => {
    mockUseJobStatus.mockReturnValue({
      data: { job_id: 'job-1', doc_id: 'doc-1', status: 'QUEUED', error_message: null },
      isLoading: false,
      isError: false,
    });

    render(
      createElement(ExtractionStatus, {
        workspaceId: 'ws-001',
        jobId: 'job-1',
        onComplete,
      })
    );

    expect(screen.getByText(/queued/i)).toBeInTheDocument();
    expect(document.querySelector('[data-slot="skeleton"]')).toBeInTheDocument();
  });

  it('shows "Extracting" state with progress', () => {
    mockUseJobStatus.mockReturnValue({
      data: { job_id: 'job-1', doc_id: 'doc-1', status: 'RUNNING', error_message: null },
      isLoading: false,
      isError: false,
    });

    render(
      createElement(ExtractionStatus, {
        workspaceId: 'ws-001',
        jobId: 'job-1',
        onComplete,
      })
    );

    expect(screen.getByText(/extracting/i)).toBeInTheDocument();
    expect(document.querySelector('[data-slot="progress"]')).toBeInTheDocument();
  });

  it('shows success badge and calls onComplete when COMPLETED', () => {
    mockUseJobStatus.mockReturnValue({
      data: { job_id: 'job-1', doc_id: 'doc-1', status: 'COMPLETED', error_message: null },
      isLoading: false,
      isError: false,
    });

    render(
      createElement(ExtractionStatus, {
        workspaceId: 'ws-001',
        jobId: 'job-1',
        onComplete,
      })
    );

    expect(screen.getByText(/complete/i)).toBeInTheDocument();
    expect(onComplete).toHaveBeenCalledWith('doc-1');
  });

  it('shows error alert when FAILED', () => {
    mockUseJobStatus.mockReturnValue({
      data: {
        job_id: 'job-1',
        doc_id: 'doc-1',
        status: 'FAILED',
        error_message: 'PDF parsing failed',
      },
      isLoading: false,
      isError: false,
    });

    render(
      createElement(ExtractionStatus, {
        workspaceId: 'ws-001',
        jobId: 'job-1',
        onComplete,
      })
    );

    expect(screen.getByText('Extraction Failed')).toBeInTheDocument();
    expect(screen.getByText('PDF parsing failed')).toBeInTheDocument();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('shows a retry button when FAILED', () => {
    mockUseJobStatus.mockReturnValue({
      data: {
        job_id: 'job-1',
        doc_id: 'doc-1',
        status: 'FAILED',
        error_message: 'Parse error',
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(
      createElement(ExtractionStatus, {
        workspaceId: 'ws-001',
        jobId: 'job-1',
        onComplete,
      })
    );

    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});
