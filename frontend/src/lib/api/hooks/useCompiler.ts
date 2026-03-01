import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { components } from '../schema';

// ── Schema-derived body types ──────────────────────────────────────────
type CompileBody = components['schemas']['src__api__compiler__CompileRequest'];
type BulkDecisionBody = components['schemas']['BulkDecisionRequest'];

// ── Types ──────────────────────────────────────────────────────────────

export interface Suggestion {
  line_item_id: string;
  sector_code: string;
  confidence: number;
  explanation: string;
}

/** Alias for the schema-inferred compile request body. */
export type CompileRequest = CompileBody;

export interface CompileResponse {
  compilation_id: string;
  suggestions: Suggestion[];
  high_confidence: number;
  medium_confidence: number;
  low_confidence: number;
}

export interface CompilationStatusResponse {
  compilation_id: string;
  total_suggestions: number;
  high_confidence: number;
  medium_confidence: number;
  low_confidence: number;
  assumption_drafts: number;
}

export interface DecisionItem {
  line_item_id: string;
  action: 'accept' | 'reject';
  override_sector_code?: string;
  note?: string;
}

/** Alias for the schema-inferred bulk decision request body. */
export type BulkDecisionsRequest = BulkDecisionBody;

export interface BulkDecisionsResponse {
  accepted: number;
  rejected: number;
  total: number;
}

export interface DecisionEntry {
  action: 'accept' | 'reject' | 'override' | 'pending';
  overrideSector?: string;
}

export type DecisionMap = Record<string, DecisionEntry>;

// ── Hooks ──────────────────────────────────────────────────────────────

/**
 * Trigger AI-assisted compilation.
 * On success, caches the full response by compilation_id so the
 * compilation review page can read suggestions without re-fetching.
 */
export function useCompile(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation<CompileResponse, Error, CompileRequest>({
    mutationFn: async (request: CompileRequest) => {
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/compiler/compile',
        {
          params: { path: { workspace_id: workspaceId } },
          body: request,
        }
      );
      if (error) throw error;
      return data as unknown as CompileResponse;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(
        ['compilation', data.compilation_id],
        data
      );
    },
  });
}

/**
 * Get compilation status (counts only, NOT full suggestions).
 */
export function useCompilationStatus(
  workspaceId: string,
  compilationId: string
) {
  return useQuery<CompilationStatusResponse>({
    queryKey: ['compilationStatus', workspaceId, compilationId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/v1/workspaces/{workspace_id}/compiler/{compilation_id}/status',
        {
          params: {
            path: {
              workspace_id: workspaceId,
              compilation_id: compilationId,
            },
          },
        }
      );
      if (error) throw error;
      return data as unknown as CompilationStatusResponse;
    },
  });
}

/**
 * Bulk accept/reject decisions for a compilation.
 */
export function useBulkDecisions(
  workspaceId: string,
  compilationId: string
) {
  return useMutation<BulkDecisionsResponse, Error, BulkDecisionsRequest>({
    mutationFn: async (request: BulkDecisionsRequest) => {
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions',
        {
          params: {
            path: {
              workspace_id: workspaceId,
              compilation_id: compilationId,
            },
          },
          body: request,
        }
      );
      if (error) throw error;
      return data as unknown as BulkDecisionsResponse;
    },
  });
}

/**
 * Read cached compilation data from TanStack Query cache.
 * Returns undefined if the cache is cold (e.g., after page refresh).
 */
export function useCompilationData(compilationId: string) {
  const queryClient = useQueryClient();
  return queryClient.getQueryData<CompileResponse>([
    'compilation',
    compilationId,
  ]);
}

/**
 * Cache user decisions alongside compilation data.
 * Called when user submits decisions on the compilation review page.
 */
export function useSetCompilationDecisions() {
  const queryClient = useQueryClient();
  return (compilationId: string, decisions: DecisionMap) => {
    queryClient.setQueryData(['compilationDecisions', compilationId], decisions);
  };
}

/**
 * Read cached decisions for a compilation.
 * Returns undefined if cache is cold.
 */
export function useCompilationDecisions(compilationId: string) {
  const queryClient = useQueryClient();
  return queryClient.getQueryData<DecisionMap>([
    'compilationDecisions',
    compilationId,
  ]);
}
