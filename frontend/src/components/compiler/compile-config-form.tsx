'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCompile } from '@/lib/api/hooks/useCompiler';

interface CompileConfigFormProps {
  workspaceId: string;
  documentId: string;
}

export function CompileConfigForm({
  workspaceId,
  documentId,
}: CompileConfigFormProps) {
  const router = useRouter();
  const compile = useCompile(workspaceId);

  const [scenarioName, setScenarioName] = useState('');
  const [baseModelVersionId, setBaseModelVersionId] = useState('');
  const [baseYear, setBaseYear] = useState(2020);
  const [startYear, setStartYear] = useState(2025);
  const [endYear, setEndYear] = useState(2030);
  const [validationError, setValidationError] = useState<string | null>(null);

  const isValid = scenarioName.trim().length > 0;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setValidationError(null);

    if (endYear < startYear) {
      setValidationError(
        'End year must be greater than or equal to start year'
      );
      return;
    }

    const result = await compile.mutateAsync({
      scenario_name: scenarioName,
      base_model_version_id: baseModelVersionId,
      base_year: baseYear,
      start_year: startYear,
      end_year: endYear,
      document_id: documentId,
    });

    router.push(`/w/${workspaceId}/compilations/${result.compilation_id}`);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Compile Scenario</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Scenario Name */}
          <div className="space-y-2">
            <Label htmlFor="scenario-name">Scenario Name</Label>
            <Input
              id="scenario-name"
              type="text"
              value={scenarioName}
              onChange={(e) => setScenarioName(e.target.value)}
              placeholder="e.g. NEOM Phase 1 Impact"
              required
            />
          </div>

          {/* Model Version */}
          <div className="space-y-2">
            <Label htmlFor="model-version">Model Version</Label>
            <Input
              id="model-version"
              type="text"
              value={baseModelVersionId}
              onChange={(e) => setBaseModelVersionId(e.target.value)}
              placeholder="UUID"
            />
            <p className="text-xs text-muted-foreground">
              Enter model version UUID
            </p>
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

          {/* Start Year */}
          <div className="space-y-2">
            <Label htmlFor="start-year">Start Year</Label>
            <Input
              id="start-year"
              type="number"
              value={startYear}
              onChange={(e) => setStartYear(Number(e.target.value))}
            />
          </div>

          {/* End Year */}
          <div className="space-y-2">
            <Label htmlFor="end-year">End Year</Label>
            <Input
              id="end-year"
              type="number"
              value={endYear}
              onChange={(e) => setEndYear(Number(e.target.value))}
            />
          </div>

          {/* Document ID (read-only info) */}
          <div className="space-y-2">
            <Label>Document</Label>
            <p className="text-sm font-mono text-muted-foreground">
              {documentId}
            </p>
          </div>

          {/* Validation Error */}
          {validationError && (
            <p className="text-sm text-red-600">{validationError}</p>
          )}

          <Button type="submit" disabled={!isValid || compile.isPending}>
            {compile.isPending ? 'Compiling...' : 'Compile'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
