import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TopNav } from '../topnav';

vi.mock('next/navigation', () => ({
  usePathname: () => '/w/test-ws/documents',
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: {
      user: {
        name: 'Dev User',
        id: '00000000-0000-7000-8000-000000000001',
      },
    },
    status: 'authenticated',
  }),
  signOut: vi.fn(),
}));

vi.mock('@/lib/api/hooks/useHealth', () => ({
  useHealth: () => ({
    data: { status: 'ok' },
    isLoading: false,
    isError: false,
  }),
}));

describe('TopNav', () => {
  it('renders SANDBOX mode badge', () => {
    render(<TopNav />);
    expect(screen.getByText('SANDBOX')).toBeInTheDocument();
  });

  it('shows health indicator element', () => {
    render(<TopNav />);
    expect(screen.getByTestId('health-indicator')).toBeInTheDocument();
  });

  it('shows breadcrumb with current section', () => {
    render(<TopNav />);
    expect(screen.getByText('Documents')).toBeInTheDocument();
  });

  it('shows user name from session', () => {
    render(<TopNav />);
    expect(screen.getByText('Dev User')).toBeInTheDocument();
  });
});
