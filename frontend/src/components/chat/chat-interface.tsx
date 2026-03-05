'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  useChatSession,
  useSendMessage,
  hasPendingConfirmation,
  getPendingToolCall,
} from '@/lib/api/hooks/useChat';
import { MessageBubble } from './message-bubble';
import { ConfirmationGate } from './confirmation-gate';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Send, Loader2 } from 'lucide-react';

interface ChatInterfaceProps {
  workspaceId: string;
  sessionId: string;
}

export function ChatInterface({ workspaceId, sessionId }: ChatInterfaceProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    data: sessionData,
    isLoading: isLoadingSession,
    error: sessionError,
  } = useChatSession(workspaceId, sessionId);

  const sendMessage = useSendMessage(workspaceId, sessionId);

  const messages = sessionData?.messages ?? [];
  const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;
  const pendingToolCall =
    lastMessage && hasPendingConfirmation(lastMessage)
      ? getPendingToolCall(lastMessage)
      : null;

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || sendMessage.isPending) return;
    sendMessage.mutate({ content: trimmed });
    setInput('');
  }, [input, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleApprove = useCallback(() => {
    sendMessage.mutate({
      content: 'Approved. Please proceed.',
      confirm_scenario: true,
    });
  }, [sendMessage]);

  const handleReject = useCallback(
    (reason: string) => {
      sendMessage.mutate({
        content: `Rejected: ${reason}`,
        confirm_scenario: false,
      });
    },
    [sendMessage]
  );

  const handleEdit = useCallback(
    (editedContent: string) => {
      sendMessage.mutate({
        content: `Please modify: ${editedContent}`,
        confirm_scenario: false,
      });
    },
    [sendMessage]
  );

  // ── Loading state ────────────────────────────────────────────────
  if (isLoadingSession) {
    return (
      <div className="flex h-full flex-col space-y-4 p-4" data-testid="chat-loading">
        <Skeleton className="h-10 w-3/4" />
        <Skeleton className="h-10 w-1/2 self-end" />
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-10 w-1/2 self-end" />
      </div>
    );
  }

  // ── Error state ──────────────────────────────────────────────────
  if (sessionError) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="text-center">
          <p className="text-sm font-medium text-red-600">
            Failed to load chat session
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {sessionError.message}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Message list */}
      <ScrollArea className="flex-1 px-4 py-4">
        <div className="space-y-3">
          {messages.length === 0 && (
            <div className="flex h-40 items-center justify-center text-sm text-slate-400">
              Send a message to start the conversation.
            </div>
          )}
          {messages.map((msg) => (
            <MessageBubble key={msg.message_id} message={msg} workspaceId={workspaceId} />
          ))}
          {sendMessage.isPending && (
            <div className="flex items-center gap-2 text-sm text-slate-400" data-testid="sending-indicator">
              <Loader2 className="h-4 w-4 animate-spin" />
              Thinking...
            </div>
          )}
          {sendMessage.isError && (
            <div className="text-sm text-red-500" data-testid="send-error">
              Failed to send message: {sendMessage.error.message}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Confirmation gate */}
      {pendingToolCall && (
        <div className="border-t border-slate-200 px-4 py-3">
          <ConfirmationGate
            toolCall={pendingToolCall}
            onApprove={handleApprove}
            onReject={handleReject}
            onEdit={handleEdit}
            disabled={sendMessage.isPending}
          />
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-slate-200 px-4 py-3">
        <div className="flex items-end gap-2">
          <Textarea
            placeholder="Ask the economist copilot..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            className="min-h-[44px] max-h-32 resize-none text-sm"
            rows={1}
            disabled={sendMessage.isPending}
            aria-label="Chat message input"
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || sendMessage.isPending}
            size="sm"
            className="shrink-0"
            aria-label="Send message"
          >
            {sendMessage.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
