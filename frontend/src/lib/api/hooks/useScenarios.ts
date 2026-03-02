import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type { components } from '../schema';

// ── Schema-derived body types ──────────────────────────────────────────
type ScenarioCompileBody = components['schemas']['src__api__scenarios__CompileRequest'];

// ── Types ──────────────────────────────────────────────────────────────

export interface CreateScenarioRequest {
  name: string;
  base_model_version_id: string;
  base_year: number;
  start_year: number;
  end_year: number;
}

export interface CreateScenarioResponse {
  scenario_spec_id: string;
  version: number;
  name: string;
}

export interface ScenarioDecisionPayload {
  line_item_id: string;
  final_sector_code: string | null;
  decision_type: 'APPROVED' | 'EXCLUDED' | 'OVERRIDDEN';
  decided_by: string;
  suggested_confidence?: number;
}

export interface ShockItem {
  shock_type: string;
  sector_code: string;
  value: number;
  year: string;
}

/** Alias for the schema-inferred scenario compile request body. */
export type ScenarioCompileRequest = ScenarioCompileBody;

export interface ScenarioCompileResponse {
  scenario_spec_id: string;
  version: number;
  shock_items: ShockItem[];
  data_quality_summary?: Record<string, unknown>;
}

export interface VersionEntry {
  version: number;
  updated_at: string;
}

export interface VersionsResponse {
  versions: VersionEntry[];
}

// ── Hooks ──────────────────────────────────────────────────────────────

/**
 * Create a new scenario.
 * POST /v1/workspaces/{workspace_id}/scenarios
 */
export function useCreateScenario(workspaceId: string) {
  return useMutation<CreateScenarioResponse, Error, CreateScenarioRequest>({
    mutationFn: async (request: CreateScenarioRequest) => {
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/scenarios',
        {
          params: { path: { workspace_id: workspaceId } },
          body: request,
        }
      );
      if (error) throw error;
      return data as unknown as CreateScenarioResponse;
    },
  });
}

/**
 * Compile a scenario — maps decisions + phasing into shock items.
 * POST /v1/workspaces/{workspace_id}/scenarios/{scenario_id}/compile
 *
 * CRITICAL: All items must be included in decisions — accepted AND rejected.
 * Rejected items get decision_type: "EXCLUDED", final_sector_code: null.
 * Omitting rejected items causes auto-approval by backend.
 */
export function useCompileScenario(
  workspaceId: string,
  scenarioId: string
) {
  return useMutation<ScenarioCompileResponse, Error, ScenarioCompileRequest>({
    mutationFn: async (request: ScenarioCompileRequest) => {
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/compile',
        {
          params: {
            path: {
              workspace_id: workspaceId,
              scenario_id: scenarioId,
            },
          },
          body: request,
        }
      );
      if (error) throw error;
      return data as unknown as ScenarioCompileResponse;
    },
  });
}

/**
 * Get all versions of a scenario.
 * GET /v1/workspaces/{workspace_id}/scenarios/{scenario_id}/versions
 */
export function useScenarioVersions(
  workspaceId: string,
  scenarioId: string
) {
  return useQuery<VersionsResponse>({
    queryKey: ['scenarioVersions', workspaceId, scenarioId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/versions',
        {
          params: {
            path: {
              workspace_id: workspaceId,
              scenario_id: scenarioId,
            },
          },
        }
      );
      if (error) throw error;
      return data as unknown as VersionsResponse;
    },
  });
}
