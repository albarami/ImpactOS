import type { BridgeDriverResponse } from '@/lib/api/hooks/useVarianceBridges';

// ── Helpers ──────────────────────────────────────────────────────────

function formatValue(value: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatImpact(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}`;
}

// ── Props ────────────────────────────────────────────────────────────

interface WaterfallChartProps {
  startValue: number;
  endValue: number;
  totalVariance: number;
  drivers: BridgeDriverResponse[];
}

// ── Component ────────────────────────────────────────────────────────

export function WaterfallChart({
  startValue,
  endValue,
  totalVariance,
  drivers,
}: WaterfallChartProps) {
  if (drivers.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <p className="text-center text-sm text-slate-500">
          No variance detected
        </p>
        <div className="mt-4 flex justify-between text-sm text-slate-600">
          <span aria-label={`Start value: ${formatValue(startValue)}`}>
            Start: {formatValue(startValue)}
          </span>
          <span aria-label={`End value: ${formatValue(endValue)}`}>
            End: {formatValue(endValue)}
          </span>
        </div>
      </div>
    );
  }

  // Calculate the maximum absolute value for scaling bars
  const allValues = [
    startValue,
    endValue,
    ...drivers.map((d) => Math.abs(d.impact)),
  ];
  const maxValue = Math.max(...allValues);

  function barWidth(value: number): string {
    if (maxValue === 0) return '0%';
    return `${Math.min((Math.abs(value) / maxValue) * 100, 100)}%`;
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6">
      <div className="space-y-3">
        {/* Start value bar */}
        <div
          className="flex items-center gap-3"
          aria-label={`Start value: ${formatValue(startValue)}`}
        >
          <span className="w-40 shrink-0 text-right text-sm font-medium text-slate-700">
            Start
          </span>
          <div className="flex-1">
            <div
              className="h-8 rounded bg-slate-400"
              style={{ width: barWidth(startValue) }}
            />
          </div>
          <span className="w-24 shrink-0 text-right font-mono text-sm text-slate-600">
            {formatValue(startValue)}
          </span>
        </div>

        {/* Driver bars */}
        {drivers.map((driver, index) => {
          const isPositive = driver.impact >= 0;
          return (
            <div
              key={`${driver.driver_type}-${index}`}
              className="flex items-center gap-3"
              aria-label={`${driver.driver_type}: ${formatImpact(driver.impact)}`}
              {...(isPositive
                ? { 'data-positive': '' }
                : { 'data-negative': '' })}
            >
              <span className="w-40 shrink-0 text-right text-sm font-medium text-slate-700">
                {driver.driver_type}
              </span>
              <div className="flex-1">
                <div
                  className={`h-8 rounded ${isPositive ? 'bg-green-500' : 'bg-red-500'}`}
                  style={{ width: barWidth(driver.impact) }}
                />
              </div>
              <span
                className={`w-24 shrink-0 text-right font-mono text-sm ${
                  isPositive ? 'text-green-700' : 'text-red-700'
                }`}
              >
                {formatImpact(driver.impact)}
              </span>
            </div>
          );
        })}

        {/* End value bar */}
        <div
          className="flex items-center gap-3"
          aria-label={`End value: ${formatValue(endValue)}`}
        >
          <span className="w-40 shrink-0 text-right text-sm font-medium text-slate-700">
            End
          </span>
          <div className="flex-1">
            <div
              className="h-8 rounded bg-slate-600"
              style={{ width: barWidth(endValue) }}
            />
          </div>
          <span className="w-24 shrink-0 text-right font-mono text-sm text-slate-600">
            {formatValue(endValue)}
          </span>
        </div>
      </div>

      {/* Total variance summary */}
      <div className="mt-4 border-t border-slate-100 pt-3 text-right">
        <span className="text-sm text-slate-500">Total Variance: </span>
        <span
          className={`font-mono text-sm font-semibold ${
            totalVariance >= 0 ? 'text-green-700' : 'text-red-700'
          }`}
        >
          {formatImpact(totalVariance)}
        </span>
      </div>
    </div>
  );
}
