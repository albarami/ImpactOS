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
  confidence_class?: string;
  sector_breakdowns?: Record<string, Record<string, number>>;
  year?: number | null;
  series_kind?: string | null;
  baseline_run_id?: string | null;
}

export interface RunSnapshot {
  run_id: string;
  model_version_id: string;
  model_denomination?: string;
}

export interface WorkforceSector {
  sector_code: string;
  total_jobs: number;
  saudi_ready_jobs: number;
  saudi_trainable_jobs: number;
  expat_reliant_jobs: number;
}

export interface WorkforceResponse {
  total_jobs: number;
  total_saudi_ready: number;
  total_saudi_trainable: number;
  total_expat_reliant: number;
  has_saudization_split: boolean;
  per_sector: WorkforceSector[];
}

export interface SuiteRunResponse {
  scenario_spec_id: string;
  scenario_spec_version: number;
  run_id: string;
  direction_id: string;
  name: string;
  mode: string;
  is_contrarian: boolean;
  multiplier: number;
  headline_output?: number | null;
  employment?: number | null;
  muhasaba_status: string;
  sensitivities: Array<string | Record<string, unknown>>;
}

export interface QualitativeRiskResponse {
  risk_id?: string | null;
  label: string;
  description: string;
  disclosure_tier?: string | null;
  not_modeled: boolean;
  affected_sectors: string[];
  trigger_conditions: string[];
  expected_direction?: string | null;
}

export interface DepthTraceStepResponse {
  step: number;
  step_name: string;
  provider?: string | null;
  model?: string | null;
  generation_mode?: string | null;
  duration_ms?: number | null;
  input_tokens: number;
  output_tokens: number;
  details: Record<string, unknown>;
}

export interface DepthEngineResponse {
  plan_id: string;
  suite_id?: string | null;
  batch_id?: string | null;
  suite_rationale?: string | null;
  run_ids: string[];
  suite_runs: SuiteRunResponse[];
  sensitivity_runs: SuiteRunResponse[];
  qualitative_risks: QualitativeRiskResponse[];
  trace_steps: DepthTraceStepResponse[];
}

export interface RunResponse {
  run_id: string;
  result_sets: ResultSet[];
  snapshot: RunSnapshot;
  workforce?: WorkforceResponse | null;
  depth_engine?: DepthEngineResponse | null;
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
