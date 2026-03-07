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

interface SuiteRun {
  name: string;
  mode?: string;
  is_contrarian?: boolean;
  sensitivities?: (string | Record<string, unknown>)[];
  executable_levers?: Record<string, unknown>[];
}

interface ScenarioSuitePanelProps {
  runs: SuiteRun[];
  suiteId?: string;
  rationale?: string;
}

/**
 * P6-4: Scenario Suite Panel — displays the list of depth-engine
 * scenario runs from a ScenarioSuitePlan.
 */
export function ScenarioSuitePanel({
  runs,
  suiteId,
  rationale,
}: ScenarioSuitePanelProps) {
  if (runs.length === 0) return null;

  return (
    <Card data-testid="scenario-suite-panel">
      <CardHeader>
        <CardTitle className="text-base">Scenario Suite</CardTitle>
        {suiteId && (
          <p className="text-xs text-muted-foreground font-mono">{suiteId}</p>
        )}
      </CardHeader>
      <CardContent>
        {rationale && (
          <p className="text-sm text-muted-foreground mb-4">{rationale}</p>
        )}
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Scenario</TableHead>
                <TableHead>Mode</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Sensitivities</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((run, idx) => (
                <TableRow key={idx}>
                  <TableCell className="font-medium">{run.name}</TableCell>
                  <TableCell>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        run.mode === 'GOVERNED'
                          ? 'bg-green-100 text-green-800'
                          : 'bg-yellow-100 text-yellow-800'
                      }`}
                    >
                      {run.mode ?? 'SANDBOX'}
                    </span>
                  </TableCell>
                  <TableCell>
                    {run.is_contrarian ? (
                      <span className="text-amber-600 font-medium">Contrarian</span>
                    ) : (
                      <span className="text-muted-foreground">Standard</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {run.sensitivities?.length ?? 0}
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
