'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { DepthTraceStepResponse } from '@/lib/api/hooks/useRuns';

interface DepthEngineTracePanelProps {
  steps: DepthTraceStepResponse[];
  planId?: string | null;
}

function formatDetails(details: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(details).map(([key, value]) => [
    key,
    Array.isArray(value) ? value.join(', ') : String(value),
  ]);
}

export function DepthEngineTracePanel({
  steps,
  planId,
}: DepthEngineTracePanelProps) {
  const [expanded, setExpanded] = useState(false);
  if (steps.length === 0) return null;

  const totalDuration = steps.reduce((sum, step) => sum + (step.duration_ms ?? 0), 0);
  const totalTokens = steps.reduce(
    (sum, step) => sum + (step.input_tokens ?? 0) + (step.output_tokens ?? 0),
    0
  );

  return (
    <Card data-testid="depth-engine-trace-panel">
      <CardHeader>
        <CardTitle className="text-base">AL-MUHASIBI DEPTH ENGINE TRACE</CardTitle>
        {planId && <p className="font-mono text-xs text-muted-foreground">{planId}</p>}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
          <span>{steps.length} steps</span>
          <span>{(totalDuration / 1000).toFixed(1)}s total</span>
          <span>{totalTokens.toLocaleString()} tokens</span>
        </div>
        <button
          type="button"
          className="text-sm font-medium text-primary"
          onClick={() => setExpanded((prev) => !prev)}
        >
          {expanded ? 'Hide trace details' : 'Show trace details'}
        </button>
        {expanded && (
          <div className="space-y-3">
            {steps.map((step) => (
              <div key={step.step} className="rounded-md border p-3" data-testid={`trace-step-${step.step}`}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-medium">{step.step_name}</div>
                    <div className="text-xs text-muted-foreground">
                      {step.provider ?? 'unknown provider'}
                      {step.model ? ` / ${step.model}` : ''}
                    </div>
                  </div>
                  <div className="text-right text-xs text-muted-foreground">
                    <div>{step.generation_mode ?? 'UNKNOWN'}</div>
                    <div>{step.duration_ms ?? 0}ms</div>
                  </div>
                </div>
                {formatDetails(step.details).length > 0 && (
                  <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                    {formatDetails(step.details).map(([key, value]) => (
                      <div key={key}>
                        <dt className="text-xs uppercase tracking-wide text-muted-foreground">{key}</dt>
                        <dd>{value}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
