'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { WorkforceResponse } from '@/lib/api/hooks/useRuns';

interface WorkforcePanelProps {
  workforce: WorkforceResponse;
}

function formatNumber(value: number): string {
  const str = Math.round(value).toString();
  const parts: string[] = [];
  for (let i = str.length; i > 0; i -= 3) {
    parts.unshift(str.slice(Math.max(0, i - 3), i));
  }
  return parts.join(',');
}

export function WorkforcePanel({ workforce }: WorkforcePanelProps) {
  const entries = [...workforce.per_sector].sort(
    (a, b) => b.total_jobs - a.total_jobs
  );

  if (entries.length === 0) return null;

  return (
    <Card data-testid="workforce-panel">
      <CardHeader>
        <CardTitle className="text-base">Workforce Impact</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="mb-4">
          <p className="text-sm text-muted-foreground">Total Jobs</p>
          <p className="text-2xl font-bold">{formatNumber(workforce.total_jobs)}</p>
          {workforce.has_saudization_split && (
            <div className="mt-2 grid grid-cols-1 gap-2 text-sm text-muted-foreground sm:grid-cols-3">
              <div>
                Saudi-ready:{' '}
                <span className="font-medium text-foreground">
                  {formatNumber(workforce.total_saudi_ready)}
                </span>
              </div>
              <div>
                Saudi-trainable:{' '}
                <span className="font-medium text-foreground">
                  {formatNumber(workforce.total_saudi_trainable)}
                </span>
              </div>
              <div>
                Expat-reliant:{' '}
                <span className="font-medium text-foreground">
                  {formatNumber(workforce.total_expat_reliant)}
                </span>
              </div>
            </div>
          )}
        </div>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Sector</TableHead>
                <TableHead className="text-right">Total Jobs</TableHead>
                {workforce.has_saudization_split && (
                  <>
                    <TableHead className="text-right">Saudi-Ready</TableHead>
                    <TableHead className="text-right">Saudi-Trainable</TableHead>
                    <TableHead className="text-right">Expat-Reliant</TableHead>
                  </>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => (
                <TableRow key={entry.sector_code}>
                  <TableCell className="font-mono">{entry.sector_code}</TableCell>
                  <TableCell className="text-right">
                    {formatNumber(entry.total_jobs)}
                  </TableCell>
                  {workforce.has_saudization_split && (
                    <>
                      <TableCell className="text-right">
                        {formatNumber(entry.saudi_ready_jobs)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatNumber(entry.saudi_trainable_jobs)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatNumber(entry.expat_reliant_jobs)}
                      </TableCell>
                    </>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
