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

interface SectorBreakdownsPanelProps {
  breakdowns: Record<string, Record<string, number>>;
  denomination?: string;
}

function formatNumber(value: number): string {
  const str = Math.round(value).toString();
  const parts: string[] = [];
  for (let i = str.length; i > 0; i -= 3) {
    parts.unshift(str.slice(Math.max(0, i - 3), i));
  }
  return parts.join(',');
}

function formatLabel(key: string): string {
  return key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
}

/**
 * P6-4: Sector breakdowns panel — shows direct/indirect/employment
 * decomposition per sector from ResultSet.sector_breakdowns.
 */
export function SectorBreakdownsPanel({
  breakdowns,
  denomination,
}: SectorBreakdownsPanelProps) {
  const breakdownKeys = Object.keys(breakdowns);
  if (breakdownKeys.length === 0) return null;

  return (
    <div className="space-y-4" data-testid="sector-breakdowns">
      {breakdownKeys.map((key) => {
        const data = breakdowns[key];
        const entries = Object.entries(data).sort(([, a], [, b]) => b - a);

        return (
          <Card key={key}>
            <CardHeader>
              <CardTitle className="text-base">
                {formatLabel(key)} Breakdown
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Sector</TableHead>
                      <TableHead className="text-right">Value</TableHead>
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
      })}
    </div>
  );
}
