interface ConfidenceSummaryProps {
  highConfidence: number;
  mediumConfidence: number;
  lowConfidence: number;
  accepted: number;
  rejected: number;
  pending: number;
}

export function ConfidenceSummary({
  highConfidence,
  mediumConfidence,
  lowConfidence,
  accepted,
  rejected,
  pending,
}: ConfidenceSummaryProps) {
  const total = highConfidence + mediumConfidence + lowConfidence;

  const highPct = total > 0 ? (highConfidence / total) * 100 : 0;
  const medPct = total > 0 ? (mediumConfidence / total) * 100 : 0;
  const lowPct = total > 0 ? (lowConfidence / total) * 100 : 0;

  return (
    <div className="space-y-3">
      {/* Stacked horizontal bar */}
      <div
        data-testid="confidence-bar"
        className="flex h-4 w-full overflow-hidden rounded-full bg-gray-200"
      >
        {highPct > 0 && (
          <div
            data-testid="bar-high"
            className="bg-green-600"
            style={{ width: `${highPct}%` }}
          />
        )}
        {medPct > 0 && (
          <div
            data-testid="bar-medium"
            className="bg-amber-500"
            style={{ width: `${medPct}%` }}
          />
        )}
        {lowPct > 0 && (
          <div
            data-testid="bar-low"
            className="bg-red-500"
            style={{ width: `${lowPct}%` }}
          />
        )}
      </div>

      {/* Confidence text */}
      <p className="text-sm text-muted-foreground">
        {highConfidence} high, {mediumConfidence} medium, {lowConfidence} low
        confidence
      </p>

      {/* Decision counts */}
      <p className="text-sm text-muted-foreground">
        {accepted} accepted, {rejected} rejected, {pending} pending
      </p>
    </div>
  );
}
