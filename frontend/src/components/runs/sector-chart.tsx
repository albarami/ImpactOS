'use client';

import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

interface SectorChartProps {
  data: Record<string, number>;
}

interface ChartEntry {
  sector: string;
  value: number;
}

export function SectorChart({ data }: SectorChartProps) {
  const chartData = useMemo<ChartEntry[]>(() => {
    return Object.entries(data)
      .map(([sector, value]) => ({ sector, value }))
      .sort((a, b) => b.value - a.value);
  }, [data]);

  if (chartData.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No sector data available
      </p>
    );
  }

  const chartHeight = Math.max(300, chartData.length * 40);

  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart
        data={chartData}
        layout="vertical"
        margin={{ top: 5, right: 30, left: 60, bottom: 5 }}
      >
        <XAxis type="number" />
        <YAxis dataKey="sector" type="category" width={80} />
        <Tooltip
          formatter={(value) => {
            const rawValue = Array.isArray(value) ? value[0] : value;
            const numericValue =
              typeof rawValue === 'number' ? rawValue : Number(rawValue ?? 0);
            return [numericValue.toLocaleString('en-US'), 'Value'] as const;
          }}
        />
        <Bar dataKey="value" fill="#334155" />
      </BarChart>
    </ResponsiveContainer>
  );
}
