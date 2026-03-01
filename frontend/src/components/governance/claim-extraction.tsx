'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  useExtractClaims,
  type ExtractClaimsResponse,
} from '@/lib/api/hooks/useGovernance';

interface ClaimExtractionProps {
  workspaceId: string;
  runId: string;
}

const CLAIM_TYPE_COLORS: Record<string, string> = {
  MODEL: 'bg-blue-100 text-blue-800 hover:bg-blue-100',
  SOURCE_FACT: 'bg-purple-100 text-purple-800 hover:bg-purple-100',
  ASSUMPTION: 'bg-amber-100 text-amber-800 hover:bg-amber-100',
  RECOMMENDATION: 'bg-teal-100 text-teal-800 hover:bg-teal-100',
};

export function ClaimExtraction({ workspaceId, runId }: ClaimExtractionProps) {
  const [draftText, setDraftText] = useState('');
  const [result, setResult] = useState<ExtractClaimsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { mutateAsync, isPending } = useExtractClaims(workspaceId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!draftText.trim()) {
      return;
    }

    try {
      const response = await mutateAsync({
        draft_text: draftText,
        run_id: runId,
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed');
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Claim Extraction</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <p className="text-sm text-muted-foreground mb-2">
              Run: <span className="font-mono">{runId}</span>
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="draft-text">Draft Text</Label>
            <Textarea
              id="draft-text"
              placeholder="Enter the text to extract claims from..."
              value={draftText}
              onChange={(e) => setDraftText(e.target.value)}
              rows={6}
            />
          </div>

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}

          <Button type="submit" disabled={isPending}>
            {isPending ? 'Extracting...' : 'Extract Claims'}
          </Button>
        </form>

        {/* Results */}
        {result && (
          <div className="mt-6 space-y-4">
            <div className="flex items-center gap-4">
              <p className="text-sm font-medium">
                {result.total} claim{result.total !== 1 ? 's' : ''} extracted
              </p>
              {result.needs_evidence_count > 0 && (
                <Badge variant="outline">
                  {result.needs_evidence_count} need{result.needs_evidence_count !== 1 ? '' : 's'} evidence
                </Badge>
              )}
            </div>

            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Text</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.claims.map((claim) => (
                    <TableRow key={claim.claim_id}>
                      <TableCell className="max-w-xs truncate">
                        {claim.text}
                      </TableCell>
                      <TableCell>
                        <Badge
                          className={
                            CLAIM_TYPE_COLORS[claim.claim_type] ??
                            'bg-gray-100 text-gray-800 hover:bg-gray-100'
                          }
                        >
                          {claim.claim_type}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{claim.status}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
