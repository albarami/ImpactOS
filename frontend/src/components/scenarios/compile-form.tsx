'use client';

import { useState, useMemo, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  useCompileScenario,
  type ScenarioDecisionPayload,
  type ShockItem,
} from '@/lib/api/hooks/useScenarios';
import {
  useCompilationData,
  type Suggestion,
  type CompileResponse,
} from '@/lib/api/hooks/useCompiler';
import { DEV_USER_ID } from '@/lib/auth';

// ── Types ──────────────────────────────────────────────────────────────

interface ScenarioCompileFormProps {
  workspaceId: string;
  scenarioId: string;
  compilationId?: string;
}

interface PhasingEntry {
  year: string;
  share: number;
}

interface DecisionSummaryRow {
  line_item_id: string;
  sector_code: string;
  confidence: number;
  decision_type: 'APPROVED' | 'EXCLUDED' | 'OVERRIDDEN';
}

// ── Helpers ────────────────────────────────────────────────────────────

/**
 * Maps compiler suggestions + their bulk decisions into scenario compile
 * decision payloads.
 *
 * From F-3A decision data (stored in compilation cache):
 * - All items default to "accept" -> APPROVED
 * - Items with override_sector_code -> OVERRIDDEN
 *
 * CRITICAL: Rejected items MUST be included with decision_type "EXCLUDED"
 * and final_sector_code null. Omitting them causes auto-approval.
 */
function buildDecisions(
  suggestions: Suggestion[],
  decisionOverrides: Record<string, { action: 'accept' | 'reject'; overrideSector?: string }>
): { decisions: ScenarioDecisionPayload[]; summaryRows: DecisionSummaryRow[] } {
  const decisions: ScenarioDecisionPayload[] = [];
  const summaryRows: DecisionSummaryRow[] = [];

  for (const suggestion of suggestions) {
    const override = decisionOverrides[suggestion.line_item_id];
    const action = override?.action ?? 'accept';
    const overrideSector = override?.overrideSector;

    if (action === 'reject') {
      decisions.push({
        line_item_id: suggestion.line_item_id,
        final_sector_code: null,
        decision_type: 'EXCLUDED',
        decided_by: DEV_USER_ID,
        suggested_confidence: suggestion.confidence,
      });
      summaryRows.push({
        line_item_id: suggestion.line_item_id,
        sector_code: suggestion.sector_code,
        confidence: suggestion.confidence,
        decision_type: 'EXCLUDED',
      });
    } else if (overrideSector) {
      decisions.push({
        line_item_id: suggestion.line_item_id,
        final_sector_code: overrideSector,
        decision_type: 'OVERRIDDEN',
        decided_by: DEV_USER_ID,
        suggested_confidence: suggestion.confidence,
      });
      summaryRows.push({
        line_item_id: suggestion.line_item_id,
        sector_code: overrideSector,
        confidence: suggestion.confidence,
        decision_type: 'OVERRIDDEN',
      });
    } else {
      decisions.push({
        line_item_id: suggestion.line_item_id,
        final_sector_code: suggestion.sector_code,
        decision_type: 'APPROVED',
        decided_by: DEV_USER_ID,
        suggested_confidence: suggestion.confidence,
      });
      summaryRows.push({
        line_item_id: suggestion.line_item_id,
        sector_code: suggestion.sector_code,
        confidence: suggestion.confidence,
        decision_type: 'APPROVED',
      });
    }
  }

  return { decisions, summaryRows };
}

function decisionBadgeColor(dt: string): string {
  if (dt === 'APPROVED') return 'bg-green-600';
  if (dt === 'EXCLUDED') return 'bg-red-500';
  return 'bg-amber-500';
}

// ── Component ──────────────────────────────────────────────────────────

