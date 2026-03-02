'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useApproveAssumption } from '@/lib/api/hooks/useGovernance';
import { DEV_USER_ID } from '@/lib/auth';

interface AssumptionApproveProps {
  workspaceId: string;
  assumptionId: string;
  onApproved: () => void;
}

export function AssumptionApprove({
  workspaceId,
  assumptionId,
  onApproved,
}: AssumptionApproveProps) {
  const [rangeMin, setRangeMin] = useState('');
  const [rangeMax, setRangeMax] = useState('');
  const [error, setError] = useState<string | null>(null);

  const { mutateAsync, isPending } = useApproveAssumption(workspaceId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const min = parseFloat(rangeMin);
    const max = parseFloat(rangeMax);

    if (isNaN(min) || isNaN(max)) {
      setError('Range values must be valid numbers');
      return;
    }

    if (max < min) {
      setError('Range max must be greater than or equal to range min');
      return;
    }

    try {
      await mutateAsync({
        assumption_id: assumptionId,
        range_min: min,
        range_max: max,
        actor: DEV_USER_ID,
      });
      onApproved();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve assumption');
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Approve Assumption</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground mb-4">
          Assumption: <span className="font-mono">{assumptionId}</span>
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="range-min">Range Min</Label>
              <Input
                id="range-min"
                type="number"
                step="any"
                value={rangeMin}
                onChange={(e) => setRangeMin(e.target.value)}
                placeholder="0.3"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="range-max">Range Max</Label>
              <Input
                id="range-max"
                type="number"
                step="any"
                value={rangeMax}
                onChange={(e) => setRangeMax(e.target.value)}
                placeholder="0.4"
                required
              />
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}

          <Button type="submit" disabled={isPending}>
            {isPending ? 'Approving...' : 'Approve'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
