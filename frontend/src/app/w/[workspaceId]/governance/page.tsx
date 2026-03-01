'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';

export default function GovernancePage() {
  const params = useParams<{ workspaceId: string }>();
  const router = useRouter();
  const [runId, setRunId] = useState('');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (runId.trim()) {
      router.push(`/w/${params.workspaceId}/governance/${runId.trim()}`);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Governance</h1>
        <p className="mt-2 text-slate-500">
          Select a run to view governance status, claims, and assumptions.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Select a Run</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex items-end gap-4">
            <div className="flex-1 space-y-2">
              <Label htmlFor="run-id-input">Run ID</Label>
              <Input
                id="run-id-input"
                type="text"
                value={runId}
                onChange={(e) => setRunId(e.target.value)}
                placeholder="Enter a run ID..."
                required
              />
            </div>
            <Button type="submit">View Governance</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