export function ScenarioCompileForm({
  workspaceId,
  scenarioId,
  compilationId,
}: ScenarioCompileFormProps) {
  const compileScenario = useCompileScenario(workspaceId, scenarioId);

  // Read cached compilation data from F-3A
  const compilationData: CompileResponse | undefined = useCompilationData(
    compilationId ?? ''
  );

  const [documentId, setDocumentId] = useState('');
  const [phasingEntries, setPhasingEntries] = useState<PhasingEntry[]>([
    { year: '2025', share: 1.0 },
  ]);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [shockItems, setShockItems] = useState<ShockItem[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);

  // Build decisions from compilation data (all defaults to APPROVED)
  const { decisions, summaryRows } = useMemo(() => {
    if (!compilationData?.suggestions) {
      return { decisions: [], summaryRows: [] };
    }
    // In F-3A, users make accept/reject decisions. For now, default all to accepted
    // Future: read per-item decisions from the bulk decisions cache
    return buildDecisions(compilationData.suggestions, {});
  }, [compilationData]);

  function addPhasingEntry() {
    setPhasingEntries((prev) => [...prev, { year: '', share: 0 }]);
  }

  function removePhasingEntry(index: number) {
    setPhasingEntries((prev) => prev.filter((_, i) => i !== index));
  }

  function updatePhasingEntry(
    index: number,
    field: 'year' | 'share',
    value: string
  ) {
    setPhasingEntries((prev) =>
      prev.map((entry, i) =>
        i === index
          ? {
              ...entry,
              [field]: field === 'share' ? parseFloat(value) || 0 : value,
            }
          : entry
      )
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setValidationError(null);
    setApiError(null);

    // Validate phasing sums to 1.0
    const sharesSum = phasingEntries.reduce(
      (sum, entry) => sum + entry.share,
      0
    );
    if (Math.abs(sharesSum - 1.0) > 0.001) {
      setValidationError('Phasing shares must sum to 1.0');
      return;
    }

    // Build phasing record
    const phasing: Record<string, number> = {};
    for (const entry of phasingEntries) {
      if (entry.year) {
        phasing[entry.year] = entry.share;
      }
    }

    try {
      const result = await compileScenario.mutateAsync({
        document_id: documentId || undefined,
        decisions,
        phasing,
        default_domestic_share: 0.65,
      });

      setShockItems(result.shock_items);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to compile scenario';
      setApiError(message);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Compile Scenario</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Decisions Summary */}
            {compilationData?.suggestions &&
            compilationData.suggestions.length > 0 ? (
              <div className="space-y-2">
                <h3 className="text-sm font-medium">Decisions Summary</h3>
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Line Item</TableHead>
                        <TableHead>Sector</TableHead>
                        <TableHead>Confidence</TableHead>
                        <TableHead>Decision</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {summaryRows.map((row) => (
                        <TableRow key={row.line_item_id}>
                          <TableCell className="font-mono text-xs">
                            {row.line_item_id}
                          </TableCell>
                          <TableCell className="font-mono text-sm">
                            {row.sector_code}
                          </TableCell>
                          <TableCell>
                            {Math.round(row.confidence * 100)}%
                          </TableCell>
                          <TableCell>
                            <Badge
                              className={`${decisionBadgeColor(row.decision_type)} text-white`}
                            >
                              {row.decision_type}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No compilation data available. Enter a document ID to compile
                directly.
              </p>
            )}

            {/* Document ID */}
            <div className="space-y-2">
              <Label htmlFor="document-id">Document ID</Label>
              <Input
                id="document-id"
                type="text"
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
                placeholder="Enter document UUID"
              />
            </div>

            {/* Phasing Editor */}
            <div className="space-y-2">
              <h3 className="text-sm font-medium">Phasing</h3>
              <p className="text-xs text-muted-foreground">
                Define year-share entries. Shares must sum to 1.0.
              </p>
              <div className="space-y-2">
                {phasingEntries.map((entry, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      type="text"
                      placeholder="Year"
                      value={entry.year}
                      onChange={(e) =>
                        updatePhasingEntry(index, 'year', e.target.value)
                      }
                      className="w-24"
                    />
                    <Input
                      type="number"
                      placeholder="Share"
                      value={entry.share}
                      onChange={(e) =>
                        updatePhasingEntry(index, 'share', e.target.value)
                      }
                      step={0.01}
                      min={0}
                      max={1}
                      className="w-24"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => removePhasingEntry(index)}
                      aria-label="Remove"
                    >
                      Remove
                    </Button>
                  </div>
                ))}
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addPhasingEntry}
              >
                Add Year
              </Button>
            </div>

            {/* Validation Error */}
            {validationError && (
              <p className="text-sm text-red-600">{validationError}</p>
            )}

            {/* API Error */}
            {apiError && <p className="text-sm text-red-600">{apiError}</p>}

            <Button type="submit" disabled={compileScenario.isPending}>
              {compileScenario.isPending ? 'Compiling...' : 'Compile'}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Shock Items Result Table */}
      {shockItems.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Shock Items</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead>Sector</TableHead>
                    <TableHead>Value</TableHead>
                    <TableHead>Year</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shockItems.map((item, index) => (
                    <TableRow key={index}>
                      <TableCell>{item.shock_type}</TableCell>
                      <TableCell className="font-mono">
                        {item.sector_code}
                      </TableCell>
                      <TableCell>{item.value}</TableCell>
                      <TableCell>{item.year}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
