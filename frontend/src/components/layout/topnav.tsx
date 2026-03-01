'use client';

import { usePathname } from 'next/navigation';
import { useSession, signOut } from 'next-auth/react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useHealth } from '@/lib/api/hooks/useHealth';

const SECTION_LABELS: Record<string, string> = {
  documents: 'Documents',
  compilations: 'Compilations',
  scenarios: 'Scenarios',
  runs: 'Runs',
  governance: 'Governance',
  exports: 'Exports',
};

function getHealthColor(
  status: string | undefined,
  isLoading: boolean,
  isError: boolean
): string {
  if (isLoading) return 'bg-slate-400';
  if (isError || status === 'degraded') return 'bg-red-500';
  return 'bg-green-500';
}

export function TopNav() {
  const pathname = usePathname();
  const { data: session } = useSession();
  const { data: health, isLoading, isError } = useHealth();

  // Extract section from pathname like /w/{id}/documents
  const segments = pathname.split('/');
  const sectionSlug = segments[3] || '';
  const sectionLabel = SECTION_LABELS[sectionSlug] || sectionSlug;

  const healthStatus = health?.status;
  const healthColor = getHealthColor(healthStatus, isLoading, isError);

  return (
    <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-500">
          {sectionLabel && (
            <>
              <span className="text-slate-400">/</span>{' '}
              <span className="font-medium text-slate-700">{sectionLabel}</span>
            </>
          )}
        </span>
      </div>

      <div className="flex items-center gap-4">
        <Badge variant="destructive" className="font-mono text-xs uppercase">
          SANDBOX
        </Badge>

        <div className="flex items-center gap-2">
          <div
            data-testid="health-indicator"
            className={`h-2.5 w-2.5 rounded-full ${healthColor}`}
            title={`Health: ${healthStatus || (isLoading ? 'loading' : 'unknown')}`}
          />
        </div>

        {session?.user?.name && (
          <span className="text-sm text-slate-600">{session.user.name}</span>
        )}

        <Button
          variant="ghost"
          size="sm"
          onClick={() => signOut({ callbackUrl: '/login' })}
        >
          Sign out
        </Button>
      </div>
    </header>
  );
}
