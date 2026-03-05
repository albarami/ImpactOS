import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';

// ── Props ────────────────────────────────────────────────────────────

interface DriverCardProps {
  driverType: string;
  description: string;
  impact: number;
  weight: number;
  totalVariance?: number;
  sourceField?: string | null;
  diffSummary?: string | null;
}

// ── Helpers ──────────────────────────────────────────────────────────

function formatImpact(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}`;
}

// ── Component ────────────────────────────────────────────────────────

export function DriverCard({
  driverType,
  description,
  impact,
  weight,
  totalVariance,
  sourceField,
  diffSummary,
}: DriverCardProps) {
  const isPositive = impact >= 0;
  const percentOfTotal =
    totalVariance && totalVariance !== 0
      ? ((Math.abs(impact) / Math.abs(totalVariance)) * 100).toFixed(1)
      : null;

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          {/* Left: type badge + description */}
          <div className="space-y-2">
            <Badge variant="secondary">{driverType}</Badge>
            <p className="text-sm text-slate-600">{description}</p>

            {/* Optional metadata */}
            {sourceField && (
              <p className="text-xs text-slate-400">
                Source: <span className="font-mono">{sourceField}</span>
              </p>
            )}
            {diffSummary && (
              <p
                className="text-xs text-slate-500"
                data-testid="diff-summary"
              >
                {diffSummary}
              </p>
            )}
          </div>

          {/* Right: impact value + weight */}
          <div className="shrink-0 text-right">
            <p
              className={`font-mono text-lg font-semibold ${
                isPositive ? 'text-green-700' : 'text-red-700'
              }`}
            >
              {formatImpact(impact)}
            </p>
            <p className="text-xs text-slate-400">
              Weight: {(weight * 100).toFixed(1)}%
            </p>
            {percentOfTotal && (
              <p className="text-xs text-slate-500">
                {percentOfTotal}% of total
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
