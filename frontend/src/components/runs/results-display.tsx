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
import { SectorBreakdownsPanel } from './sector-breakdowns-panel';
import { WorkforcePanel } from './workforce-panel';
import { FeasibilityPanel } from './feasibility-panel';
import { ScenarioSuitePanel } from './scenario-suite-panel';
import { QualitativeRisksPanel } from './qualitative-risks-panel';
import { SensitivityEnvelopePanel } from './sensitivity-envelope-panel';
import { DepthEngineTracePanel } from './depth-engine-trace-panel';

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

/**
 * P6-3: Convert model_denomination code to display label.
 * "SAR_MILLIONS" → "SAR (Millions)"
 * "SAR_THOUSANDS" → "SAR (Thousands)"
 * "SAR" → "SAR"
 * undefined/UNKNOWN → "SAR"
 */
function formatDenomination(denomination?: string): string {
  if (!denomination || denomination === 'UNKNOWN') return 'SAR';
  if (denomination === 'SAR_MILLIONS') return 'SAR (Millions)';
  if (denomination === 'SAR_THOUSANDS') return 'SAR (Thousands)';
  if (denomination === 'SAR') return 'SAR';
  // Fallback: strip underscores and title-case
  const parts = denomination.split('_');
  const currency = parts[0] || 'SAR';
  const scale = parts.slice(1).join(' ');
  if (!scale) return currency;
  return `${currency} (${scale.charAt(0).toUpperCase()}${scale.slice(1).toLowerCase()})`;
}

export function ResultsDisplay({ workspaceId, runId }: ResultsDisplayProps) {
  const { data, isLoading, isError } = useRunResults(workspaceId, runId);

  // P6-3: Denomination label from snapshot metadata
  const denominationLabel = useMemo(() => {
    return formatDenomination(data?.snapshot?.model_denomination);
  }, [data]);

  // P6-3: Total impact sums only total_output (or gross_output as fallback)
  const totalImpact = useMemo(() => {
    if (!data?.result_sets) return 0;
    const outputRS = data.result_sets.find(
      (rs) =>
        rs.metric_type === 'total_output' || rs.metric_type === 'gross_output'
    );
    if (!outputRS) return 0;
    return Object.values(outputRS.values).reduce((sum, val) => sum + val, 0);
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

  // P6-4: Extract sector breakdowns from total_output ResultSet
  const sectorBreakdowns = useMemo(() => {
    if (!data?.result_sets) return null;
    const outputRS = data.result_sets.find(
      (rs) => rs.metric_type === 'total_output' || rs.metric_type === 'gross_output'
    );
    if (!outputRS?.sector_breakdowns) return null;
    return outputRS.sector_breakdowns;
  }, [data]);

  // P6-4: Extract employment data
  const employmentData = useMemo(() => {
    if (!data?.result_sets) return null;
    const empRS = data.result_sets.find((rs) => rs.metric_type === 'employment');
    if (!empRS) return null;
    return empRS.values;
  }, [data]);

  // P6-4: Extract feasibility data
  const feasibilityData = useMemo(() => {
    if (!data?.result_sets) return null;
    const unconstrainedRS = data.result_sets.find(
      (rs) => rs.metric_type === 'total_output' || rs.metric_type === 'gross_output'
    );
    const feasibleRS = data.result_sets.find(
      (rs) => rs.metric_type === 'feasible_output'
    );
    const gapRS = data.result_sets.find(
      (rs) => rs.metric_type === 'constraint_gap'
    );
    if (!feasibleRS || !gapRS) return null;
    return {
      unconstrained: unconstrainedRS?.values ?? {},
      feasible: feasibleRS.values,
      gap: gapRS.values,
    };
  }, [data]);

  // P6-4: Extract depth engine data (suite runs, risks, sensitivity, trace)
  const depthData = useMemo(() => {
    if (!data?.depth_engine) return null;
    return data.depth_engine;
  }, [data]);

  // P6-4: Suite runs from depth engine
  const suiteRuns = useMemo(() => {
    return depthData?.suite_runs ?? [];
  }, [depthData]);

  // P6-4: Qualitative risks from depth engine
  const qualitativeRisks = useMemo(() => {
    return depthData?.qualitative_risks ?? [];
  }, [depthData]);

  // P6-4: Sensitivity runs from depth engine
  const sensitivityRuns = useMemo(() => {
    return depthData?.sensitivity_runs ?? [];
  }, [depthData]);

  // P6-4: Depth trace steps from depth engine
  const depthTrace = useMemo(() => {
    return depthData?.trace_steps ?? [];
  }, [depthData]);

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
                  {denominationLabel}
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
                    {denominationLabel}
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
                    {denominationLabel}
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

      {/* P6-4: Sector Breakdowns Panel */}
      {sectorBreakdowns && (
        <SectorBreakdownsPanel
          breakdowns={sectorBreakdowns}
          denomination={denominationLabel}
        />
      )}

      {/* P6-4: Workforce Panel */}
      {employmentData && <WorkforcePanel employment={employmentData} />}

      {/* P6-4: Feasibility Panel */}
      {feasibilityData && (
        <FeasibilityPanel
          unconstrained={feasibilityData.unconstrained}
          feasible={feasibilityData.feasible}
          gap={feasibilityData.gap}
        />
      )}

      {/* P6-4: Scenario Suite Panel */}
      {suiteRuns.length > 0 && (
        <ScenarioSuitePanel
          runs={suiteRuns}
          suiteId={depthData?.suite_id}
          rationale={depthData?.suite_rationale}
        />
      )}

      {/* P6-4: Qualitative Risks Panel */}
      {qualitativeRisks.length > 0 && (
        <QualitativeRisksPanel risks={qualitativeRisks} />
      )}

      {/* P6-4: Sensitivity Envelope Panel */}
      {sensitivityRuns.length > 0 && (
        <SensitivityEnvelopePanel runs={sensitivityRuns} />
      )}

      {/* P6-4: Depth Engine Trace Panel */}
      {depthTrace.length > 0 && (
        <DepthEngineTracePanel
          steps={depthTrace}
          planId={depthData?.plan_id}
        />
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
