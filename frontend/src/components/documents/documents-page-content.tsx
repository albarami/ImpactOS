'use client';

import { useState } from 'react';
import Link from 'next/link';
import { UploadForm, type UploadResult } from './upload-form';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface RecentUpload {
  docId: string;
  jobId: string;
  timestamp: Date;
}

interface DocumentsPageContentProps {
  workspaceId: string;
}

export function DocumentsPageContent({
  workspaceId,
}: DocumentsPageContentProps) {
  const [recentUploads, setRecentUploads] = useState<RecentUpload[]>([]);

  function handleUploaded(result: UploadResult) {
    setRecentUploads((prev) => [
      { docId: result.docId, jobId: result.jobId, timestamp: new Date() },
      ...prev,
    ]);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Documents</h1>
        <p className="mt-1 text-sm text-slate-500">
          Upload and process documents for line-item extraction.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <UploadForm workspaceId={workspaceId} onUploaded={handleUploaded} />

        <Card>
          <CardHeader>
            <CardTitle>Recent Uploads</CardTitle>
          </CardHeader>
          <CardContent>
            {recentUploads.length === 0 ? (
              <p className="text-sm text-slate-500">
                No documents uploaded yet. Use the form to upload your first
                document.
              </p>
            ) : (
              <ul className="space-y-3">
                {recentUploads.map((upload) => (
                  <li
                    key={upload.docId}
                    className="flex items-center justify-between rounded-md border border-slate-200 p-3"
                  >
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-slate-900">
                        {upload.docId}
                      </p>
                      <Badge variant="secondary" className="text-xs">
                        Job: {upload.jobId}
                      </Badge>
                    </div>
                    <Button asChild size="sm" variant="outline">
                      <Link
                        href={`/w/${workspaceId}/documents/${upload.docId}?jobId=${upload.jobId}`}
                      >
                        View
                      </Link>
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
