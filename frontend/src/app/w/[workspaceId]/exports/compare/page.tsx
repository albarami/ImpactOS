'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RunSelector } from '@/components/exports/RunSelector';
import { WaterfallChart } from '@/components/exports/WaterfallChart';
import { DriverCard } from '@/components/exports/DriverCard';
import {
  useCreateVarianceBridge,
  type BridgeAnalysisResponse,
} from '@/lib/api/hooks/useVarianceBridges';

export default function ComparePage() {
  const params = useParams<{ workspaceId: string }>();
  const workspaceId = params.workspaceId;

  const createBridge = useCreateVarianceBridge(workspaceId);
  const [result, setResult] = useState<BridgeAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // TODO(sprint-24): Integrate useRuns(workspaceId) hook to populate
  // RunSelector dropdown. Currently passes empty array, requiring users
  // to use manual UUID entry mode.
  const [runIdA, setRunIdA] = useState('');
  const [runIdB, setRunIdB] = useState('');
  const [manualMode, setManualMode] = useState(false);

  async function handleCompare(runAId: string, runBId: string) {
    setError(null);
    setResult(null);
    try {
      const data = await createBridge.mutateAsync({
        run_a_id: runAId,
        run_b_id: runBId,
      });
      setResult(data);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Comparison failed';
      setError(message);
    }
  }

  async function handleManualCompare() {
    if (!runIdA.trim() || !runIdB.trim()) return;
    await handleCompare(runIdA.trim(), runIdB.trim());
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">
          Compare Runs
        </h1>
        <p className="mt-2 text-slate-500">
          Select two engine runs to generate a variance bridge analysis.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Select Runs</CardTitle>
        </CardHeader>
        <CardContent>
          {manualMode ? (
            <div className="space-y-4">
              <p className="text-sm text-slate-500">
                Enter run IDs directly.{' '}
                <button
                  onClick={() => setManualMode(false)}
                  className="text-primary underline hover:text-primary/80"
                >
                  Switch to dropdown selector
                </button>
              </p>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
                <div className="flex-1 space-y-2">
                  <label
                    htmlFor="manual-run-a"
                    className="text-sm font-medium text-slate-700"
                  >
                    Run A ID
                  </label>
                  <input
                    id="manual-run-a"
                    type="text"
                    value={runIdA}
                    onChange={(e) => setRunIdA(e.target.value)}
                    placeholder="Enter Run A ID"
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                </div>
                <div className="flex-1 space-y-2">
                  <label
                    htmlFor="manual-run-b"
                    className="text-sm font-medium text-slate-700"
                  >
                    Run B ID
                  </label>
                  <input
                    id="manual-run-b"
                    type="text"
                    value={runIdB}
                    onChange={(e) => setRunIdB(e.target.value)}
                    placeholder="Enter Run B ID"
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                </div>
                <button
                  onClick={handleManualCompare}
                  disabled={
                    !runIdA.trim() ||
                    !runIdB.trim() ||
                    runIdA.trim() === runIdB.trim() ||
                    createBridge.isPending
                  }
                  className="inline-flex h-9 shrink-0 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground shadow-xs hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
                >
                  {createBridge.isPending ? 'Comparing...' : 'Compare'}
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <RunSelector
                runs={[]}
                onCompare={handleCompare}
                loading={createBridge.isPending}
              />
              <p className="text-sm text-slate-500">
                No runs loaded yet.{' '}
                <button
                  onClick={() => setManualMode(true)}
                  className="text-primary underline hover:text-primary/80"
                >
                  Enter run IDs manually
                </button>
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6">
          {/* Metadata */}
          <Card>
            <CardHeader>
              <CardTitle>Analysis Metadata</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                <dt className="text-slate-500">Analysis ID</dt>
                <dd className="font-mono text-slate-700">
                  {result.analysis_id}
                </dd>
                <dt className="text-slate-500">Metric Type</dt>
                <dd className="text-slate-700">{result.metric_type}</dd>
                <dt className="text-slate-500">Run A</dt>
                <dd className="font-mono text-slate-700">
                  {result.run_a_id}
                </dd>
                <dt className="text-slate-500">Run B</dt>
                <dd className="font-mono text-slate-700">
                  {result.run_b_id}
                </dd>
                <dt className="text-slate-500">Version</dt>
                <dd className="text-slate-700">{result.analysis_version}</dd>
                <dt className="text-slate-500">Created</dt>
                <dd className="text-slate-700">{result.created_at}</dd>
              </dl>
            </CardContent>
          </Card>

          {/* Waterfall Chart */}
          <div>
            <h2 className="mb-4 text-lg font-semibold text-slate-900">
              Variance Waterfall
            </h2>
            <WaterfallChart
              startValue={result.start_value}
              endValue={result.end_value}
              totalVariance={result.total_variance}
              drivers={result.drivers}
            />
          </div>

          {/* Driver Cards */}
          {result.drivers.length > 0 && (
            <div>
              <h2 className="mb-4 text-lg font-semibold text-slate-900">
                Driver Details
              </h2>
              <div className="space-y-3">
                {result.drivers.map((driver, index) => (
                  <DriverCard
                    key={`${driver.driver_type}-${index}`}
                    driverType={driver.driver_type}
                    description={driver.description}
                    impact={driver.impact}
                    weight={driver.weight}
                    totalVariance={result.total_variance}
                    sourceField={driver.source_field}
                    diffSummary={driver.diff_summary}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
