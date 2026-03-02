'use client';

import { useMemo } from 'react';
import { useParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ResultsDisplay } from '@/components/runs/results-display';
import { SectorChart } from '@/components/runs/sector-chart';
import { useRunResults } from '@/lib/api/hooks/useRuns';

export default function RunDetailPage() {
  const params = useParams<{ workspaceId: string; runId: string }>();
  const workspaceId = params.workspaceId;
  const runId = params.runId;

  const { data } = useRunResults(workspaceId, runId);

  // Aggregate values across all result sets for chart
  const chartData = useMemo<Record<string, number>>(() => {
    if (!data?.result_sets?.length) return {};
    // Use the first result set for the chart (typically gross_output)
    const firstSet = data.result_sets[0];
    return firstSet.values;
  }, [data]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Run Results</h1>
        <p className="mt-1 text-sm text-slate-500 font-mono">{runId}</p>
      </div>

      <ResultsDisplay workspaceId={workspaceId} runId={runId} />

      {Object.keys(chartData).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Sector Impact Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <SectorChart data={chartData} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
