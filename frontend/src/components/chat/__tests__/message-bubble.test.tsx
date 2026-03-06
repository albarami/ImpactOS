import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { createElement } from 'react';
import { MessageBubble } from '../message-bubble';
import type {
  ChatMessageResponse,
  ToolCall,
  TraceMetadata,
} from '@/lib/api/hooks/useChat';

// ── Helpers ──────────────────────────────────────────────────────────

function makeMessage(
  overrides: Partial<ChatMessageResponse> & {
    message_id: string;
    role: 'user' | 'assistant';
  }
): ChatMessageResponse {
  return {
    content: '',
    created_at: '2026-03-05T10:00:00Z',
    ...overrides,
  };
}

function renderBubble(
  message: ChatMessageResponse,
  workspaceId?: string
) {
  return render(
    createElement(MessageBubble, { message, workspaceId })
  );
}

// ── Status Badge Tests ───────────────────────────────────────────────

describe('MessageBubble – status badges', () => {
  it('renders success badge for completed run', () => {
    const msg = makeMessage({
      message_id: 'msg-s1',
      role: 'assistant',
      content: 'Run complete.',
      tool_calls: [
        {
          tool_name: 'run_engine',
          arguments: { scenario_id: 'sc-01' },
          result: {
            status: 'success',
            reason_code: 'ok',
            retryable: false,
            latency_ms: 200,
            result: { gdp_impact: 1.5 },
          },
        },
      ],
    });
    renderBubble(msg);

    const badge = screen.getByTestId('tool-status-badge-success');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('success');
    // Green styling
    expect(badge.className).toMatch(/bg-green/);
  });

  it('renders blocked badge with amber styling (not red)', () => {
    const msg = makeMessage({
      message_id: 'msg-b1',
      role: 'assistant',
      content: 'Export blocked.',
      tool_calls: [
        {
          tool_name: 'export_decision_pack',
          arguments: { run_id: 'run-01' },
          result: {
            status: 'blocked',
            reason_code: 'governance_hold',
            retryable: false,
            latency_ms: 10,
            result: {
              export_status: 'BLOCKED',
              blocking_reasons: ['No quality assessment'],
            },
          },
        },
      ],
    });
    renderBubble(msg);

    const badge = screen.getByTestId('tool-status-badge-blocked');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('blocked');
    // Amber styling, NOT red
    expect(badge.className).toMatch(/bg-amber/);
    expect(badge.className).not.toMatch(/bg-red/);
  });

  it('renders error badge with red styling', () => {
    const msg = makeMessage({
      message_id: 'msg-e1',
      role: 'assistant',
      content: 'Engine error.',
      tool_calls: [
        {
          tool_name: 'run_engine',
          arguments: { scenario_id: 'sc-fail' },
          result: {
            status: 'error',
            reason_code: 'engine_timeout',
            retryable: true,
            latency_ms: 5000,
            error_summary: 'Engine timed out after 5s',
          },
        },
      ],
    });
    renderBubble(msg);

    const badge = screen.getByTestId('tool-status-badge-error');
    expect(badge).toBeInTheDocument();
    expect(badge.className).toMatch(/bg-red/);
  });
});

// ── Blocking Reasons Tests ───────────────────────────────────────────

describe('MessageBubble – blocking reasons', () => {
  it('renders blocking reasons for blocked export', () => {
    const msg = makeMessage({
      message_id: 'msg-br1',
      role: 'assistant',
      content: 'Export blocked by governance.',
      tool_calls: [
        {
          tool_name: 'export_decision_pack',
          arguments: { run_id: 'run-01' },
          result: {
            status: 'blocked',
            reason_code: 'governance_hold',
            retryable: false,
            latency_ms: 10,
            result: {
              export_status: 'BLOCKED',
              blocking_reasons: [
                'No quality assessment',
                'Missing assumption sign-off',
              ],
            },
          },
        },
      ],
    });
    renderBubble(msg);

    expect(screen.getByText('No quality assessment')).toBeInTheDocument();
    expect(
      screen.getByText('Missing assumption sign-off')
    ).toBeInTheDocument();
  });

  it('does not render blocking reasons list when array is empty', () => {
    const msg = makeMessage({
      message_id: 'msg-br2',
      role: 'assistant',
      content: 'Success.',
      tool_calls: [
        {
          tool_name: 'export_decision_pack',
          arguments: { run_id: 'run-01' },
          result: {
            status: 'success',
            reason_code: 'ok',
            retryable: false,
            latency_ms: 100,
            result: {
              export_status: 'COMPLETED',
              blocking_reasons: [],
            },
          },
        },
      ],
    });
    renderBubble(msg);

    expect(screen.queryByTestId('blocking-reasons-list')).not.toBeInTheDocument();
  });

  it('does not render blocking reasons list when field is absent', () => {
    const msg = makeMessage({
      message_id: 'msg-br3',
      role: 'assistant',
      content: 'Success.',
      tool_calls: [
        {
          tool_name: 'run_engine',
          arguments: { scenario_id: 'sc-01' },
          result: {
            status: 'success',
            reason_code: 'ok',
            retryable: false,
            latency_ms: 100,
            result: { gdp_impact: 1.5 },
          },
        },
      ],
    });
    renderBubble(msg);

    expect(screen.queryByTestId('blocking-reasons-list')).not.toBeInTheDocument();
  });
});

