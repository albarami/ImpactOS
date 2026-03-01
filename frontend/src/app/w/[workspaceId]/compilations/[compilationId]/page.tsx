'use client';

import { useState, useCallback } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCompilationData } from '@/lib/api/hooks/useCompiler';
import { DecisionTable, type DecisionMap } from '@/components/compiler/decision-table';
import { BulkControls } from '@/components/compiler/bulk-controls';
import { ConfidenceSummary } from '@/components/compiler/confidence-summary';

export default function CompilationDetailPage() {
  const params = useParams<{ workspaceId: string; compilationId: string }>();
  const workspaceId = params.workspaceId;
  const compilationId = params.compilationId;

  const compilationData = useCompilationData(compilationId);
  const [decisions, setDecisions] = useState<DecisionMap>({});
  const [submitted, setSubmitted] = useState(false);

  const handleDecisionsChange = useCallback((newDecisions: DecisionMap) => {
    setDecisions(newDecisions);
  }, []);

  const handleSubmitted = useCallback(() => {
    setSubmitted(true);
  }, []);

  // Cache is empty — data unavailable
  if (!compilationData) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Compilation Review
          </h1>
        </div>
        <Card>
          <CardContent className="py-8 text-center">
            <p className="text-muted-foreground">
              Compilation data unavailable — please recompile.
            </p>
            <Button asChild className="mt-4" variant="outline">
              <Link href={`/w/${workspaceId}/documents`}>
                Back to Documents
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const { suggestions, high_confidence, medium_confidence, low_confidence } =
    compilationData;

  const acceptedCount = Object.values(decisions).filter(
    (d) => d === 'accept'
  ).length;
  const rejectedCount = Object.values(decisions).filter(
    (d) => d === 'reject'
  ).length;
  const pendingCount = suggestions.length - acceptedCount - rejectedCount;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">
          Compilation Review
        </h1>
        <p className="mt-1 text-sm text-slate-500 font-mono">
          {compilationId}
        </p>
      </div>

      {/* Confidence Summary */}
      <Card>
        <CardHeader>
          <CardTitle>Confidence Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <ConfidenceSummary
            highConfidence={high_confidence}
            mediumConfidence={medium_confidence}
            lowConfidence={low_confidence}
            accepted={acceptedCount}
            rejected={rejectedCount}
            pending={pendingCount}
          />
        </CardContent>
      </Card>

      {/* Decision Review Table */}
      <Card>
        <CardHeader>
          <CardTitle>Suggestion Review</CardTitle>
        </CardHeader>
        <CardContent>
          <DecisionTable
            suggestions={suggestions}
            onDecisionsChange={handleDecisionsChange}
          />
        </CardContent>
      </Card>

      {/* Bulk Controls */}
      <Card>
        <CardContent className="pt-6">
          <BulkControls
            workspaceId={workspaceId}
            compilationId={compilationId}
            suggestions={suggestions}
            decisions={decisions}
            onSubmitted={handleSubmitted}
          />
        </CardContent>
      </Card>

      {/* Proceed to Scenario link */}
      {submitted && (
        <div className="flex justify-end">
          <Button asChild>
            <Link
              href={`/w/${workspaceId}/scenarios?compilationId=${compilationId}`}
            >
              Proceed to Scenario
            </Link>
          </Button>
        </div>
      )}
    </div>
  );
}
