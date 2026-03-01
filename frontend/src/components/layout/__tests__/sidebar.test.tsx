import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Sidebar } from '../sidebar';

vi.mock('next/navigation', () => ({
  usePathname: () => '/w/test-ws/documents',
  useParams: () => ({ workspaceId: 'test-ws' }),
}));

const NAV_ITEMS = [
  { label: 'Documents', href: '/w/test-ws/documents' },
  { label: 'Compilations', href: '/w/test-ws/compilations' },
  { label: 'Scenarios', href: '/w/test-ws/scenarios' },
  { label: 'Runs', href: '/w/test-ws/runs' },
  { label: 'Governance', href: '/w/test-ws/governance' },
  { label: 'Exports', href: '/w/test-ws/exports' },
];

describe('Sidebar', () => {
  it('renders all navigation links', () => {
    render(<Sidebar />);
    for (const item of NAV_ITEMS) {
      expect(screen.getByText(item.label)).toBeInTheDocument();
    }
  });

  it('each link has correct href with workspaceId', () => {
    render(<Sidebar />);
    for (const item of NAV_ITEMS) {
      const link = screen.getByText(item.label).closest('a');
      expect(link).toHaveAttribute('href', item.href);
    }
  });

  it('active link is highlighted', () => {
    render(<Sidebar />);
    const activeLink = screen.getByText('Documents').closest('a');
    expect(activeLink).toHaveAttribute('data-active', 'true');

    const inactiveLink = screen.getByText('Compilations').closest('a');
    expect(inactiveLink).not.toHaveAttribute('data-active', 'true');
  });

  it('renders ImpactOS logo text', () => {
    render(<Sidebar />);
    expect(screen.getByText('ImpactOS')).toBeInTheDocument();
  });
});
