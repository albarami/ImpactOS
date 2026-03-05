'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import {
  useChatSessions,
  useCreateSession,
} from '@/lib/api/hooks/useChat';
import { ChatInterface } from '@/components/chat/chat-interface';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { MessageSquare, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function ChatPage() {
  const params = useParams<{ workspaceId: string }>();
  const workspaceId = params.workspaceId;

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  const {
    data: sessionsData,
    isLoading: isLoadingSessions,
  } = useChatSessions(workspaceId);

  const createSession = useCreateSession(workspaceId);

  const sessions = sessionsData?.sessions ?? [];

  const handleNewSession = () => {
    createSession.mutate(
      { title: undefined },
      {
        onSuccess: (session) => {
          setActiveSessionId(session.session_id);
        },
      }
    );
  };

  return (
    <div className="flex h-full -m-6">
      {/* Session sidebar */}
      <div className="flex w-64 flex-col border-r border-slate-200 bg-slate-50">
        <div className="flex items-center justify-between border-b border-slate-200 px-3 py-3">
          <h2 className="text-sm font-semibold text-slate-700">Sessions</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleNewSession}
            disabled={createSession.isPending}
            aria-label="New session"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <ScrollArea className="flex-1">
          <div className="space-y-0.5 p-2">
            {isLoadingSessions && (
              <>
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </>
            )}
            {sessions.map((session) => (
              <button
                key={session.session_id}
                onClick={() => setActiveSessionId(session.session_id)}
                className={cn(
                  'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
                  activeSessionId === session.session_id
                    ? 'bg-slate-200 text-slate-900'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                )}
              >
                <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">
                  {session.title || 'New conversation'}
                </span>
              </button>
            ))}
            {!isLoadingSessions && sessions.length === 0 && (
              <div className="px-2 py-4 text-center text-xs text-slate-400">
                No conversations yet
              </div>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Chat area */}
      <div className="flex flex-1 flex-col">
        {activeSessionId ? (
          <ChatInterface
            workspaceId={workspaceId}
            sessionId={activeSessionId}
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-slate-400">
            <MessageSquare className="h-12 w-12 text-slate-300" />
            <div className="text-center">
              <p className="text-lg font-medium text-slate-600">
                Economist Copilot
              </p>
              <p className="mt-1 text-sm">
                Start a new conversation to build scenarios and run analyses.
              </p>
            </div>
            <Button onClick={handleNewSession} disabled={createSession.isPending}>
              <Plus className="mr-2 h-4 w-4" />
              New Conversation
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
