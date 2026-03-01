'use client';

import { useParams, useSearchParams } from 'next/navigation';
import { ScenarioCreateForm } from '@/components/scenarios/create-form';

export default function ScenariosPage() {
  const params = useParams<{ workspaceId: string }>();
  const searchParams = useSearchParams();
  const workspaceId = params.workspaceId;
  const compilationId = searchParams.get('compilationId') ?? undefined;
  const documentId = searchParams.get('documentId') ?? undefined;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Create Scenario</h1>
        {compilationId && (
          <p className="mt-1 text-sm text-slate-500">
            Compilation:{' '}
            <span className="font-mono">{compilationId}</span>
          </p>
        )}
      </div>

      <ScenarioCreateForm workspaceId={workspaceId} compilationId={compilationId} />
    </div>
  );
}
