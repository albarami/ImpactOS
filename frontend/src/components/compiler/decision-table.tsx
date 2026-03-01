'use client';

import { useMemo, useState, useCallback, useRef } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from '@tanstack/react-table';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { DecisionMap, DecisionEntry } from '@/lib/api/hooks/useCompiler';

// ── Types ──────────────────────────────────────────────────────────────

export type { DecisionMap, DecisionEntry };

export interface Suggestion {
  line_item_id: string;
  sector_code: string;
  confidence: number;
  explanation: string;
}

interface DecisionTableProps {
  suggestions: Suggestion[];
  onDecisionsChange: (decisions: DecisionMap) => void;
}

// ── Helpers ────────────────────────────────────────────────────────────

function confidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'bg-green-600';
  if (confidence >= 0.5) return 'bg-amber-500';
  return 'bg-red-500';
}

function confidencePercent(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

function statusColor(action: DecisionEntry['action']): string {
  if (action === 'accept') return 'bg-green-600';
  if (action === 'reject') return 'bg-red-500';
  if (action === 'override') return 'bg-amber-500';
  return 'bg-gray-400';
}

function statusLabel(action: DecisionEntry['action']): string {
  if (action === 'accept') return 'accepted';
  if (action === 'reject') return 'rejected';
  if (action === 'override') return 'overridden';
  return 'pending';
}

// ── Component ──────────────────────────────────────────────────────────

export function DecisionTable({
  suggestions,
  onDecisionsChange,
}: DecisionTableProps) {
  const [decisions, setDecisions] = useState<DecisionMap>(() => {
    const initial: DecisionMap = {};
    for (const s of suggestions) {
      initial[s.line_item_id] = { action: 'pending' };
    }
    return initial;
  });

  // Track which row has the override input open
  const [overrideOpenFor, setOverrideOpenFor] = useState<string | null>(null);
  // Use a ref for the override input value to avoid re-render cascades
  // through the column memoization chain
  const overrideInputRef = useRef('');
  // Counter to force re-render of just the input display value
  const [, setInputTick] = useState(0);

  const handleDecision = useCallback(
    (lineItemId: string, action: 'accept' | 'reject') => {
      setDecisions((prev) => {
        const next = { ...prev, [lineItemId]: { action } };
        onDecisionsChange(next);
        return next;
      });
      // Close override input if open for this row
      setOverrideOpenFor((current) => {
        if (current === lineItemId) {
          overrideInputRef.current = '';
          return null;
        }
        return current;
      });
    },
    [onDecisionsChange]
  );

  const handleOverrideOpen = useCallback((lineItemId: string) => {
    overrideInputRef.current = '';
    setOverrideOpenFor(lineItemId);
  }, []);

  const handleOverrideConfirm = useCallback(
    (lineItemId: string) => {
      const value = overrideInputRef.current.trim();
      if (!value) return;
      setDecisions((prev) => {
        const next: DecisionMap = {
          ...prev,
          [lineItemId]: { action: 'override', overrideSector: value },
        };
        onDecisionsChange(next);
        return next;
      });
      overrideInputRef.current = '';
      setOverrideOpenFor(null);
    },
    [onDecisionsChange]
  );

  const handleOverrideCancel = useCallback(() => {
    overrideInputRef.current = '';
    setOverrideOpenFor(null);
  }, []);

  const handleOverrideInputChange = useCallback((value: string) => {
    overrideInputRef.current = value;
    setInputTick((t) => t + 1);
  }, []);

  const columns = useMemo<ColumnDef<Suggestion>[]>(
    () => [
      {
        id: 'line_item',
        header: 'Line Item',
        cell: ({ row }) => (
          <span className="font-mono text-xs">
            {row.original.line_item_id}
          </span>
        ),
      },
      {
        id: 'explanation',
        header: 'Explanation',
        cell: ({ row }) => (
          <span className="block max-w-xs truncate" title={row.original.explanation}>
            {row.original.explanation}
          </span>
        ),
      },
      {
        id: 'confidence',
        header: 'Confidence',
        cell: ({ row }) => (
          <Badge className={`${confidenceColor(row.original.confidence)} text-white`}>
            {confidencePercent(row.original.confidence)}
          </Badge>
        ),
      },
      {
        id: 'sector',
        header: 'Sector',
        cell: ({ row }) => {
          const entry = decisions[row.original.line_item_id];
          const sectorCode =
            entry?.action === 'override' && entry.overrideSector
              ? entry.overrideSector
              : row.original.sector_code;
          return <span className="font-mono text-sm">{sectorCode}</span>;
        },
      },
      {
        id: 'status',
        header: 'Status',
        cell: ({ row }) => {
          const entry = decisions[row.original.line_item_id];
          const action = entry?.action ?? 'pending';
          return (
            <Badge className={`${statusColor(action)} text-white`}>
              {statusLabel(action)}
            </Badge>
          );
        },
      },
      {
        id: 'action',
        header: 'Action',
        cell: ({ row }) => {
          const lineItemId = row.original.line_item_id;
          const isOverrideOpen = overrideOpenFor === lineItemId;

          return (
            <div className="flex flex-col gap-2">
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleDecision(lineItemId, 'accept')}
                >
                  Accept
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleDecision(lineItemId, 'reject')}
                >
                  Reject
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleOverrideOpen(lineItemId)}
                >
                  Override
                </Button>
              </div>
              {isOverrideOpen && (
                <div className="flex gap-2 items-center">
                  <Input
                    type="text"
                    placeholder="Sector code"
                    defaultValue=""
                    onChange={(e) => handleOverrideInputChange(e.target.value)}
                    className="w-24 h-8 text-xs"
                    aria-label="Override sector code"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleOverrideConfirm(lineItemId)}
                  >
                    Save
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={handleOverrideCancel}
                  >
                    Cancel
                  </Button>
                </div>
              )}
            </div>
          );
        },
      },
    ],
    [decisions, handleDecision, handleOverrideOpen, handleOverrideConfirm, handleOverrideCancel, handleOverrideInputChange, overrideOpenFor]
  );

  const table = useReactTable({
    data: suggestions,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((headerGroup) => (
          <TableRow key={headerGroup.id}>
            {headerGroup.headers.map((header) => (
              <TableHead key={header.id}>
                {header.isPlaceholder
                  ? null
                  : flexRender(
                      header.column.columnDef.header,
                      header.getContext()
                    )}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={columns.length} className="text-center">
              No suggestions found.
            </TableCell>
          </TableRow>
        ) : (
          table.getRowModel().rows.map((row) => (
            <TableRow key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}
