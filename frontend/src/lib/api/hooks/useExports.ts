import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';

// ── Types ──────────────────────────────────────────────────────────────

export type ExportMode = 'SANDBOX' | 'GOVERNED';

export type ExportFormat = 'excel' | 'pptx';

export type ExportStatus =
  | 'COMPLETED'
  | 'BLOCKED'
  | 'FAILED'
  | 'PENDING'
  | 'GENERATING';

export interface CreateExportRequest {
  run_id: string;
  mode: ExportMode;
  export_formats: ExportFormat[];
  pack_data: Record<string, unknown>;
}

export interface CreateExportResponse {
  export_id: string;
  status: string;
  checksums: Record<string, string>;
  blocking_reasons: string[];
}

export interface ExportStatusResponse {
  export_id: string;
  run_id: string;
  mode: string;
  status: ExportStatus;
  checksums: Record<string, string>;
}

// ── Hooks ──────────────────────────────────────────────────────────────

/**
 * Create a new export.
 * POST /v1/workspaces/{workspace_id}/exports
 */
export function useCreateExport(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation<CreateExportResponse, Error, CreateExportRequest>({
    mutationFn: async (request: CreateExportRequest) => {
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/exports',
        {
          params: { path: { workspace_id: workspaceId } },
          // eslint-disable-next-line @typescript-eslint/no-explicit-any -- body shape may differ from generated schema
          body: request as any,
        }
      );
      if (error) throw error;
      return data as unknown as CreateExportResponse;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['export', data.export_id], data);
    },
  });
}

/**
 * Get export status by export_id.
 * GET /v1/workspaces/{workspace_id}/exports/{export_id}
 *
 * Polls every 3s when status is PENDING or GENERATING.
 * Disabled when exportId is empty/falsy.
 */
export function useExportStatus(workspaceId: string, exportId: string) {
  return useQuery<ExportStatusResponse>({
    queryKey: ['exportStatus', workspaceId, exportId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/v1/workspaces/{workspace_id}/exports/{export_id}',
        {
          params: {
            path: {
              workspace_id: workspaceId,
              export_id: exportId,
            },
          },
        }
      );
      if (error) throw error;
      return data as unknown as ExportStatusResponse;
    },
    enabled: !!exportId,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === 'PENDING' || s === 'GENERATING' ? 3000 : false;
    },
  });
}

/**
 * Read cached export data from TanStack Query cache.
 * Returns undefined if the cache is cold (e.g., after page refresh).
 */
export function useExportData(exportId: string) {
  const queryClient = useQueryClient();
  return queryClient.getQueryData<CreateExportResponse>([
    'export',
    exportId,
  ]);
}
