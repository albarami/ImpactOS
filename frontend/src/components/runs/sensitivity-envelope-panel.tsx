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

interface SensitivityRun {
  name: string;
  multiplier: number;
  total_output?: number;
  employment?: number;
}

interface SensitivityEnvelopePanelProps {
  runs: SensitivityRun[];
  baseRunName?: string;
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
 * P6-4: Sensitivity Envelope Panel — displays confidence ranges
 * from sensitivity sweep runs, showing how output varies with
 * different multiplier values.
 */
export function SensitivityEnvelopePanel({
  runs,
  baseRunName,
}: SensitivityEnvelopePanelProps) {
  if (runs.length === 0) return null;

  // Sort by multiplier ascending for envelope display
  const sorted = [...runs].sort((a, b) => a.multiplier - b.multiplier);

  // Compute min/max envelope
  const outputs = sorted.filter((r) => r.total_output != null);
  const minOutput = outputs.length > 0 ? Math.min(...outputs.map((r) => r.total_output!)) : null;
  const maxOutput = outputs.length > 0 ? Math.max(...outputs.map((r) => r.total_output!)) : null;

  return (
    <Card data-testid="sensitivity-envelope-panel">
      <CardHeader>
        <CardTitle className="text-base">Sensitivity Envelope</CardTitle>
        {baseRunName && (
          <p className="text-xs text-muted-foreground">
            Base scenario: {baseRunName}
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Envelope summary */}
        {minOutput != null && maxOutput != null && (
          <div className="flex gap-4" data-testid="envelope-range">
            <div>
              <p className="text-xs text-muted-foreground">Low estimate</p>
              <p className="text-lg font-semibold">{formatNumber(minOutput)}</p>
            </div>
            <div className="flex items-center text-muted-foreground">—</div>
            <div>
              <p className="text-xs text-muted-foreground">High estimate</p>
              <p className="text-lg font-semibold">{formatNumber(maxOutput)}</p>
            </div>
          </div>
        )}

        {/* Detailed sweep table */}
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Scenario</TableHead>
                <TableHead className="text-right">Multiplier</TableHead>
                <TableHead className="text-right">Total Output</TableHead>
                <TableHead className="text-right">Employment</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((run, idx) => (
                <TableRow key={idx}>
                  <TableCell className="font-medium">{run.name}</TableCell>
                  <TableCell className="text-right font-mono">
                    {run.multiplier.toFixed(2)}x
                  </TableCell>
                  <TableCell className="text-right">
                    {run.total_output != null ? formatNumber(run.total_output) : '—'}
                  </TableCell>
                  <TableCell className="text-right">
                    {run.employment != null ? formatNumber(run.employment) : '—'}
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
