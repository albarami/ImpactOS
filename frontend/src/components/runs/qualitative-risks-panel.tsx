'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface QualitativeRisk {
  risk_id?: string;
  label: string;
  description: string;
  not_modeled?: boolean;
  affected_sectors?: string[];
  trigger_conditions?: string[];
  expected_direction?: string;
}

interface QualitativeRisksPanelProps {
  risks: QualitativeRisk[];
}

/**
 * P6-4: Qualitative Risks Panel — displays qualitative risks
 * from the depth engine, explicitly labeled as "not modeled"
 * per the agent-to-math boundary.
 */
export function QualitativeRisksPanel({ risks }: QualitativeRisksPanelProps) {
  if (risks.length === 0) return null;

  return (
    <div className="space-y-4" data-testid="qualitative-risks-panel">
      <h3 className="text-lg font-semibold">Qualitative Risks</h3>
      <p className="text-sm text-muted-foreground">
        These risks are identified by the depth engine but are{' '}
        <strong>not modeled</strong> in the deterministic engine.
      </p>
      {risks.map((risk, idx) => (
        <Card key={risk.risk_id ?? idx}>
          <CardHeader>
            <CardTitle className="text-base">{risk.label}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-sm">{risk.description}</p>
            {risk.affected_sectors && risk.affected_sectors.length > 0 && (
              <div>
                <span className="text-xs font-medium text-muted-foreground">
                  Affected sectors:{' '}
                </span>
                <span className="text-xs font-mono">
                  {risk.affected_sectors.join(', ')}
                </span>
              </div>
            )}
            {risk.trigger_conditions && risk.trigger_conditions.length > 0 && (
              <div>
                <span className="text-xs font-medium text-muted-foreground">
                  Trigger conditions:
                </span>
                <ul className="list-disc list-inside text-xs ml-2">
                  {risk.trigger_conditions.map((cond, i) => (
                    <li key={i}>{cond}</li>
                  ))}
                </ul>
              </div>
            )}
            {risk.expected_direction && (
              <div>
                <span className="text-xs font-medium text-muted-foreground">
                  Expected direction:{' '}
                </span>
                <span className="text-xs">{risk.expected_direction}</span>
              </div>
            )}
            <div className="mt-1">
              <span className="inline-flex items-center rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-800">
                Not modeled in engine
              </span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
