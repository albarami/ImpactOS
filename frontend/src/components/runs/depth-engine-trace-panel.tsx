'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface StepTrace {
  step: number;
  step_name: string;
  provider?: string;
  model?: string;
  generation_mode?: string;
  duration_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
}

interface DepthEngineTracePanelProps {
  steps: StepTrace[];
  planId?: string;
}

/**
 * P6-4: Depth Engine Trace Panel — displays the 5-step
 * Al-Muhasabi pipeline execution metadata for transparency.
 * Shows which steps ran, LLM vs fallback mode, token usage, and timing.
 */
export function DepthEngineTracePanel({
  steps,
  planId,
}: DepthEngineTracePanelProps) {
  if (steps.length === 0) return null;

  const totalDuration = steps.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0);
  const totalTokens = steps.reduce(
    (sum, s) => sum + (s.input_tokens ?? 0) + (s.output_tokens ?? 0),
    0
  );

  return (
    <Card data-testid="depth-engine-trace-panel">
      <CardHeader>
        <CardTitle className="text-base">Depth Engine Trace</CardTitle>
        {planId && (
          <p className="text-xs text-muted-foreground font-mono">{planId}</p>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Summary */}
        <div className="flex gap-6 text-sm text-muted-foreground">
          <span>{steps.length} steps</span>
          {totalDuration > 0 && <span>{(totalDuration / 1000).toFixed(1)}s total</span>}
          {totalTokens > 0 && <span>{totalTokens.toLocaleString()} tokens</span>}
        </div>

        {/* Step list */}
        <div className="space-y-2">
          {steps.map((step) => (
            <div
              key={step.step}
              className="flex items-center gap-3 rounded-md border p-3"
              data-testid={`trace-step-${step.step}`}
            >
              {/* Step number badge */}
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold">
                {step.step}
              </div>

              {/* Step details */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{step.step_name}</span>
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      step.generation_mode === 'LLM'
                        ? 'bg-blue-100 text-blue-800'
                        : 'bg-gray-100 text-gray-800'
                    }`}
                  >
                    {step.generation_mode ?? 'UNKNOWN'}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {step.provider && <span>{step.provider}</span>}
                  {step.model && <span> / {step.model}</span>}
                  {step.duration_ms != null && (
                    <span> — {step.duration_ms}ms</span>
                  )}
                </div>
              </div>

              {/* Token usage */}
              {(step.input_tokens != null || step.output_tokens != null) && (
                <div className="text-xs text-muted-foreground text-right">
                  <div>{step.input_tokens ?? 0} in</div>
                  <div>{step.output_tokens ?? 0} out</div>
                </div>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
