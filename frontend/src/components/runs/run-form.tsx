'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useCreateRun,
  type CreateRunRequest,
  type SatelliteCoefficients,
} from '@/lib/api/hooks/useRuns';

interface RunFormProps {
  workspaceId: string;
}

const SHOCKS_PLACEHOLDER = `{
  "2025": [100000, 200000, 50000],
  "2026": [120000, 250000, 60000]
}`;

const SATELLITE_PLACEHOLDER = `{
  "jobs_coeff": [0.1, 0.2, 0.15],
  "import_ratio": [0.3, 0.4, 0.35],
  "va_ratio": [0.7, 0.6, 0.65]
}`;

const DEFLATORS_PLACEHOLDER = `{
  "2025": 1.02,
  "2026": 1.04
}`;

export function RunForm({ workspaceId }: RunFormProps) {
  const router = useRouter();
  const createRun = useCreateRun(workspaceId);

  const [modelVersionId, setModelVersionId] = useState('');
  const [baseYear, setBaseYear] = useState(2020);
  const [annualShocksJson, setAnnualShocksJson] = useState('');
  const [satelliteJson, setSatelliteJson] = useState('');
  const [deflatorsJson, setDeflatorsJson] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  function tryParseJson<T>(value: string, label: string): T | null {
    try {
      return JSON.parse(value) as T;
    } catch {
      setValidationError(`Invalid JSON in ${label}`);
      return null;
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setValidationError(null);
    setApiError(null);

    // Parse annual_shocks
    const annualShocks = tryParseJson<Record<string, number[]>>(
      annualShocksJson,
      'Annual Shocks'
    );
    if (!annualShocks) return;

    // Parse satellite_coefficients
    const satellite = tryParseJson<SatelliteCoefficients>(
      satelliteJson,
      'Satellite Coefficients'
    );
    if (!satellite) return;

    // Parse optional deflators
    let deflators: Record<string, number> | undefined;
    if (deflatorsJson.trim()) {
      const parsed = tryParseJson<Record<string, number>>(
        deflatorsJson,
        'Deflators'
      );
      if (!parsed) return;
      deflators = parsed;
    }

    const request: CreateRunRequest = {
      model_version_id: modelVersionId,
      base_year: baseYear,
      annual_shocks: annualShocks,
      satellite_coefficients: satellite,
    };

    if (deflators) {
      request.deflators = deflators;
    }

    try {
      const result = await createRun.mutateAsync(request);
      router.push(`/w/${workspaceId}/runs/${result.run_id}`);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to create run';
      setApiError(message);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Execute Engine Run</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Model Version */}
          <div className="space-y-2">
            <Label htmlFor="model-version">Model Version</Label>
            <Input
              id="model-version"
              type="text"
              value={modelVersionId}
              onChange={(e) => setModelVersionId(e.target.value)}
              placeholder="Enter model version UUID"
            />
          </div>

          {/* Base Year */}
          <div className="space-y-2">
            <Label htmlFor="base-year">Base Year</Label>
            <Input
              id="base-year"
              type="number"
              value={baseYear}
              onChange={(e) => setBaseYear(Number(e.target.value))}
            />
          </div>

          {/* Annual Shocks */}
          <div className="space-y-2">
            <Label htmlFor="annual-shocks">Annual Shocks</Label>
            <Textarea
              id="annual-shocks"
              value={annualShocksJson}
              onChange={(e) => setAnnualShocksJson(e.target.value)}
              placeholder={SHOCKS_PLACEHOLDER}
              rows={6}
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              JSON object mapping year strings to arrays of shock values per
              sector.
            </p>
          </div>

          {/* Satellite Coefficients */}
          <div className="space-y-2">
            <Label htmlFor="satellite-coefficients">
              Satellite Coefficients
            </Label>
            <Textarea
              id="satellite-coefficients"
              value={satelliteJson}
              onChange={(e) => setSatelliteJson(e.target.value)}
              placeholder={SATELLITE_PLACEHOLDER}
              rows={5}
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              JSON object with jobs_coeff, import_ratio, and va_ratio arrays
              (one entry per sector).
            </p>
          </div>

          {/* Deflators (optional) */}
          <div className="space-y-2">
            <Label htmlFor="deflators">Deflators (optional)</Label>
            <Textarea
              id="deflators"
              value={deflatorsJson}
              onChange={(e) => setDeflatorsJson(e.target.value)}
              placeholder={DEFLATORS_PLACEHOLDER}
              rows={4}
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Optional JSON object mapping year strings to deflator values.
            </p>
          </div>

          {/* Validation Error */}
          {validationError && (
            <p className="text-sm text-red-600">{validationError}</p>
          )}

          {/* API Error */}
          {apiError && <p className="text-sm text-red-600">{apiError}</p>}

          <Button type="submit" disabled={createRun.isPending}>
            {createRun.isPending ? 'Running...' : 'Execute Run'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
