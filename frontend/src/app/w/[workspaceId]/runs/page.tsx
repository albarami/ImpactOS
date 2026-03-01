'use client';

import { useParams } from 'next/navigation';
import { RunForm } from '@/components/runs/run-form';

export default function RunsPage() {
  const params = useParams<{ workspaceId: string }>();
  const workspaceId = params.workspaceId;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Execute Run</h1>
        <p className="mt-2 text-slate-500">
          Configure and execute an I-O engine run.
        </p>
      </div>

      <RunForm workspaceId={workspaceId} />
    </div>
  );
}
