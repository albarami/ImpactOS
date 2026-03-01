'use client';

import { useState, useCallback } from 'react';
import { ExtractionStatus } from './extraction-status';
import { LineItemsTable } from './line-items-table';

interface DocumentDetailContentProps {
  workspaceId: string;
  docId: string;
  initialJobId: string | null;
}

export function DocumentDetailContent({
  workspaceId,
  docId,
  initialJobId,
}: DocumentDetailContentProps) {
  const [jobId] = useState<string | null>(initialJobId);
  const [extractionDone, setExtractionDone] = useState(false);

  const handleComplete = useCallback((_completedDocId: string) => {
    setExtractionDone(true);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Document Detail</h1>
        <p className="mt-1 text-sm text-slate-500 font-mono">{docId}</p>
      </div>

      {/* Extraction status — polls until COMPLETED / FAILED */}
      <ExtractionStatus
        workspaceId={workspaceId}
        jobId={jobId}
        onComplete={handleComplete}
      />

      {/* Line items — shown when extraction finishes (or when no jobId provided, meaning we just want to view existing items) */}
      {(extractionDone || !jobId) && (
        <LineItemsTable workspaceId={workspaceId} docId={docId} />
      )}
    </div>
  );
}
