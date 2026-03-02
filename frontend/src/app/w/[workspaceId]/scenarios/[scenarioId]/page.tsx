'use client';

import { useParams, useSearchParams } from 'next/navigation';
import { ScenarioCompileForm } from '@/components/scenarios/compile-form';

export default function ScenarioDetailPage() {
  const params = useParams<{ workspaceId: string; scenarioId: string }>();
  const searchParams = useSearchParams();
  const workspaceId = params.workspaceId;
  const scenarioId = params.scenarioId;
  const compilationId = searchParams.get('compilationId') ?? undefined;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Scenario Compile</h1>
        <p className="mt-1 text-sm text-slate-500 font-mono">{scenarioId}</p>
      </div>

      <ScenarioCompileForm
        workspaceId={workspaceId}
        scenarioId={scenarioId}
        compilationId={compilationId}
      />
    </div>
  );
}
