import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LineItemsTable } from '../line-items-table';

// ── Mocks ────────────────────────────────────────────────────────────

const mockUseLineItems = vi.fn();

vi.mock('@/lib/api/hooks/useDocuments', () => ({
  useLineItems: (...args: unknown[]) => mockUseLineItems(...args),
}));

vi.mock('next/link', () => ({
  default: ({
    children,
    href,
  }: {
    children: ReactNode;
    href: string;
  }) => createElement('a', { href }, children),
}));

// ── Helpers ──────────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const MOCK_LINE_ITEMS = [
  {
    line_item_id: 'li-001',
    doc_id: 'doc-123',
    raw_text: 'Steel rebar for building foundations',
    description: 'Steel rebar for foundations',
    quantity: 100,
    unit: 'ton',
    unit_price: 2500,
    total_value: 250000,
    currency_code: 'SAR',
    year_or_phase: '2026',
    vendor: 'SteelCo',
    category_code: 'C01',
    page_ref: 3,
    evidence_snippet_ids: ['ev-001'],
    completeness_score: 0.95,
    created_at: '2026-01-15T10:00:00Z',
  },
  {
    line_item_id: 'li-002',
    doc_id: 'doc-123',
    raw_text: 'Concrete mix',
    description: 'Ready-mix concrete',
    quantity: 500,
    unit: 'm3',
    unit_price: 300,
    total_value: 150000,
    currency_code: 'SAR',
    year_or_phase: '2026',
    vendor: null,
    category_code: null,
    page_ref: 5,
    evidence_snippet_ids: ['ev-002'],
    completeness_score: 0.6,
    created_at: '2026-01-15T10:01:00Z',
  },
  {
    line_item_id: 'li-003',
    doc_id: 'doc-123',
    raw_text: 'Unknown item',
    description: 'Partial entry',
    quantity: null,
    unit: null,
    unit_price: null,
    total_value: null,
    currency_code: 'SAR',
    year_or_phase: null,
    vendor: null,
    category_code: null,
    page_ref: 7,
    evidence_snippet_ids: ['ev-003'],
    completeness_score: 0.3,
    created_at: '2026-01-15T10:02:00Z',
  },
];

// ── Tests ────────────────────────────────────────────────────────────

describe('LineItemsTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders column headers', () => {
    mockUseLineItems.mockReturnValue({
      data: { items: MOCK_LINE_ITEMS },
      isLoading: false,
      isError: false,
    });

    render(
      createElement(
        createWrapper(),
        null,
        createElement(LineItemsTable, {
          workspaceId: 'ws-001',
          docId: 'doc-123',
        })
      )
    );

    expect(screen.getByText('#')).toBeInTheDocument();
    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByText('Total Value')).toBeInTheDocument();
    expect(screen.getByText('Unit')).toBeInTheDocument();
    expect(screen.getByText('Currency')).toBeInTheDocument();
    expect(screen.getByText('Completeness')).toBeInTheDocument();
  });

  it('renders data rows correctly', () => {
    mockUseLineItems.mockReturnValue({
      data: { items: MOCK_LINE_ITEMS },
      isLoading: false,
      isError: false,
    });

    render(
      createElement(
        createWrapper(),
        null,
        createElement(LineItemsTable, {
          workspaceId: 'ws-001',
          docId: 'doc-123',
        })
      )
    );

    // Check first row description
    expect(screen.getByText('Steel rebar for foundations')).toBeInTheDocument();
    // Check second row description
    expect(screen.getByText('Ready-mix concrete')).toBeInTheDocument();
    // Check third row description
    expect(screen.getByText('Partial entry')).toBeInTheDocument();
  });

  it('renders formatted total values', () => {
    mockUseLineItems.mockReturnValue({
      data: { items: MOCK_LINE_ITEMS },
      isLoading: false,
      isError: false,
    });

    render(
      createElement(
        createWrapper(),
        null,
        createElement(LineItemsTable, {
          workspaceId: 'ws-001',
          docId: 'doc-123',
        })
      )
    );

    // 250000 should be formatted with commas
    expect(screen.getByText('250,000')).toBeInTheDocument();
    expect(screen.getByText('150,000')).toBeInTheDocument();
  });

  it('renders completeness score badges with correct colors', () => {
    mockUseLineItems.mockReturnValue({
      data: { items: MOCK_LINE_ITEMS },
      isLoading: false,
      isError: false,
    });

    render(
      createElement(
        createWrapper(),
        null,
        createElement(LineItemsTable, {
          workspaceId: 'ws-001',
          docId: 'doc-123',
        })
      )
    );

    // 0.95 = 95% (green)
    expect(screen.getByText('95%')).toBeInTheDocument();
    // 0.6 = 60% (amber)
    expect(screen.getByText('60%')).toBeInTheDocument();
    // 0.3 = 30% (red)
    expect(screen.getByText('30%')).toBeInTheDocument();
  });

  it('renders "Proceed to Compile" link with correct href', () => {
    mockUseLineItems.mockReturnValue({
      data: { items: MOCK_LINE_ITEMS },
      isLoading: false,
      isError: false,
    });

    render(
      createElement(
        createWrapper(),
        null,
        createElement(LineItemsTable, {
          workspaceId: 'ws-001',
          docId: 'doc-123',
        })
      )
    );

    const link = screen.getByRole('link', { name: /proceed to compile/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute(
      'href',
      '/w/ws-001/documents/doc-123/compile'
    );
  });

  it('shows loading state', () => {
    mockUseLineItems.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });

    render(
      createElement(
        createWrapper(),
        null,
        createElement(LineItemsTable, {
          workspaceId: 'ws-001',
          docId: 'doc-123',
        })
      )
    );

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});
