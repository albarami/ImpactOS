'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { useBulkDecisions } from '@/lib/api/hooks/useCompiler';
import type { Suggestion, DecisionMap } from './decision-table';

interface BulkControlsProps {
  workspaceId: string;
  compilationId: string;
  suggestions: Suggestion[];
  decisions: DecisionMap;
  onSubmitted: () => void;
}

export function BulkControls({
  workspaceId,
  compilationId,
  suggestions,
  decisions,
  onSubmitted,
}: BulkControlsProps) {
  const bulkDecisions = useBulkDecisions(workspaceId, compilationId);
  const [bulkAction, setBulkAction] = useState<'accept' | 'reject' | null>(
    null
  );

  const acceptedCount = Object.values(decisions).filter(
    (d) => d === 'accept'
  ).length;
  const rejectedCount = Object.values(decisions).filter(
    (d) => d === 'reject'
  ).length;
  const pendingCount = Object.values(decisions).filter(
    (d) => d === 'pending'
  ).length;

  const hasDecisions = acceptedCount > 0 || rejectedCount > 0;

  async function handleBulkConfirm() {
    if (!bulkAction) return;

    const allDecisions = suggestions.map((s) => ({
      line_item_id: s.line_item_id,
      action: bulkAction as 'accept' | 'reject',
    }));

    try {
      await bulkDecisions.mutateAsync({ decisions: allDecisions });
      toast.success(
        `All ${suggestions.length} suggestions ${bulkAction === 'accept' ? 'accepted' : 'rejected'}`
      );
      onSubmitted();
    } catch {
      toast.error('Failed to submit bulk decisions');
    }

    setBulkAction(null);
  }

  async function handleSubmit() {
    const nonPendingDecisions = Object.entries(decisions)
      .filter(([, action]) => action !== 'pending')
      .map(([lineItemId, action]) => ({
        line_item_id: lineItemId,
        action: action as 'accept' | 'reject',
      }));

    try {
      await bulkDecisions.mutateAsync({ decisions: nonPendingDecisions });
      toast.success('Decisions submitted successfully');
      onSubmitted();
    } catch {
      toast.error('Failed to submit decisions');
    }
  }

  return (
    <div className="flex items-center gap-4">
      <div className="flex-1 text-sm text-muted-foreground">
        {acceptedCount} accepted, {rejectedCount} rejected, {pendingCount}{' '}
        pending
      </div>

      <AlertDialog
        open={bulkAction !== null}
        onOpenChange={(open) => {
          if (!open) setBulkAction(null);
        }}
      >
        <AlertDialogTrigger asChild>
          <Button
            variant="outline"
            onClick={() => setBulkAction('accept')}
          >
            Accept All
          </Button>
        </AlertDialogTrigger>

        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will {bulkAction} all {suggestions.length} suggestions.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleBulkConfirm}>
              Confirm
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Button
        variant="outline"
        onClick={() => setBulkAction('reject')}
      >
        Reject All
      </Button>

      <Button
        onClick={handleSubmit}
        disabled={!hasDecisions || bulkDecisions.isPending}
      >
        {bulkDecisions.isPending ? 'Submitting...' : 'Submit Decisions'}
      </Button>
    </div>
  );
}
