import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '../client';

// ── Types ──────────────────────────────────────────────────────────────

export interface SatelliteCoefficients {
  jobs_coeff: number[];
  import_ratio: number[];
  va_ratio: number[];
}

export interface CreateRunRequest {
  model_version_id: string;
  annual_shocks: Record<string, number[]>;
  base_year: number;
  satellite_coefficients: SatelliteCoefficients;
  deflators?: Record<string, number>;
}

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
          // eslint-disable-next-line @typescript-eslint/no-explicit-any -- body shape may differ from generated schema
          body: request as any,
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
