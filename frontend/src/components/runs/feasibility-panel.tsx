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

interface FeasibilityPanelProps {
  unconstrained: Record<string, number>;
  feasible: Record<string, number>;
  gap: Record<string, number>;
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
 * P6-4: Feasibility panel — shows unconstrained vs feasible output
 * per sector, highlighting binding constraints (gap > 0).
 */
export function FeasibilityPanel({
  unconstrained,
  feasible,
  gap,
}: FeasibilityPanelProps) {
  const sectors = useMemo(() => {
    const allSectors = new Set([
      ...Object.keys(unconstrained),
      ...Object.keys(feasible),
      ...Object.keys(gap),
    ]);
    return Array.from(allSectors)
      .filter((s) => !s.startsWith('_'))
      .sort();
  }, [unconstrained, feasible, gap]);

  if (sectors.length === 0) return null;

  const hasBindingConstraints = sectors.some(
    (s) => (gap[s] ?? 0) > 0
  );

  return (
    <Card data-testid="feasibility-panel">
      <CardHeader>
        <CardTitle className="text-base">
          Feasibility Analysis
          {hasBindingConstraints && (
            <span className="ml-2 text-sm font-normal text-amber-600">
              (constraints binding)
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Sector</TableHead>
                <TableHead className="text-right">Unconstrained</TableHead>
                <TableHead className="text-right">Feasible</TableHead>
                <TableHead className="text-right">Gap</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sectors.map((sector) => {
                const sectorGap = gap[sector] ?? 0;
                const isBinding = sectorGap > 0;
                return (
                  <TableRow
                    key={sector}
                    className={isBinding ? 'bg-amber-50' : ''}
                  >
                    <TableCell className="font-mono">{sector}</TableCell>
                    <TableCell className="text-right">
                      {formatNumber(unconstrained[sector] ?? 0)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatNumber(feasible[sector] ?? 0)}
                    </TableCell>
                    <TableCell
                      className={`text-right ${isBinding ? 'font-semibold text-amber-700' : ''}`}
                    >
                      {formatNumber(sectorGap)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
