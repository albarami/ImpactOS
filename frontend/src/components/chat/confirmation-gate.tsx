'use client';

import { useState } from 'react';
import type { ToolCall } from '@/lib/api/hooks/useChat';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

interface ConfirmationGateProps {
  toolCall: ToolCall;
  onApprove: () => void;
  onReject: (reason: string) => void;
  onEdit: (editedContent: string) => void;
  disabled?: boolean;
}

export function ConfirmationGate({
  toolCall,
  onApprove,
  onReject,
  onEdit,
  disabled = false,
}: ConfirmationGateProps) {
  const [mode, setMode] = useState<'idle' | 'editing' | 'rejecting'>('idle');
  const [editText, setEditText] = useState('');
  const [rejectReason, setRejectReason] = useState('');

  const handleEdit = () => {
    if (mode === 'editing') {
      onEdit(editText);
      setMode('idle');
      setEditText('');
    } else {
      setMode('editing');
    }
  };

  const handleReject = () => {
    if (mode === 'rejecting') {
      onReject(rejectReason || 'Rejected by user');
      setMode('idle');
      setRejectReason('');
    } else {
      setMode('rejecting');
    }
  };

  return (
    <Card className="border-amber-200 bg-amber-50">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-amber-800">
          Confirmation Required
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="text-xs text-amber-700">
          The assistant wants to execute{' '}
          <code className="rounded bg-amber-100 px-1 py-0.5 font-mono font-bold">
            {toolCall.tool_name}
          </code>
        </div>
        <pre className="max-h-40 overflow-auto rounded-md bg-white p-2 text-xs text-slate-700">
          {JSON.stringify(toolCall.arguments, null, 2)}
        </pre>
        {mode === 'editing' && (
          <Textarea
            placeholder="Describe your modifications..."
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            className="text-sm"
            data-testid="edit-input"
          />
        )}
        {mode === 'rejecting' && (
          <Textarea
            placeholder="Reason for rejection (optional)..."
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            className="text-sm"
            data-testid="reject-input"
          />
        )}
      </CardContent>
      <CardFooter className="gap-2">
        <Button
          size="sm"
          onClick={onApprove}
          disabled={disabled}
          className="bg-green-600 hover:bg-green-700"
        >
          Approve
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handleEdit}
          disabled={disabled}
        >
          {mode === 'editing' ? 'Send Edit' : 'Edit'}
        </Button>
        <Button
          size="sm"
          variant="destructive"
          onClick={handleReject}
          disabled={disabled}
        >
          {mode === 'rejecting' ? 'Confirm Reject' : 'Reject'}
        </Button>
      </CardFooter>
    </Card>
  );
}
