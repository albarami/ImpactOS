'use client';

import { useEffect, useRef } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { useJobStatus } from '@/lib/api/hooks/useDocuments';

interface ExtractionStatusProps {
  workspaceId: string;
  jobId: string | null;
  onComplete: (docId: string) => void;
}

export function ExtractionStatus({
  workspaceId,
  jobId,
  onComplete,
}: ExtractionStatusProps) {
  const { data, refetch } = useJobStatus(workspaceId, jobId);
  const completedRef = useRef(false);

  // Call onComplete exactly once when the job completes
  useEffect(() => {
    if (data?.status === 'COMPLETED' && !completedRef.current) {
      completedRef.current = true;
      onComplete(data.doc_id);
    }
  }, [data?.status, data?.doc_id, onComplete]);

  // Reset the completed ref when the jobId changes
  useEffect(() => {
    completedRef.current = false;
  }, [jobId]);

  if (!jobId) return null;

  if (!data) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-2 w-full" />
      </div>
    );
  }

  if (data.status === 'QUEUED') {
    return (
      <div className="space-y-2">
        <p className="text-sm text-slate-600">Queued...</p>
        <Skeleton className="h-2 w-full" />
      </div>
    );
  }

  if (data.status === 'RUNNING') {
    return (
      <div className="space-y-2">
        <p className="text-sm text-slate-600">Extracting...</p>
        <Progress />
      </div>
    );
  }

  if (data.status === 'COMPLETED') {
    return (
      <div className="flex items-center gap-2">
        <Badge variant="default" className="bg-green-600">
          Extraction Complete
        </Badge>
      </div>
    );
  }

  if (data.status === 'FAILED') {
    return (
      <Alert variant="destructive">
        <AlertTitle>Extraction Failed</AlertTitle>
        <AlertDescription>
          <p>{data.error_message ?? 'Unknown error'}</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => refetch()}
          >
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return null;
}
