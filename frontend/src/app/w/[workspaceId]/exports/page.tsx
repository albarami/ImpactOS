'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export default function ExportsPage() {
  const params = useParams<{ workspaceId: string }>();
  const router = useRouter();
  const workspaceId = params.workspaceId;

  const [runId, setRunId] = useState('');

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!runId.trim()) return;
    router.push(`/w/${workspaceId}/exports/new?runId=${encodeURIComponent(runId.trim())}`);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Exports</h1>
        <p className="mt-2 text-slate-500">
          Create a Decision Pack export from a completed engine run.
        </p>
      </div>

      {/* Compare Runs CTA */}
      <Card>
        <CardHeader>
          <CardTitle>Variance Bridge Analysis</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-slate-500">
            Compare two engine runs side-by-side to understand what drove
            differences in output metrics.
          </p>
          <Link href={`/w/${workspaceId}/exports/compare`}>
            <Button variant="outline">Compare Runs</Button>
          </Link>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Create New Export</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex items-end gap-4">
            <div className="flex-1 space-y-2">
              <Label htmlFor="export-run-id">Run ID</Label>
              <Input
                id="export-run-id"
                type="text"
                value={runId}
                onChange={(e) => setRunId(e.target.value)}
                placeholder="Enter the run ID to export"
              />
            </div>
            <Button type="submit" disabled={!runId.trim()}>
              Continue
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
