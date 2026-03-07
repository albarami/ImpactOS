'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { QualitativeRiskResponse } from '@/lib/api/hooks/useRuns';

interface QualitativeRisksPanelProps {
  risks: QualitativeRiskResponse[];
}

function tierTone(tier?: string | null): string {
  if (tier === 'TIER0') return 'bg-red-100 text-red-800';
  if (tier === 'TIER1') return 'bg-blue-100 text-blue-800';
  if (tier === 'TIER2') return 'bg-emerald-100 text-emerald-800';
  return 'bg-muted text-muted-foreground';
}

export function QualitativeRisksPanel({ risks }: QualitativeRisksPanelProps) {
  if (risks.length === 0) return null;

  return (
    <div className="space-y-4" data-testid="qualitative-risks-panel">
      <div>
        <h3 className="text-lg font-semibold">Qualitative Risks</h3>
        <p className="text-sm text-muted-foreground">
          NOT MODELLED IN IO FRAMEWORK - analytical judgment only.
        </p>
      </div>
      {risks.map((risk, idx) => (
        <Card key={risk.risk_id ?? idx}>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-base">{risk.label}</CardTitle>
              {risk.disclosure_tier && (
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tierTone(risk.disclosure_tier)}`}>
                  {risk.disclosure_tier === 'TIER0' ? 'TIER0 INTERNAL' : risk.disclosure_tier}
                </span>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-sm">{risk.description}</p>
            {risk.affected_sectors.length > 0 && (
              <div className="text-xs">
                <span className="font-medium text-muted-foreground">Affected sectors: </span>
                <span className="font-mono">{risk.affected_sectors.join(', ')}</span>
              </div>
            )}
            {risk.trigger_conditions.length > 0 && (
              <div>
                <span className="text-xs font-medium text-muted-foreground">Trigger conditions</span>
                <ul className="ml-4 list-disc text-xs">
                  {risk.trigger_conditions.map((condition, index) => (
                    <li key={index}>{condition}</li>
                  ))}
                </ul>
              </div>
            )}
            {risk.expected_direction && (
              <div className="text-xs">
                <span className="font-medium text-muted-foreground">Expected direction: </span>
                <span>{risk.expected_direction}</span>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
