'use client';

import type { ChatMessageResponse, ToolExecutionResult } from '@/lib/api/hooks/useChat';
import { TraceMetadata } from './trace-metadata';
import { cn } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';

interface MessageBubbleProps {
  message: ChatMessageResponse;
  workspaceId?: string;
}

/** Map tool execution status to badge styling. */
function statusBadgeClass(status: string): string {
  switch (status) {
    case 'success':
      return 'bg-green-100 text-green-800 border-green-300';
    case 'error':
      return 'bg-red-100 text-red-800 border-red-300';
    case 'blocked':
      return 'bg-amber-100 text-amber-800 border-amber-300';
    default:
      return 'bg-slate-100 text-slate-600 border-slate-300';
  }
}

/**
 * Extract the effective export status from the tool call results.
 * Returns the status string (e.g. "COMPLETED", "BLOCKED", "FAILED")
 * from the inner result payload, or undefined if not present.
 *
 * The backend _handle_create_export returns {status: "COMPLETED"|"BLOCKED", ...}
 * in the inner result dict (not export_status).
 */
function getExportStatus(
  toolCalls?: ChatMessageResponse['tool_calls']
): string | undefined {
  if (!toolCalls) return undefined;
  for (const tc of toolCalls) {
    if (tc.tool_name !== 'create_export') continue;
    const result = tc.result as ToolExecutionResult | undefined;
    const inner = result?.result as Record<string, unknown> | undefined;
    if (inner?.status && typeof inner.status === 'string') {
      return inner.status as string;
    }
  }
  return undefined;
}

export function MessageBubble({ message, workspaceId }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  const resolvedToolCalls = message.tool_calls?.filter(
    (tc) => tc.result != null
  );

  const exportStatus = getExportStatus(message.tool_calls);

  return (
    <div
      className={cn('flex w-full', isUser ? 'justify-end' : 'justify-start')}
    >
      <div
        className={cn(
          'max-w-[80%] rounded-lg px-4 py-2.5',
          isUser
            ? 'bg-blue-600 text-white'
            : 'border border-slate-200 bg-white text-slate-900'
        )}
      >
        {/* P6-5: Render markdown for assistant messages, plain text for user */}
        {isUser ? (
          <div className="whitespace-pre-wrap text-sm">{message.content}</div>
        ) : (
          <div className="prose prose-sm prose-slate max-w-none text-sm">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )}

        {resolvedToolCalls && resolvedToolCalls.length > 0 && (
          <div className="mt-2 space-y-1">
            {resolvedToolCalls.map((tc, i) => {
              const result = tc.result as ToolExecutionResult | undefined;
              const status = result?.status;
              const errorSummary = result?.error_summary;
              const reasonCode = result?.reason_code;
              const innerResult = result?.result as
                | Record<string, unknown>
                | undefined;
              const blockingReasons = innerResult?.blocking_reasons as
                | string[]
                | undefined;
              const downloadUrl = innerResult?.download_url as
                | string
                | undefined;
              const toolExportStatus = innerResult?.status as
                | string
                | undefined;

              return (
                <details
                  key={i}
                  className={cn(
                    'rounded border text-xs',
                    isUser
                      ? 'border-blue-500 bg-blue-700'
                      : 'border-slate-200 bg-slate-50'
                  )}
                >
                  <summary
                    className={cn(
                      'cursor-pointer px-2 py-1 font-medium flex items-center gap-2',
                      isUser ? 'text-blue-200' : 'text-slate-600'
                    )}
                  >
                    <span>Tool: {tc.tool_name}</span>
                    {status && (
                      <span
                        data-testid={`tool-status-badge-${status}`}
                        className={cn(
                          'inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-semibold leading-none',
                          statusBadgeClass(status)
                        )}
                      >
                        {status}
                      </span>
                    )}
                  </summary>

                  {status === 'error' && errorSummary && (
                    <div className="px-2 py-1 text-red-600 font-medium">
                      {errorSummary}
                    </div>
                  )}

                  {status === 'blocked' && reasonCode && (
                    <div className="px-2 py-1 text-amber-700 font-medium">
                      {reasonCode}
                    </div>
                  )}

                  {blockingReasons && blockingReasons.length > 0 && (
                    <ul
                      data-testid="blocking-reasons-list"
                      className="mx-2 mb-1 list-disc pl-4 text-amber-700"
                    >
                      {blockingReasons.map((reason, j) => (
                        <li key={j}>{reason}</li>
                      ))}
                    </ul>
                  )}

                  {toolExportStatus === 'COMPLETED' && downloadUrl && (
                    <div className="px-2 py-1">
                      <a
                        data-testid="export-download-link"
                        href={downloadUrl}
                        className="inline-flex items-center gap-1 rounded bg-green-50 px-2 py-0.5 text-green-700 underline hover:text-green-900"
                      >
                        Download export
                      </a>
                    </div>
                  )}

                  {/* P6-1: Structured result summary */}
                  {innerResult && Object.keys(innerResult).length > 0 && (
                    <div
                      data-testid="tool-result-summary"
                      className="px-2 py-1 text-xs space-y-0.5"
                    >
                      {Object.entries(innerResult)
                        .filter(
                          ([key]) =>
                            !['status', 'blocking_reasons', 'download_url', 'reason_code', 'export_id', 'run_id'].includes(key)
                        )
                        .slice(0, 5)
                        .map(([key, value]) => (
                          <div
                            key={key}
                            className={cn(
                              'flex justify-between gap-2',
                              isUser ? 'text-blue-200' : 'text-slate-500'
                            )}
                          >
                            <span className="font-medium">
                              {key.replace(/_/g, ' ')}
                            </span>
                            <span className="font-mono truncate max-w-[200px]">
                              {typeof value === 'object' && value !== null
                                ? `{${Object.keys(value as Record<string, unknown>).length} fields}`
                                : String(value)}
                            </span>
                          </div>
                        ))}
                    </div>
                  )}

                  <details className="px-2">
                    <summary
                      className={cn(
                        'cursor-pointer text-[10px] py-0.5',
                        isUser ? 'text-blue-300' : 'text-slate-400'
                      )}
                    >
                      Raw JSON
                    </summary>
                    <pre
                      className={cn(
                        'overflow-auto py-1 font-mono text-[10px]',
                        isUser ? 'text-blue-200' : 'text-slate-600'
                      )}
                    >
                      {JSON.stringify(tc.result, null, 2)}
                    </pre>
                  </details>
                </details>
              );
            })}
          </div>
        )}

        {!isUser && message.trace_metadata && (
          <TraceMetadata
            trace={message.trace_metadata}
            workspaceId={workspaceId}
            exportStatus={exportStatus}
          />
        )}

        <div className="mt-1 text-right text-xs text-slate-400">
          {new Date(message.created_at).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
    </div>
  );
}
