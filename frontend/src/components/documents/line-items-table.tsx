'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
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
import { Skeleton } from '@/components/ui/skeleton';
import { useLineItems, type BoQLineItem } from '@/lib/api/hooks/useDocuments';

interface LineItemsTableProps {
  workspaceId: string;
  docId: string;
}

function formatNumber(value: number | null): string {
  if (value === null || value === undefined) return '-';
  return value.toLocaleString('en-US');
}

function completenessColor(score: number | null): string {
  if (score === null || score === undefined) return 'bg-slate-400';
  if (score >= 0.8) return 'bg-green-600';
  if (score >= 0.5) return 'bg-amber-500';
  return 'bg-red-500';
}

function completenessPercent(score: number | null): string {
  if (score === null || score === undefined) return '-';
  return `${Math.round(score * 100)}%`;
}

export function LineItemsTable({ workspaceId, docId }: LineItemsTableProps) {
  const { data, isLoading } = useLineItems(workspaceId, docId);
  const [sorting, setSorting] = useState<SortingState>([]);

  const columns = useMemo<ColumnDef<BoQLineItem>[]>(
    () => [
      {
        id: 'index',
        header: '#',
        cell: ({ row }) => row.index + 1,
        enableSorting: false,
      },
      {
        accessorKey: 'description',
        header: 'Description',
        cell: ({ getValue }) => {
          const val = getValue<string>();
          return (
            <span className="block max-w-xs truncate" title={val}>
              {val}
            </span>
          );
        },
      },
      {
        accessorKey: 'total_value',
        header: 'Total Value',
        cell: ({ getValue }) => formatNumber(getValue<number | null>()),
      },
      {
        accessorKey: 'unit',
        header: 'Unit',
        cell: ({ getValue }) => getValue<string | null>() ?? '-',
      },
      {
        accessorKey: 'currency_code',
        header: 'Currency',
        cell: ({ getValue }) => getValue<string>(),
      },
      {
        accessorKey: 'completeness_score',
        header: 'Completeness',
        cell: ({ getValue }) => {
          const score = getValue<number | null>();
          return (
            <Badge className={`${completenessColor(score)} text-white`}>
              {completenessPercent(score)}
            </Badge>
          );
        },
      },
    ],
    []
  );

  const table = useReactTable({
    data: data?.items ?? [],
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-500">Loading line items...</p>
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead
                  key={header.id}
                  className={
                    header.column.getCanSort()
                      ? 'cursor-pointer select-none'
                      : ''
                  }
                  onClick={header.column.getToggleSortingHandler()}
                >
                  {header.isPlaceholder
                    ? null
                    : flexRender(
                        header.column.columnDef.header,
                        header.getContext()
                      )}
                  {{
                    asc: ' \u2191',
                    desc: ' \u2193',
                  }[header.column.getIsSorted() as string] ?? null}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columns.length} className="text-center">
                No line items found.
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

      {data && data.items.length > 0 && (
        <div className="flex justify-end">
          <Button asChild>
            <Link href={`/w/${workspaceId}/documents/${docId}/compile`}>
              Proceed to Compile
            </Link>
          </Button>
        </div>
      )}
    </div>
  );
}
