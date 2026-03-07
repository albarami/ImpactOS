'use client';

import { useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { SuiteRunResponse } from '@/lib/api/hooks/useRuns';

interface ScenarioSuitePanelProps {
  runs: SuiteRunResponse[];
  suiteId?: string | null;
  rationale?: string | null;
  denomination?: string;
}

function formatNumber(value?: number | null): string {
  if (value == null) return '-';
  const str = Math.round(value).toString();
  const parts: string[] = [];
  for (let i = str.length; i > 0; i -= 3) {
    parts.unshift(str.slice(Math.max(0, i - 3), i));
  }
  return parts.join(',');
}

function statusTone(status: string): string {
  if (status === 'SURVIVED') return 'bg-green-100 text-green-800';
  if (status === 'REJECTED') return 'bg-red-100 text-red-800';
  return 'bg-amber-100 text-amber-800';
}

export function ScenarioSuitePanel({
  runs,
  suiteId,
  rationale,
  denomination = 'SAR',
}: ScenarioSuitePanelProps) {
  const [expanded, setExpanded] = useState(false);
  const sortedRuns = useMemo(
    () => [...runs].sort((a, b) => (b.headline_output ?? 0) - (a.headline_output ?? 0)),
    [runs]
  );
  const visibleRuns = expanded ? sortedRuns : sortedRuns.slice(0, 5);

  if (runs.length === 0) return null;

  return (
    <Card data-testid="scenario-suite-panel">
      <CardHeader>
        <CardTitle className="text-base">Scenario Suite</CardTitle>
        {suiteId && <p className="font-mono text-xs text-muted-foreground">{suiteId}</p>}
      </CardHeader>
      <CardContent className="space-y-4">
        {rationale && <p className="text-sm text-muted-foreground">{rationale}</p>}
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Scenario</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Headline Output</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibleRuns.map((run) => (
                <TableRow key={run.run_id}>
                  <TableCell className="font-medium">{run.name}</TableCell>
                  <TableCell>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${statusTone(run.muhasaba_status)}`}
                    >
                      {run.muhasaba_status}
                    </span>
                  </TableCell>
                  <TableCell>
                    {run.is_contrarian ? (
                      <span className="font-medium text-amber-700">Contrarian</span>
                    ) : (
                      <span className="text-muted-foreground">Standard</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatNumber(run.headline_output)} {denomination}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {runs.length > 5 && (
          <button
            type="button"
            className="text-sm font-medium text-primary"
            onClick={() => setExpanded((prev) => !prev)}
          >
            {expanded ? 'Show top 5' : `Show all ${runs.length} scenarios`}
          </button>
        )}
      </CardContent>
    </Card>
  );
}
