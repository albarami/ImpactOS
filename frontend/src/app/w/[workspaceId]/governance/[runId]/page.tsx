'use client';

import { useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { GovernanceStatusDisplay } from '@/components/governance/status-display';
import { ClaimExtraction } from '@/components/governance/claim-extraction';
import { AssumptionCreate } from '@/components/governance/assumption-create';
import { AssumptionApprove } from '@/components/governance/assumption-approve';
import { PublicationGate } from '@/components/governance/publication-gate';
import {
  useGovernanceStatus,
  useBlockingReasons,
} from '@/lib/api/hooks/useGovernance';

export default function GovernanceRunPage() {
  const params = useParams<{ workspaceId: string; runId: string }>();
  const workspaceId = params.workspaceId;
  const runId = params.runId;

  const { data: statusData } = useGovernanceStatus(workspaceId, runId);
  const { data: blockingData } = useBlockingReasons(workspaceId, runId);

  const [lastCreatedAssumptionId, setLastCreatedAssumptionId] = useState<
    string | null
  >(null);

  const handleAssumptionCreated = useCallback((assumptionId: string) => {
    setLastCreatedAssumptionId(assumptionId);
  }, []);

  const handleAssumptionApproved = useCallback(() => {
    setLastCreatedAssumptionId(null);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Governance</h1>
        <p className="mt-1 text-sm text-slate-500 font-mono">{runId}</p>
      </div>

      {/* Governance Status */}
      <GovernanceStatusDisplay workspaceId={workspaceId} runId={runId} />

      {/* Claim Extraction */}
      <ClaimExtraction workspaceId={workspaceId} runId={runId} />

      {/* Assumptions */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <AssumptionCreate
          workspaceId={workspaceId}
          onCreated={handleAssumptionCreated}
        />
        {lastCreatedAssumptionId && (
          <AssumptionApprove
            workspaceId={workspaceId}
            assumptionId={lastCreatedAssumptionId}
            onApproved={handleAssumptionApproved}
          />
        )}
      </div>

      {/* Publication Gate */}
      <PublicationGate
        workspaceId={workspaceId}
        runId={runId}
        nffPassed={statusData?.nff_passed ?? false}
        blockingReasons={blockingData?.blocking_reasons ?? []}
      />
    </div>
  );
}
