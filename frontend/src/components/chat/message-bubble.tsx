'use client';

import type { ChatMessageResponse } from '@/lib/api/hooks/useChat';
import { TraceMetadata } from './trace-metadata';
import { cn } from '@/lib/utils';

interface MessageBubbleProps {
  message: ChatMessageResponse;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  const resolvedToolCalls = message.tool_calls?.filter(
    (tc) => tc.result != null
  );

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
        <div className="whitespace-pre-wrap text-sm">{message.content}</div>

        {resolvedToolCalls && resolvedToolCalls.length > 0 && (
          <div className="mt-2 space-y-1">
            {resolvedToolCalls.map((tc, i) => (
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
                    'cursor-pointer px-2 py-1 font-medium',
                    isUser ? 'text-blue-200' : 'text-slate-600'
                  )}
                >
                  Tool: {tc.tool_name}
                </summary>
                <pre
                  className={cn(
                    'overflow-auto px-2 py-1 font-mono',
                    isUser ? 'text-blue-200' : 'text-slate-600'
                  )}
                >
                  {JSON.stringify(tc.result, null, 2)}
                </pre>
              </details>
            ))}
          </div>
        )}

        {!isUser && message.trace_metadata && (
          <TraceMetadata trace={message.trace_metadata} />
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
