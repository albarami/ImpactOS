'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useExportStatus, type ExportStatus } from '@/lib/api/hooks/useExports';

interface ExportStatusDisplayProps {
  workspaceId: string;
  exportId: string;
  blockingReasons?: string[];
}

function StatusBadge({ status }: { status: ExportStatus }) {
  switch (status) {
    case 'COMPLETED':
      return (
        <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">
          COMPLETED
        </Badge>
      );
    case 'BLOCKED':
      return (
        <Badge className="bg-red-100 text-red-800 hover:bg-red-100">
          BLOCKED
        </Badge>
      );
    case 'FAILED':
      return (
        <Badge className="bg-red-100 text-red-800 hover:bg-red-100">
          FAILED
        </Badge>
      );
    case 'PENDING':
      return (
        <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100">
          PENDING
        </Badge>
      );
    case 'GENERATING':
      return (
        <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100">
          GENERATING
        </Badge>
      );
  }
}

export function ExportStatusDisplay({
  workspaceId,
  exportId,
  blockingReasons,
}: ExportStatusDisplayProps) {
  const { data, isLoading, isError } = useExportStatus(workspaceId, exportId);

  if (isLoading) {
    return (
      <div className="space-y-4" data-testid="export-loading">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <p className="text-red-600">Failed to load export status</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return null;
  }

  const isPolling = data.status === 'PENDING' || data.status === 'GENERATING';
  const checksumEntries = Object.entries(data.checksums);

  return (
    <div className="space-y-4">
      {/* Export Details Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3">
            Export Status
            <StatusBadge status={data.status} />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3 text-sm">
            <div>
              <dt className="font-medium text-muted-foreground">Export ID</dt>
              <dd className="font-mono mt-1">{data.export_id}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">Run ID</dt>
              <dd className="font-mono mt-1">{data.run_id}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">Mode</dt>
              <dd className="mt-1">{data.mode}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Polling indicator for PENDING/GENERATING */}
      {isPolling && (
        <Card data-testid="export-polling">
          <CardContent className="py-6">
            <div className="flex items-center gap-3">
              <Skeleton className="h-4 w-4 rounded-full" />
              <p className="text-sm text-muted-foreground">
                Generating export...
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* COMPLETED: Checksums + Phase 3B message */}
      {data.status === 'COMPLETED' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Checksums</CardTitle>
          </CardHeader>
          <CardContent>
            {checksumEntries.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Format</TableHead>
                    <TableHead>Checksum</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {checksumEntries.map(([format, checksum]) => (
                    <TableRow key={format}>
                      <TableCell className="font-medium">{format}</TableCell>
                      <TableCell className="font-mono text-xs">
                        {checksum}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="text-sm text-muted-foreground">
                No checksums available.
              </p>
            )}
            <p className="mt-4 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
              Download not yet available (Phase 3B — B-12)
            </p>
          </CardContent>
        </Card>
      )}

      {/* BLOCKED */}
      {data.status === 'BLOCKED' && (
        <Card>
          <CardContent className="py-6">
            {blockingReasons && blockingReasons.length > 0 ? (
              <div>
                <p className="text-sm font-medium text-red-600 mb-2">
                  Export blocked for the following reasons:
                </p>
                <ul className="list-disc list-inside space-y-1" data-testid="blocking-reasons">
                  {blockingReasons.map((reason, idx) => (
                    <li key={idx} className="text-sm text-red-600">
                      {reason}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-sm text-red-600">
                This export is blocked. The run may have unresolved governance
                issues preventing export in GOVERNED mode.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* FAILED */}
      {data.status === 'FAILED' && (
        <Card>
          <CardContent className="py-6">
            <p className="text-sm text-red-600">
              Export generation failed. Please check the run configuration and
              try again.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
