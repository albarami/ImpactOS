'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import { SectorSliders } from '@/components/workshop/sector-sliders';
import { PreviewPanel } from '@/components/workshop/preview-panel';
import { SessionControls } from '@/components/workshop/session-controls';
import {
  useCreateWorkshopSession,
  useWorkshopPreview,
  useCommitWorkshopSession,
  useExportWorkshopSession,
  type SliderItem,
  type PreviewResultSet,
} from '@/lib/api/hooks/useWorkshop';

const DEBOUNCE_MS = 500;

/** Placeholder sector codes — in production these come from the model version. */
const DEFAULT_SECTORS = ['S01', 'S02', 'S03', 'S04', 'S05'];

export default function WorkshopPage() {
  const params = useParams<{ workspaceId: string }>();
  const workspaceId = params.workspaceId;

  // ── Session state ──────────────────────────────────────────────────
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string>('draft');
  const [sliders, setSliders] = useState<SliderItem[]>([]);
  const [previewResults, setPreviewResults] = useState<PreviewResultSet[]>([]);
  const [previewError, setPreviewError] = useState<string | undefined>();

  // ── Hooks ──────────────────────────────────────────────────────────
  const createSession = useCreateWorkshopSession(workspaceId);
  const preview = useWorkshopPreview(workspaceId);
  const commitSession = useCommitWorkshopSession(
    workspaceId,
    sessionId ?? ''
  );
  const exportSession = useExportWorkshopSession(
    workspaceId,
    sessionId ?? ''
  );

  // ── Auto-create session on mount ──────────────────────────────────
  useEffect(() => {
    if (!sessionId && !createSession.isPending) {
      createSession.mutate(
        {
          baseline_run_id: '',
          base_shocks: {},
          sliders: [],
        },
        {
          onSuccess: (data) => {
            setSessionId(data.session_id);
            setSessionStatus(data.status);
          },
        }
      );
    }
    // Run only on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Debounced preview ─────────────────────────────────────────────
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const requestPreview = useCallback(
    (updatedSliders: SliderItem[]) => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }

      debounceRef.current = setTimeout(() => {
        setPreviewError(undefined);
        preview.mutate(
          {
            baseline_run_id: '',
            base_shocks: {},
            sliders: updatedSliders,
            model_version_id: '',
            base_year: 2020,
            satellite_coefficients: {
              jobs_coeff: [],
              import_ratio: [],
              va_ratio: [],
            },
          },
          {
            onSuccess: (data) => {
              setPreviewResults(data.result_sets);
            },
            onError: (err) => {
              setPreviewError(err.message);
            },
          }
        );
      }, DEBOUNCE_MS);
    },
    [preview]
  );

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  // ── Handlers ──────────────────────────────────────────────────────
  const handleSlidersChange = useCallback(
    (updated: SliderItem[]) => {
      setSliders(updated);
      requestPreview(updated);
    },
    [requestPreview]
  );

  const handleCommit = useCallback(() => {
    if (!sessionId) return;
    commitSession.mutate(
      {
        model_version_id: '',
        base_year: 2020,
        satellite_coefficients: {
          jobs_coeff: [],
          import_ratio: [],
          va_ratio: [],
        },
      },
      {
        onSuccess: (data) => {
          setSessionStatus(data.status);
        },
      }
    );
  }, [sessionId, commitSession]);

  const handleExport = useCallback(() => {
    if (!sessionId) return;
    exportSession.mutate();
  }, [sessionId, exportSession]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">
          Live Workshop
        </h1>
        <p className="mt-2 text-slate-500">
          Adjust sector sliders to preview impact scenarios in real time.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectorSliders
          sectorCodes={DEFAULT_SECTORS}
          sliders={sliders}
          onChange={handleSlidersChange}
          disabled={sessionStatus !== 'draft'}
        />

        <PreviewPanel
          resultSets={previewResults}
          isLoading={preview.isPending}
          error={previewError}
        />
      </div>

      <SessionControls
        status={sessionStatus}
        onCommit={handleCommit}
        onExport={handleExport}
        isCommitting={commitSession.isPending}
      />
    </div>
  );
}
