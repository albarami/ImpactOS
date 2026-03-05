'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';

// ── Types ────────────────────────────────────────────────────────────

interface RunOption {
  run_id: string;
  label?: string;
  created_at: string;
}

interface RunSelectorProps {
  runs: RunOption[];
  onCompare: (runAId: string, runBId: string) => void;
  loading?: boolean;
}

// ── Component ────────────────────────────────────────────────────────

export function RunSelector({ runs, onCompare, loading }: RunSelectorProps) {
  const [runAId, setRunAId] = useState('');
  const [runBId, setRunBId] = useState('');

  const canCompare =
    runAId !== '' && runBId !== '' && runAId !== runBId && !loading;

  function handleCompare() {
    if (canCompare) {
      onCompare(runAId, runBId);
    }
  }

  function displayLabel(run: RunOption): string {
    return run.label || run.run_id;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
        {/* Run A */}
        <div className="flex-1 space-y-2">
          <Label htmlFor="run-a-select">Run A</Label>
          <select
            id="run-a-select"
            value={runAId}
            onChange={(e) => setRunAId(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="">Select a run...</option>
            {runs.map((run) => (
              <option key={run.run_id} value={run.run_id}>
                {displayLabel(run)}
              </option>
            ))}
          </select>
        </div>

        {/* Run B */}
        <div className="flex-1 space-y-2">
          <Label htmlFor="run-b-select">Run B</Label>
          <select
            id="run-b-select"
            value={runBId}
            onChange={(e) => setRunBId(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="">Select a run...</option>
            {runs.map((run) => (
              <option key={run.run_id} value={run.run_id}>
                {displayLabel(run)}
              </option>
            ))}
          </select>
        </div>

        {/* Compare button */}
        <Button
          onClick={handleCompare}
          disabled={!canCompare}
          className="shrink-0"
        >
          {loading ? 'Comparing...' : 'Compare'}
        </Button>
      </div>

      {runAId && runBId && runAId === runBId && (
        <p className="text-sm text-amber-600">
          Please select two different runs to compare.
        </p>
      )}
    </div>
  );
}
