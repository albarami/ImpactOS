'use client';

import { useMemo, useState, useCallback } from 'react';
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

// ── Types ──────────────────────────────────────────────────────────────

export interface Suggestion {
  line_item_id: string;
  sector_code: string;
  confidence: number;
  explanation: string;
}

export type DecisionMap = Record<string, 'accept' | 'reject' | 'pending'>;

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

function statusColor(status: 'accept' | 'reject' | 'pending'): string {
  if (status === 'accept') return 'bg-green-600';
  if (status === 'reject') return 'bg-red-500';
  return 'bg-gray-400';
}

function statusLabel(status: 'accept' | 'reject' | 'pending'): string {
  if (status === 'accept') return 'accepted';
  if (status === 'reject') return 'rejected';
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
      initial[s.line_item_id] = 'pending';
    }
    return initial;
  });

  const handleDecision = useCallback(
    (lineItemId: string, action: 'accept' | 'reject') => {
      setDecisions((prev) => {
        const next = { ...prev, [lineItemId]: action };
        onDecisionsChange(next);
        return next;
      });
    },
    [onDecisionsChange]
  );

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
        cell: ({ row }) => (
          <span className="font-mono text-sm">{row.original.sector_code}</span>
        ),
      },
      {
        id: 'status',
        header: 'Status',
        cell: ({ row }) => {
          const status = decisions[row.original.line_item_id] ?? 'pending';
          return (
            <Badge className={`${statusColor(status)} text-white`}>
              {statusLabel(status)}
            </Badge>
          );
        },
      },
      {
        id: 'action',
        header: 'Action',
        cell: ({ row }) => (
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleDecision(row.original.line_item_id, 'accept')}
            >
              Accept
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleDecision(row.original.line_item_id, 'reject')}
            >
              Reject
            </Button>
          </div>
        ),
      },
    ],
    [decisions, handleDecision]
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
