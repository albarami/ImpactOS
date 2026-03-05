'use client';

import type { TraceMetadata as TraceMetadataType } from '@/lib/api/hooks/useChat';
import { Badge } from '@/components/ui/badge';

interface TraceMetadataProps {
  trace: TraceMetadataType;
  workspaceId?: string;
}

export function TraceMetadata({ trace, workspaceId }: TraceMetadataProps) {
  const hasContent =
    trace.run_id ||
    trace.scenario_spec_id ||
    trace.model_version_id ||
    (trace.assumptions && trace.assumptions.length > 0) ||
    trace.confidence;

  if (!hasContent) return null;

  return (
    <details className="mt-2 rounded-md border border-slate-200 bg-slate-50 text-xs text-slate-500">
      <summary className="cursor-pointer px-3 py-1.5 font-medium text-slate-600 hover:text-slate-800">
        Trace Details
      </summary>
      <div className="space-y-1.5 border-t border-slate-200 px-3 py-2">
        {trace.run_id && (
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-600">Run:</span>
            {workspaceId ? (
              <a
                data-testid="trace-run-link"
                href={`/w/${workspaceId}/runs/${trace.run_id}`}
                className="rounded bg-slate-100 px-1 py-0.5 font-mono text-blue-600 underline hover:text-blue-800"
              >
                {trace.run_id}
              </a>
            ) : (
              <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-slate-700">
                {trace.run_id}
              </code>
            )}
          </div>
        )}
        {trace.scenario_spec_id && (
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-600">Scenario:</span>
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-slate-700">
              {trace.scenario_spec_id}
            </code>
            {trace.scenario_spec_version != null && (
              <span className="text-slate-400">
                v{trace.scenario_spec_version}
              </span>
            )}
          </div>
        )}
        {trace.model_version_id && (
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-600">Model:</span>
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-slate-700">
              {trace.model_version_id}
            </code>
          </div>
        )}
        {trace.io_table && (
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-600">I-O Table:</span>
            <span>{trace.io_table}</span>
          </div>
        )}
        {trace.multiplier_type && (
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-600">Multiplier:</span>
            <span>{trace.multiplier_type}</span>
          </div>
        )}
        {trace.confidence && (
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-600">Confidence:</span>
            <Badge variant="secondary">{trace.confidence}</Badge>
          </div>
        )}
        {trace.confidence_reasons && trace.confidence_reasons.length > 0 && (
          <div>
            <span className="font-medium text-slate-600">Reasons:</span>
            <ul className="ml-4 mt-0.5 list-disc">
              {trace.confidence_reasons.map((reason, i) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          </div>
        )}
        {trace.assumptions && trace.assumptions.length > 0 && (
          <div>
            <span className="font-medium text-slate-600">Assumptions:</span>
            <ul className="ml-4 mt-0.5 list-disc">
              {trace.assumptions.map((assumption, i) => (
                <li key={i}>{assumption}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}
