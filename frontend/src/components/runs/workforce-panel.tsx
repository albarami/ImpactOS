'use client';

import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

interface WorkforcePanelProps {
  employment: Record<string, number>;
}

function formatNumber(value: number): string {
  const str = Math.round(value).toString();
  const parts: string[] = [];
  for (let i = str.length; i > 0; i -= 3) {
    parts.unshift(str.slice(Math.max(0, i - 3), i));
  }
  return parts.join(',');
}

/**
 * P6-4: Workforce panel — shows employment by sector from satellite
 * computation, with a headline total jobs figure.
 */
export function WorkforcePanel({ employment }: WorkforcePanelProps) {
  const entries = useMemo(() => {
    return Object.entries(employment)
      .filter(([k]) => !k.startsWith('_'))
      .sort(([, a], [, b]) => b - a);
  }, [employment]);

  const totalJobs = useMemo(() => {
    return entries.reduce((sum, [, val]) => sum + val, 0);
  }, [entries]);

  if (entries.length === 0) return null;

  return (
    <Card data-testid="workforce-panel">
      <CardHeader>
        <CardTitle className="text-base">Workforce Impact</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="mb-4">
          <p className="text-sm text-muted-foreground">Total Jobs Created</p>
          <p className="text-2xl font-bold">{formatNumber(totalJobs)}</p>
        </div>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Sector</TableHead>
                <TableHead className="text-right">Jobs</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map(([sector, value]) => (
                <TableRow key={sector}>
                  <TableCell className="font-mono">{sector}</TableCell>
                  <TableCell className="text-right">
                    {formatNumber(value)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
