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
  sector_breakdowns?: Record<string, Record<string, number>>; // P6-4
}

export interface RunSnapshot {
  run_id: string;
  model_version_id: string;
  model_denomination?: string; // P6-3: e.g. "SAR_MILLIONS", "SAR_THOUSANDS"
}

// P6-4: Depth engine data from Al-Muhasabi pipeline
export interface DepthEngineData {
  plan_id?: string;
  suite_id?: string;
  suite_rationale?: string;
  suite_runs: Array<{
    name: string;
    mode?: string;
    is_contrarian?: boolean;
    sensitivities?: Array<string | Record<string, unknown>>;
    executable_levers?: Record<string, unknown>[];
  }>;
  qualitative_risks: Array<{
    risk_id?: string;
    label: string;
    description: string;
    not_modeled?: boolean;
    affected_sectors?: string[];
    trigger_conditions?: string[];
    expected_direction?: string;
  }>;
  sensitivity_runs: Array<{
    name: string;
    multiplier: number;
    total_output?: number;
    employment?: number;
  }>;
  trace_steps: Array<{
    step: number;
    step_name: string;
    provider?: string;
    model?: string;
    generation_mode?: string;
    duration_ms?: number;
    input_tokens?: number;
    output_tokens?: number;
  }>;
}

export interface RunResponse {
  run_id: string;
  result_sets: ResultSet[];
  snapshot: RunSnapshot;
  depth_engine?: DepthEngineData; // P6-4: present when linked depth plan exists
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
