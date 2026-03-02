'use client';

import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface BlockingReason {
  claim_id: string;
  current_status: string;
  reason: string;
}

interface PublicationGateProps {
  workspaceId: string;
  runId: string;
  nffPassed: boolean;
  blockingReasons: BlockingReason[];
}

export function PublicationGate({
  workspaceId,
  runId,
  nffPassed,
  blockingReasons,
}: PublicationGateProps) {
  if (nffPassed) {
    return (
      <Card className="border-emerald-500 border-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-3">
            Publication Gate: PASS
            <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">
              PASS
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            All governance checks have passed. This run is cleared for export.
          </p>
          <Button asChild>
            <Link href={`/w/${workspaceId}/exports/new?runId=${runId}`}>
              Proceed to Export
            </Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-red-500 border-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-3">
          Publication Gate: BLOCKED
          <Badge className="bg-red-100 text-red-800 hover:bg-red-100">
            BLOCKED
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {blockingReasons.length > 0 && (
          <ul className="space-y-2 mb-4">
            {blockingReasons.map((br) => (
              <li key={br.claim_id} className="flex items-start gap-2 text-sm">
                <Badge variant="outline" className="shrink-0 mt-0.5">
                  {br.current_status}
                </Badge>
                <span>{br.reason}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="text-sm text-red-600 font-medium">
          Resolve Issues before this run can be exported.
        </p>
      </CardContent>
    </Card>
  );
}
