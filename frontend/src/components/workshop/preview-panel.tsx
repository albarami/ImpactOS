'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { PreviewResultSet } from '@/lib/api/hooks/useWorkshop';

interface PreviewPanelProps {
  resultSets: PreviewResultSet[];
  isLoading: boolean;
  error?: string;
}

export function PreviewPanel({ resultSets, isLoading, error }: PreviewPanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Preview Results</CardTitle>
      </CardHeader>
      <CardContent>
        {error && (
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        )}

        {isLoading && (
          <div className="space-y-3" data-testid="preview-skeleton">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )}

        {!isLoading && !error && resultSets.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Adjust sliders to see a preview of engine results.
          </p>
        )}

        {!isLoading &&
          !error &&
          resultSets.map((rs) => {
            const entries = Object.entries(rs.values);
            return (
              <div key={rs.result_id} className="mb-4 last:mb-0">
                <h3 className="mb-2 text-sm font-medium">{rs.metric_type}</h3>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Sector</TableHead>
                      <TableHead className="text-right">Value</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {entries.map(([sector, val]) => (
                      <TableRow key={sector}>
                        <TableCell>{sector}</TableCell>
                        <TableCell className="text-right">
                          {val.toLocaleString()}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            );
          })}
      </CardContent>
    </Card>
  );
}
