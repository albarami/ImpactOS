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
import { Skeleton } from '@/components/ui/skeleton';
import { useRunResults, type ResultSet } from '@/lib/api/hooks/useRuns';

interface ResultsDisplayProps {
  workspaceId: string;
  runId: string;
}

function formatNumber(value: number): string {
  // Manual formatting to avoid locale-dependent Intl behavior in test environments
  const str = Math.round(value).toString();
  const parts: string[] = [];
  for (let i = str.length; i > 0; i -= 3) {
    parts.unshift(str.slice(Math.max(0, i - 3), i));
  }
  return parts.join(',');
}

export function ResultsDisplay({ workspaceId, runId }: ResultsDisplayProps) {
  const { data, isLoading, isError } = useRunResults(workspaceId, runId);

  // Compute total impact across all result sets
  const totalImpact = useMemo(() => {
    if (!data?.result_sets) return 0;
    return data.result_sets.reduce((total, rs) => {
      const setSum = Object.values(rs.values).reduce(
        (sum, val) => sum + val,
        0
      );
      return total + setSum;
    }, 0);
  }, [data]);

  // P6-2: Executive summary — extract key metrics
  const executiveSummary = useMemo(() => {
    if (!data?.result_sets || data.result_sets.length === 0) return null;

    const findTotal = (metricType: string) => {
      const rs = data.result_sets.find((r) => r.metric_type === metricType);
      if (!rs) return null;
      return Object.values(rs.values).reduce((sum, val) => sum + val, 0);
    };

    const totalOutput =
      findTotal('total_output') ?? findTotal('gross_output');
    const gdp =
      findTotal('value_added') ?? findTotal('gdp_basic_price');
    const jobs = findTotal('employment');

    // Only show summary if at least one key metric exists
    if (totalOutput == null && gdp == null && jobs == null) return null;

    return { totalOutput, gdp, jobs };
  }, [data]);

  if (isLoading) {
    return (
      <div className="space-y-4" data-testid="results-loading">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <p className="text-red-600">Failed to load run results</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Headline Card */}
      <Card>
        <CardHeader>
          <CardTitle>Run Results</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <p className="text-sm text-muted-foreground">Run ID</p>
              <p className="font-mono text-sm">{data.run_id}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Model Version</p>
              <p className="font-mono text-sm">
                {data.snapshot.model_version_id}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total Impact</p>
              <p className="text-2xl font-bold" data-testid="total-impact-value">
                {formatNumber(totalImpact)}{' '}
                <span className="text-base font-normal text-muted-foreground">
                  SAR
                </span>
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* P6-2: Executive Summary KPI Cards */}
      {executiveSummary && (
        <div
          className="grid grid-cols-1 gap-4 sm:grid-cols-3"
          data-testid="executive-summary"
        >
          {executiveSummary.totalOutput != null && (
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">Total Output</p>
                <p className="text-2xl font-bold">
                  {formatNumber(executiveSummary.totalOutput)}{' '}
                  <span className="text-base font-normal text-muted-foreground">
                    SAR
                  </span>
                </p>
              </CardContent>
            </Card>
          )}
          {executiveSummary.gdp != null && (
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">GDP Impact</p>
                <p className="text-2xl font-bold">
                  {formatNumber(executiveSummary.gdp)}{' '}
                  <span className="text-base font-normal text-muted-foreground">
                    SAR
                  </span>
                </p>
              </CardContent>
            </Card>
          )}
          {executiveSummary.jobs != null && (
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">Jobs Created</p>
                <p className="text-2xl font-bold">
                  {formatNumber(executiveSummary.jobs)}
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Result Sets Table */}
      {data.result_sets.map((rs: ResultSet) => (
        <Card key={rs.result_id}>
          <CardHeader>
            <CardTitle className="text-base">{rs.metric_type}</CardTitle>
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
                  {Object.entries(rs.values)
                    .sort(([, a], [, b]) => b - a)
                    .map(([sector, value]) => (
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
      ))}
    </div>
  );
}
