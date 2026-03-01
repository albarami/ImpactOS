import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { PublicationGate } from '../publication-gate';

// ── Tests ────────────────────────────────────────────────────────────

describe('PublicationGate', () => {
  it('shows PASS heading when nffPassed is true', () => {
    render(
      createElement(PublicationGate, {
        workspaceId: 'ws-001',
        runId: 'run-001',
        nffPassed: true,
        blockingReasons: [],
      })
    );
    expect(screen.getByText(/publication gate: pass/i)).toBeInTheDocument();
  });

  it('shows green border card when passed', () => {
    const { container } = render(
      createElement(PublicationGate, {
        workspaceId: 'ws-001',
        runId: 'run-001',
        nffPassed: true,
        blockingReasons: [],
      })
    );
    const card = container.firstElementChild;
    expect(card?.className).toContain('border-emerald');
  });

  it('shows Proceed to Export link when passed', () => {
    render(
      createElement(PublicationGate, {
        workspaceId: 'ws-001',
        runId: 'run-001',
        nffPassed: true,
        blockingReasons: [],
      })
    );
    const link = screen.getByRole('link', { name: /proceed to export/i });
    expect(link).toBeInTheDocument();
    expect(link.getAttribute('href')).toBe(
      '/w/ws-001/exports/new?runId=run-001'
    );
  });

  it('shows BLOCKED heading when nffPassed is false', () => {
    render(
      createElement(PublicationGate, {
        workspaceId: 'ws-001',
        runId: 'run-001',
        nffPassed: false,
        blockingReasons: [],
      })
    );
    expect(
      screen.getByText(/publication gate: blocked/i)
    ).toBeInTheDocument();
  });

  it('shows red border card when blocked', () => {
    const { container } = render(
      createElement(PublicationGate, {
        workspaceId: 'ws-001',
        runId: 'run-001',
        nffPassed: false,
        blockingReasons: [],
      })
    );
    const card = container.firstElementChild;
    expect(card?.className).toContain('border-red');
  });

  it('shows blocking reasons list when blocked', () => {
    render(
      createElement(PublicationGate, {
        workspaceId: 'ws-001',
        runId: 'run-001',
        nffPassed: false,
        blockingReasons: [
          {
            claim_id: 'claim-001',
            current_status: 'NEEDS_EVIDENCE',
            reason: 'Claim requires supporting evidence',
          },
          {
            claim_id: 'claim-002',
            current_status: 'EXTRACTED',
            reason: 'Claim not yet reviewed',
          },
        ],
      })
    );
    expect(
      screen.getByText('Claim requires supporting evidence')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Claim not yet reviewed')
    ).toBeInTheDocument();
  });

  it('shows resolve issues text when blocked', () => {
    render(
      createElement(PublicationGate, {
        workspaceId: 'ws-001',
        runId: 'run-001',
        nffPassed: false,
        blockingReasons: [],
      })
    );
    expect(screen.getByText(/resolve issues/i)).toBeInTheDocument();
  });

  it('does not show export link when blocked', () => {
    render(
      createElement(PublicationGate, {
        workspaceId: 'ws-001',
        runId: 'run-001',
        nffPassed: false,
        blockingReasons: [],
      })
    );
    expect(
      screen.queryByRole('link', { name: /proceed to export/i })
    ).not.toBeInTheDocument();
  });
});