// ── Deep Link Tests ──────────────────────────────────────────────────

describe('MessageBubble – deep links', () => {
  it('renders deep link for run_id in trace metadata', () => {
    const msg = makeMessage({
      message_id: 'msg-dl1',
      role: 'assistant',
      content: 'Run complete.',
      trace_metadata: {
        run_id: 'run-abc-123',
        scenario_spec_id: 'spec-001',
      },
    });
    renderBubble(msg, 'ws-001');

    const runLink = screen.getByTestId('trace-run-link');
    expect(runLink).toBeInTheDocument();
    expect(runLink).toHaveAttribute(
      'href',
      '/workspaces/ws-001/engine/runs/run-abc-123'
    );
  });

  it('renders deep link for export_id only when export is COMPLETED', () => {
    const msg = makeMessage({
      message_id: 'msg-dl2',
      role: 'assistant',
      content: 'Export done.',
      trace_metadata: {
        export_id: 'exp-001',
      },
      tool_calls: [
        {
          tool_name: 'export_decision_pack',
          arguments: { run_id: 'run-01' },
          result: {
            status: 'success',
            reason_code: 'ok',
            retryable: false,
            latency_ms: 500,
            result: { export_status: 'COMPLETED' },
          },
        },
      ],
    });
    renderBubble(msg, 'ws-001');

    const exportLink = screen.getByTestId('trace-export-link');
    expect(exportLink).toBeInTheDocument();
    expect(exportLink).toHaveAttribute(
      'href',
      '/workspaces/ws-001/exports/exp-001'
    );
  });

  it('does not render export deep link when export is BLOCKED', () => {
    const msg = makeMessage({
      message_id: 'msg-dl3',
      role: 'assistant',
      content: 'Export blocked.',
      trace_metadata: {
        export_id: 'exp-002',
      },
      tool_calls: [
        {
          tool_name: 'export_decision_pack',
          arguments: { run_id: 'run-01' },
          result: {
            status: 'blocked',
            reason_code: 'governance_hold',
            retryable: false,
            latency_ms: 10,
            result: {
              export_status: 'BLOCKED',
              blocking_reasons: ['Not ready'],
            },
          },
        },
      ],
    });
    renderBubble(msg, 'ws-001');

    expect(screen.queryByTestId('trace-export-link')).not.toBeInTheDocument();
    // The export_id should still be shown as plain text
    expect(screen.getByText('exp-002')).toBeInTheDocument();
  });
});

// ── Conditional Download Link Tests ──────────────────────────────────

describe('MessageBubble – conditional download link', () => {
  it('renders download link when export status is COMPLETED', () => {
    const msg = makeMessage({
      message_id: 'msg-cd1',
      role: 'assistant',
      content: 'Export done.',
      trace_metadata: {
        export_id: 'exp-001',
      },
      tool_calls: [
        {
          tool_name: 'export_decision_pack',
          arguments: { run_id: 'run-01' },
          result: {
            status: 'success',
            reason_code: 'ok',
            retryable: false,
            latency_ms: 500,
            result: {
              export_status: 'COMPLETED',
              download_url: '/api/v1/exports/exp-001/download',
            },
          },
        },
      ],
    });
    renderBubble(msg, 'ws-001');

    const downloadLink = screen.getByTestId('export-download-link');
    expect(downloadLink).toBeInTheDocument();
    expect(downloadLink).toHaveAttribute(
      'href',
      '/api/v1/exports/exp-001/download'
    );
  });

  it('does not render download link for blocked export', () => {
    const msg = makeMessage({
      message_id: 'msg-cd2',
      role: 'assistant',
      content: 'Export blocked.',
      tool_calls: [
        {
          tool_name: 'export_decision_pack',
          arguments: { run_id: 'run-01' },
          result: {
            status: 'blocked',
            reason_code: 'governance_hold',
            retryable: false,
            latency_ms: 10,
            result: {
              export_status: 'BLOCKED',
              blocking_reasons: ['Not ready'],
              download_url: '/api/v1/exports/exp-001/download',
            },
          },
        },
      ],
    });
    renderBubble(msg);

    expect(screen.queryByTestId('export-download-link')).not.toBeInTheDocument();
  });

  it('does not render download link for failed export', () => {
    const msg = makeMessage({
      message_id: 'msg-cd3',
      role: 'assistant',
      content: 'Export failed.',
      tool_calls: [
        {
          tool_name: 'export_decision_pack',
          arguments: { run_id: 'run-01' },
          result: {
            status: 'error',
            reason_code: 'export_failed',
            retryable: true,
            latency_ms: 3000,
            error_summary: 'PDF generation error',
            result: {
              export_status: 'FAILED',
              download_url: '/api/v1/exports/exp-001/download',
            },
          },
        },
      ],
    });
    renderBubble(msg);

    expect(screen.queryByTestId('export-download-link')).not.toBeInTheDocument();
  });
});
