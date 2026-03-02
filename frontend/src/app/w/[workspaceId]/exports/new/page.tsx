'use client';

import { useParams, useSearchParams } from 'next/navigation';
import { ExportForm } from '@/components/exports/export-form';

export default function NewExportPage() {
  const params = useParams<{ workspaceId: string }>();
  const searchParams = useSearchParams();
  const workspaceId = params.workspaceId;
  const runId = searchParams.get('runId') ?? '';

  if (!runId) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">New Export</h1>
          <p className="mt-2 text-red-600">
            No run ID provided. Please go back and enter a run ID.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">New Export</h1>
        <p className="mt-2 text-slate-500">
          Configure and create a Decision Pack export.
        </p>
      </div>

      <ExportForm workspaceId={workspaceId} runId={runId} />
    </div>
  );
}
