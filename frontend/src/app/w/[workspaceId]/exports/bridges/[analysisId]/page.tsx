'use client';

import { useParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { WaterfallChart } from '@/components/exports/WaterfallChart';
import { DriverCard } from '@/components/exports/DriverCard';
import { useVarianceBridge } from '@/lib/api/hooks/useVarianceBridges';

export default function BridgeDetailPage() {
  const params = useParams<{ workspaceId: string; analysisId: string }>();
  const workspaceId = params.workspaceId;
  const analysisId = params.analysisId;

  const { data: bridge, isLoading, error } = useVarianceBridge(
    workspaceId,
    analysisId
  );

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Bridge Analysis
          </h1>
          <p className="mt-1 font-mono text-sm text-slate-500">
            {analysisId}
          </p>
        </div>
        <div className="flex items-center justify-center py-12">
          <p className="text-sm text-slate-500">Loading analysis...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Bridge Analysis
          </h1>
          <p className="mt-1 font-mono text-sm text-slate-500">
            {analysisId}
          </p>
        </div>
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700">
            {error instanceof Error ? error.message : 'Failed to load analysis'}
          </p>
        </div>
      </div>
    );
  }

  if (!bridge) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Bridge Analysis
          </h1>
        </div>
        <p className="text-sm text-slate-500">Analysis not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">
          Bridge Analysis
        </h1>
        <p className="mt-1 font-mono text-sm text-slate-500">
          {bridge.analysis_id}
        </p>
      </div>

      {/* Metadata */}
      <Card>
        <CardHeader>
          <CardTitle>Analysis Metadata</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <dt className="text-slate-500">Metric Type</dt>
            <dd className="text-slate-700">{bridge.metric_type}</dd>
            <dt className="text-slate-500">Run A</dt>
            <dd className="font-mono text-slate-700">{bridge.run_a_id}</dd>
            <dt className="text-slate-500">Run B</dt>
            <dd className="font-mono text-slate-700">{bridge.run_b_id}</dd>
            <dt className="text-slate-500">Version</dt>
            <dd className="text-slate-700">{bridge.analysis_version}</dd>
            <dt className="text-slate-500">Config Hash</dt>
            <dd className="font-mono text-slate-700">{bridge.config_hash}</dd>
            <dt className="text-slate-500">Result Checksum</dt>
            <dd className="font-mono text-slate-700">
              {bridge.result_checksum}
            </dd>
            <dt className="text-slate-500">Created</dt>
            <dd className="text-slate-700">{bridge.created_at}</dd>
          </dl>
        </CardContent>
      </Card>

      {/* Waterfall Chart */}
      <div>
        <h2 className="mb-4 text-lg font-semibold text-slate-900">
          Variance Waterfall
        </h2>
        <WaterfallChart
          startValue={bridge.start_value}
          endValue={bridge.end_value}
          totalVariance={bridge.total_variance}
          drivers={bridge.drivers}
        />
      </div>

      {/* Driver Cards */}
      {bridge.drivers.length > 0 && (
        <div>
          <h2 className="mb-4 text-lg font-semibold text-slate-900">
            Driver Details
          </h2>
          <div className="space-y-3">
            {bridge.drivers.map((driver, index) => (
              <DriverCard
                key={`${driver.driver_type}-${index}`}
                driverType={driver.driver_type}
                description={driver.description}
                impact={driver.impact}
                weight={driver.weight}
                totalVariance={bridge.total_variance}
                sourceField={driver.source_field}
                diffSummary={driver.diff_summary}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
