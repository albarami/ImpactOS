'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useGovernanceStatus,
  useBlockingReasons,
} from '@/lib/api/hooks/useGovernance';

interface GovernanceStatusDisplayProps {
  workspaceId: string;
  runId: string;
}

export function GovernanceStatusDisplay({
  workspaceId,
  runId,
}: GovernanceStatusDisplayProps) {
  const { data, isLoading, isError } = useGovernanceStatus(
    workspaceId,
    runId
  );
  const { data: blockingData } = useBlockingReasons(workspaceId, runId);

  if (isLoading) {
    return (
      <div className="space-y-4" data-testid="governance-loading">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <p className="text-red-600">Failed to load governance status</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <div className="space-y-4">
      {/* NFF Status Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3">
            NFF Status
            {data.nff_passed ? (
              <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">
                PASS
              </Badge>
            ) : (
              <Badge className="bg-red-100 text-red-800 hover:bg-red-100">
                BLOCKED
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            {/* Claims Counts */}
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-2">
                Claims
              </p>
              <div className="grid grid-cols-3 gap-2">
                <div className="text-center">
                  <p className="text-2xl font-bold">{data.claims_total}</p>
                  <p className="text-xs text-muted-foreground">Total</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-emerald-600">
                    {data.claims_resolved}
                  </p>
                  <p className="text-xs text-muted-foreground">Resolved</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-red-600">
                    {data.claims_unresolved}
                  </p>
                  <p className="text-xs text-muted-foreground">Unresolved</p>
                </div>
              </div>
            </div>

            {/* Assumptions Counts */}
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-2">
                Assumptions
              </p>
              <div className="grid grid-cols-2 gap-2">
                <div className="text-center">
                  <p className="text-2xl font-bold">{data.assumptions_total}</p>
                  <p className="text-xs text-muted-foreground">Total</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-emerald-600">
                    {data.assumptions_approved}
                  </p>
                  <p className="text-xs text-muted-foreground">Approved</p>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Blocking Reasons */}
      {!data.nff_passed && blockingData?.blocking_reasons && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Blocking Reasons</CardTitle>
          </CardHeader>
          <CardContent>
            {blockingData.blocking_reasons.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No specific blocking reasons reported.
              </p>
            ) : (
              <ul className="space-y-2">
                {blockingData.blocking_reasons.map((br) => (
                  <li
                    key={br.claim_id}
                    className="flex items-start gap-2 text-sm"
                  >
                    <Badge variant="outline" className="shrink-0 mt-0.5">
                      {br.current_status}
                    </Badge>
                    <span>{br.reason}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
