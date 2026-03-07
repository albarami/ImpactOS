'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { SuiteRunResponse } from '@/lib/api/hooks/useRuns';

interface SensitivityEnvelopePanelProps {
  runs: SuiteRunResponse[];
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

export function SensitivityEnvelopePanel({
  runs,
  denomination = 'SAR',
}: SensitivityEnvelopePanelProps) {
  const outputRuns = runs.filter((r) => r.headline_output != null);
  if (outputRuns.length === 0) return null;

  const sorted = [...outputRuns].sort(
    (a, b) => (a.headline_output ?? 0) - (b.headline_output ?? 0)
  );
  const low = sorted[0];
  const high = sorted[sorted.length - 1];
  const central = sorted[Math.floor(sorted.length / 2)];
  const dominant = [...sorted].sort(
    (a, b) =>
      Math.abs((b.headline_output ?? 0) - (central.headline_output ?? 0)) -
      Math.abs((a.headline_output ?? 0) - (central.headline_output ?? 0))
  )[0];
  const swing = Math.abs((dominant.headline_output ?? 0) - (central.headline_output ?? 0));

  return (
    <Card data-testid="sensitivity-envelope-panel">
      <CardHeader>
        <CardTitle className="text-base">Sensitivity Envelope</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3" data-testid="envelope-range">
          <div>
            <p className="text-xs text-muted-foreground">Low estimate</p>
            <p className="text-lg font-semibold">{formatNumber(low.headline_output ?? 0)} {denomination}</p>
            <p className="text-xs text-muted-foreground">{low.name}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Central estimate</p>
            <p className="text-lg font-semibold">{formatNumber(central.headline_output ?? 0)} {denomination}</p>
            <p className="text-xs text-muted-foreground">{central.name}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">High estimate</p>
            <p className="text-lg font-semibold">{formatNumber(high.headline_output ?? 0)} {denomination}</p>
            <p className="text-xs text-muted-foreground">{high.name}</p>
          </div>
        </div>

        <div className="space-y-2">
          {sorted.map((run) => {
            const min = low.headline_output ?? 0;
            const max = high.headline_output ?? 0;
            const range = max - min || 1;
            const pct = (((run.headline_output ?? 0) - min) / range) * 100;
            return (
              <div key={run.run_id} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span>{run.name}</span>
                  <span>{formatNumber(run.headline_output ?? 0)} {denomination}</span>
                </div>
                <div className="h-2 rounded-full bg-muted">
                  <div className="h-2 rounded-full bg-primary" style={{ width: `${Math.max(4, pct)}%` }} />
                </div>
              </div>
            );
          })}
        </div>

        <p className="text-sm text-muted-foreground">
          Dominant sensitivity driver: <span className="font-medium text-foreground">{dominant.name}</span>
          {' '}moves the central estimate by {formatNumber(swing)} {denomination}.
        </p>
      </CardContent>
    </Card>
  );
}
