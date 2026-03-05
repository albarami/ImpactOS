import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type { components } from '../schema';

// ── Schema-derived body types ──────────────────────────────────────────
type RunRequestBody = components['schemas']['RunRequest'];

// ── Types ──────────────────────────────────────────────────────────────

export interface SatelliteCoefficients {
  jobs_coeff: number[];
  import_ratio: number[];
  va_ratio: number[];
}

/** Alias for the schema-inferred run request body. */
export type CreateRunRequest = RunRequestBody;

export interface ResultSet {
  result_id: string;
  metric_type: string;
  values: Record<string, number>;
}

export interface RunSnapshot {
  run_id: string;
  model_version_id: string;
}

export interface RunResponse {
  run_id: string;
  result_sets: ResultSet[];
  snapshot: RunSnapshot;
}

// ── Run listing types (Sprint 24 — I-4) ──────────────────────────────

export interface RunSummary {
  run_id: string;
  model_version_id: string;
  created_at: string;
}

export interface ListRunsResponse {
  runs: RunSummary[];
}

// ── Hooks ──────────────────────────────────────────────────────────────

/**
 * Create a single engine run (SYNCHRONOUS).
 * POST /v1/workspaces/{workspace_id}/engine/runs
 */
export function useCreateRun(workspaceId: string) {
  return useMutation<RunResponse, Error, CreateRunRequest>({
    mutationFn: async (request: CreateRunRequest) => {
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/engine/runs',
        {
          params: { path: { workspace_id: workspaceId } },
          body: request,
        }
      );
      if (error) throw error;
      return data as unknown as RunResponse;
    },
  });
}

/**
 * Get results for a completed run.
 * GET /v1/workspaces/{workspace_id}/engine/runs/{run_id}
 *
 * Disabled when runId is empty/falsy.
 */
export function useRunResults(workspaceId: string, runId: string) {
  return useQuery<RunResponse>({
    queryKey: ['runResults', workspaceId, runId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/v1/workspaces/{workspace_id}/engine/runs/{run_id}',
        {
          params: {
            path: {
              workspace_id: workspaceId,
              run_id: runId,
            },
          },
        }
      );
      if (error) throw error;
      return data as unknown as RunResponse;
    },
    enabled: !!runId,
  });
}

/**
 * List all runs for a workspace (newest first).
 * GET /v1/workspaces/{workspace_id}/engine/runs
 */
export function useWorkspaceRuns(workspaceId: string) {
  return useQuery<ListRunsResponse>({
    queryKey: ['workspaceRuns', workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/v1/workspaces/{workspace_id}/engine/runs' as any,
        {
          params: { path: { workspace_id: workspaceId } },
        }
      );
      if (error) throw error;
      return data as unknown as ListRunsResponse;
    },
    enabled: !!workspaceId,
  });
}
