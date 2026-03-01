'use client';

import { useParams } from 'next/navigation';
import { ExportStatusDisplay } from '@/components/exports/export-status';
import { useExportData } from '@/lib/api/hooks/useExports';

export default function ExportDetailPage() {
  const params = useParams<{ workspaceId: string; exportId: string }>();
  const workspaceId = params.workspaceId;
  const exportId = params.exportId;
  const cachedExport = useExportData(exportId);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Export Details</h1>
        <p className="mt-1 text-sm text-slate-500 font-mono">{exportId}</p>
      </div>

      <ExportStatusDisplay
        workspaceId={workspaceId}
        exportId={exportId}
        blockingReasons={cachedExport?.blocking_reasons}
      />
    </div>
  );
}
