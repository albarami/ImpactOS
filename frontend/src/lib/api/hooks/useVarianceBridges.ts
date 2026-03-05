import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

// ── Types ──────────────────────────────────────────────────────────────

export interface BridgeDriverResponse {
  driver_type: string;
  description: string;
  impact: number;
  raw_magnitude: number;
  weight: number;
  source_field?: string | null;
  diff_summary?: string | null;
}

export interface BridgeAnalysisResponse {
  analysis_id: string;
  workspace_id: string;
  run_a_id: string;
  run_b_id: string;
  metric_type: string;
  analysis_version: string;
  start_value: number;
  end_value: number;
  total_variance: number;
  drivers: BridgeDriverResponse[];
  config_hash: string;
  result_checksum: string;
  created_at: string;
}

export interface CreateVarianceBridgeRequest {
  run_a_id: string;
  run_b_id: string;
  metric_type?: string;
}

// ── Hooks ──────────────────────────────────────────────────────────────

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Create a variance bridge analysis.
 * POST /v1/workspaces/{workspace_id}/variance-bridges
 */
export function useCreateVarianceBridge(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation<BridgeAnalysisResponse, Error, CreateVarianceBridgeRequest>({
    mutationFn: async (body: CreateVarianceBridgeRequest) => {
      const resp = await fetch(
        `${BASE_URL}/v1/workspaces/${workspaceId}/variance-bridges`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      );
      if (!resp.ok) throw new Error(`Bridge creation failed: ${resp.status}`);
      return resp.json();
    },
    onSuccess: (data) => {
      queryClient.setQueryData(
        ['variance-bridge', workspaceId, data.analysis_id],
        data
      );
      queryClient.invalidateQueries({
        queryKey: ['variance-bridges', workspaceId],
      });
    },
  });
}

/**
 * Fetch a single variance bridge analysis.
 * GET /v1/workspaces/{workspace_id}/variance-bridges/{analysis_id}
 */
export function useVarianceBridge(workspaceId: string, analysisId: string) {
  return useQuery<BridgeAnalysisResponse>({
    queryKey: ['variance-bridge', workspaceId, analysisId],
    queryFn: async () => {
      const resp = await fetch(
        `${BASE_URL}/v1/workspaces/${workspaceId}/variance-bridges/${analysisId}`
      );
      if (!resp.ok) throw new Error(`Bridge fetch failed: ${resp.status}`);
      return resp.json();
    },
    enabled: !!analysisId,
  });
}

/**
 * List all variance bridge analyses for a workspace.
 * GET /v1/workspaces/{workspace_id}/variance-bridges
 */
export function useVarianceBridges(workspaceId: string) {
  return useQuery<BridgeAnalysisResponse[]>({
    queryKey: ['variance-bridges', workspaceId],
    queryFn: async () => {
      const resp = await fetch(
        `${BASE_URL}/v1/workspaces/${workspaceId}/variance-bridges`
      );
      if (!resp.ok) throw new Error(`Bridge list failed: ${resp.status}`);
      return resp.json();
    },
  });
}
