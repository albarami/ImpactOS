import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

// ── Types ──────────────────────────────────────────────────────────────

export interface SliderItem {
  sector_code: string;
  pct_delta: number;
}

export interface CreateSessionRequest {
  baseline_run_id: string;
  base_shocks: Record<string, number[]>;
  sliders: SliderItem[];
}

export interface WorkshopSessionResponse {
  session_id: string;
  workspace_id: string;
  baseline_run_id: string;
  slider_config: SliderItem[];
  status: 'draft' | 'committed' | 'archived';
  committed_run_id: string | null;
  config_hash: string;
  preview_summary: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface WorkshopListResponse {
  items: WorkshopSessionResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface PreviewResultSet {
  result_id: string;
  metric_type: string;
  values: Record<string, number>;
}

export interface PreviewResponse {
  result_sets: PreviewResultSet[];
  transformed_shocks: Record<string, number[]>;
  ephemeral: boolean;
}

export interface CommitRequest {
  model_version_id: string;
  base_year: number;
  satellite_coefficients: {
    jobs_coeff: number[];
    import_ratio: number[];
    va_ratio: number[];
  };
  deflators?: Record<string, number>;
}

export interface PreviewRequest {
  baseline_run_id: string;
  base_shocks: Record<string, number[]>;
  sliders: SliderItem[];
  model_version_id: string;
  base_year: number;
  satellite_coefficients: {
    jobs_coeff: number[];
    import_ratio: number[];
    va_ratio: number[];
  };
}

// ── Helpers ────────────────────────────────────────────────────────────

const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function workshopFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${baseUrl}${path}`, init);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

// ── Hooks ──────────────────────────────────────────────────────────────

/**
 * Create a workshop session.
 * POST /v1/workspaces/{workspace_id}/workshop/sessions
 */
export function useCreateWorkshopSession(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation<WorkshopSessionResponse, Error, CreateSessionRequest>({
    mutationFn: async (request) => {
      return workshopFetch<WorkshopSessionResponse>(
        `/v1/workspaces/${workspaceId}/workshop/sessions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(request),
        }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workshopSessions', workspaceId] });
    },
  });
}

/**
 * Get a single workshop session.
 * GET /v1/workspaces/{workspace_id}/workshop/sessions/{session_id}
 *
 * Disabled when sessionId is empty/falsy.
 */
export function useWorkshopSession(workspaceId: string, sessionId: string) {
  return useQuery<WorkshopSessionResponse>({
    queryKey: ['workshopSession', workspaceId, sessionId],
    queryFn: async () => {
      return workshopFetch<WorkshopSessionResponse>(
        `/v1/workspaces/${workspaceId}/workshop/sessions/${sessionId}`
      );
    },
    enabled: !!sessionId,
  });
}

/**
 * List workshop sessions (paginated).
 * GET /v1/workspaces/{workspace_id}/workshop/sessions
 */
export function useWorkshopSessions(workspaceId: string, limit = 20, offset = 0) {
  return useQuery<WorkshopListResponse>({
    queryKey: ['workshopSessions', workspaceId, limit, offset],
    queryFn: async () => {
      return workshopFetch<WorkshopListResponse>(
        `/v1/workspaces/${workspaceId}/workshop/sessions?limit=${limit}&offset=${offset}`
      );
    },
  });
}

/**
 * Ephemeral engine preview.
 * POST /v1/workspaces/{workspace_id}/workshop/preview
 */
export function useWorkshopPreview(workspaceId: string) {
  return useMutation<PreviewResponse, Error, PreviewRequest>({
    mutationFn: async (request) => {
      return workshopFetch<PreviewResponse>(
        `/v1/workspaces/${workspaceId}/workshop/preview`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(request),
        }
      );
    },
  });
}

/**
 * Commit a workshop session to a permanent run.
 * POST /v1/workspaces/{workspace_id}/workshop/sessions/{session_id}/commit
 */
export function useCommitWorkshopSession(workspaceId: string, sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation<WorkshopSessionResponse, Error, CommitRequest>({
    mutationFn: async (request) => {
      return workshopFetch<WorkshopSessionResponse>(
        `/v1/workspaces/${workspaceId}/workshop/sessions/${sessionId}/commit`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(request),
        }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workshopSession', workspaceId, sessionId] });
      queryClient.invalidateQueries({ queryKey: ['workshopSessions', workspaceId] });
    },
  });
}

/**
 * Export gate for a committed workshop session.
 * POST /v1/workspaces/{workspace_id}/workshop/sessions/{session_id}/export
 */
export function useExportWorkshopSession(workspaceId: string, sessionId: string) {
  return useMutation<Record<string, unknown>, Error, void>({
    mutationFn: async () => {
      return workshopFetch<Record<string, unknown>>(
        `/v1/workspaces/${workspaceId}/workshop/sessions/${sessionId}/export`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }
      );
    },
  });
}
