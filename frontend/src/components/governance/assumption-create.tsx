'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  useCreateAssumption,
  type AssumptionType,
} from '@/lib/api/hooks/useGovernance';

interface AssumptionCreateProps {
  workspaceId: string;
  onCreated: (assumptionId: string) => void;
}

const ASSUMPTION_TYPES: AssumptionType[] = [
  'IMPORT_SHARE',
  'PHASING',
  'DEFLATOR',
  'WAGE_PROXY',
  'CAPACITY_CAP',
  'JOBS_COEFF',
];

export function AssumptionCreate({
  workspaceId,
  onCreated,
}: AssumptionCreateProps) {
  const [type, setType] = useState<AssumptionType>('IMPORT_SHARE');
  const [value, setValue] = useState('');
  const [units, setUnits] = useState('');
  const [justification, setJustification] = useState('');
  const [error, setError] = useState<string | null>(null);

  const { mutateAsync, isPending } = useCreateAssumption(workspaceId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const numValue = parseFloat(value);
    if (isNaN(numValue)) {
      setError('Value must be a valid number');
      return;
    }

    try {
      const response = await mutateAsync({
        type,
        value: numValue,
        units,
        justification,
      });
      onCreated(response.assumption_id);
      // Reset form
      setValue('');
      setUnits('');
      setJustification('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create assumption');
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create Assumption</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="assumption-type">Type</Label>
            <select
              id="assumption-type"
              value={type}
              onChange={(e) => setType(e.target.value as AssumptionType)}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {ASSUMPTION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="assumption-value">Value</Label>
            <Input
              id="assumption-value"
              type="number"
              step="any"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="0.35"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="assumption-units">Units</Label>
            <Input
              id="assumption-units"
              type="text"
              value={units}
              onChange={(e) => setUnits(e.target.value)}
              placeholder="ratio, %, SAR, etc."
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="assumption-justification">Justification</Label>
            <Textarea
              id="assumption-justification"
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              placeholder="Explain the basis for this assumption..."
              rows={3}
              required
            />
          </div>

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}

          <Button type="submit" disabled={isPending}>
            {isPending ? 'Creating...' : 'Create Assumption'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
