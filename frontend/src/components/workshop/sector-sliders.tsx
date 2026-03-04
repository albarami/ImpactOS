'use client';

import { useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import type { SliderItem } from '@/lib/api/hooks/useWorkshop';

interface SectorSlidersProps {
  sectorCodes: string[];
  sliders: SliderItem[];
  onChange: (sliders: SliderItem[]) => void;
  disabled?: boolean;
}

export function SectorSliders({
  sectorCodes,
  sliders,
  onChange,
  disabled = false,
}: SectorSlidersProps) {
  const getValue = useCallback(
    (code: string): number => {
      const item = sliders.find((s) => s.sector_code === code);
      return item?.pct_delta ?? 0;
    },
    [sliders]
  );

  const handleChange = useCallback(
    (code: string, value: number) => {
      const existing = sliders.find((s) => s.sector_code === code);
      let updated: SliderItem[];
      if (existing) {
        updated = sliders.map((s) =>
          s.sector_code === code ? { ...s, pct_delta: value } : s
        );
      } else {
        updated = [...sliders, { sector_code: code, pct_delta: value }];
      }
      onChange(updated);
    },
    [sliders, onChange]
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sector Adjustments</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {sectorCodes.map((code) => {
          const value = getValue(code);
          return (
            <div key={code} className="space-y-1">
              <div className="flex items-center justify-between">
                <Label htmlFor={`slider-${code}`}>{code}</Label>
                <span className="text-sm text-muted-foreground">
                  {value > 0 ? '+' : ''}
                  {value}%
                </span>
              </div>
              <input
                id={`slider-${code}`}
                type="range"
                min={-100}
                max={100}
                step={1}
                value={value}
                disabled={disabled}
                onChange={(e) => handleChange(code, Number(e.target.value))}
                className="w-full"
                aria-label={`${code} adjustment`}
              />
            </div>
          );
        })}
        {sectorCodes.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No sectors available. Select a baseline run to configure sliders.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
