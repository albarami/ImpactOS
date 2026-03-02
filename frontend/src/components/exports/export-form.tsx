'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useCreateExport,
  type ExportMode,
  type ExportFormat,
} from '@/lib/api/hooks/useExports';

interface ExportFormProps {
  workspaceId: string;
  runId: string;
}

const PACK_DATA_PLACEHOLDER = `{
  "scenario_name": "...",
  "base_year": 2025,
  "currency": "SAR"
}`;

export function ExportForm({ workspaceId, runId }: ExportFormProps) {
  const router = useRouter();
  const createExport = useCreateExport(workspaceId);

  const [mode, setMode] = useState<ExportMode>('SANDBOX');
  const [formats, setFormats] = useState<Record<ExportFormat, boolean>>({
    excel: false,
    pptx: false,
  });
  const [packDataJson, setPackDataJson] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const selectedFormats = (Object.keys(formats) as ExportFormat[]).filter(
    (f) => formats[f]
  );
  const hasFormats = selectedFormats.length > 0;

  function toggleFormat(format: ExportFormat) {
    setFormats((prev) => ({ ...prev, [format]: !prev[format] }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setValidationError(null);
    setApiError(null);

    // Parse pack_data — empty string defaults to {}
    let packData: Record<string, unknown> = {};
    if (packDataJson.trim()) {
      try {
        packData = JSON.parse(packDataJson) as Record<string, unknown>;
      } catch {
        setValidationError('Invalid JSON in Pack Data');
        return;
      }
    }

    try {
      const result = await createExport.mutateAsync({
        run_id: runId,
        mode,
        export_formats: selectedFormats,
        pack_data: packData,
      });
      router.push(`/w/${workspaceId}/exports/${result.export_id}`);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to create export';
      setApiError(message);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create Export</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Run ID (read-only) */}
          <div className="space-y-2">
            <Label>Run ID</Label>
            <p className="font-mono text-sm text-slate-700">{runId}</p>
          </div>

          {/* Mode */}
          <div className="space-y-2">
            <Label htmlFor="export-mode">Mode</Label>
            <select
              id="export-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as ExportMode)}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="SANDBOX">SANDBOX</option>
              <option value="GOVERNED">GOVERNED</option>
            </select>
          </div>

          {/* Export Formats */}
          <fieldset className="space-y-2">
            <Label asChild>
              <legend>Export Formats</legend>
            </Label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={formats.excel}
                  onChange={() => toggleFormat('excel')}
                />
                excel
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={formats.pptx}
                  onChange={() => toggleFormat('pptx')}
                />
                pptx
              </label>
            </div>
          </fieldset>

          {/* Pack Data */}
          <div className="space-y-2">
            <Label htmlFor="pack-data">Pack Data</Label>
            <Textarea
              id="pack-data"
              value={packDataJson}
              onChange={(e) => setPackDataJson(e.target.value)}
              placeholder={PACK_DATA_PLACEHOLDER}
              rows={6}
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Optional JSON object with scenario metadata.
            </p>
          </div>

          {/* Validation Error */}
          {validationError && (
            <p className="text-sm text-red-600">{validationError}</p>
          )}

          {/* API Error */}
          {apiError && <p className="text-sm text-red-600">{apiError}</p>}

          <Button type="submit" disabled={!hasFormats || createExport.isPending}>
            {createExport.isPending ? 'Creating...' : 'Create Export'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
