import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type { components } from '../schema';

// ── Schema-derived body types ──────────────────────────────────────────
type ExtractClaimsBody = components['schemas']['ExtractClaimsRequest'];
type NffCheckBody = components['schemas']['NFFCheckRequest'];
type CreateAssumptionBody = components['schemas']['CreateAssumptionRequest'];
type ApproveAssumptionBody = components['schemas']['ApproveAssumptionRequest'];

// ── Types ──────────────────────────────────────────────────────────────

export interface GovernanceStatusResponse {
  run_id: string;
  claims_total: number;
  claims_resolved: number;
  claims_unresolved: number;
  assumptions_total: number;
  assumptions_approved: number;
  nff_passed: boolean;
}

export interface BlockingReason {
  claim_id: string;
  current_status: string;
  reason: string;
}

export interface BlockingReasonsResponse {
  run_id: string;
  blocking_reasons: BlockingReason[];
}

/** Alias for the schema-inferred extract claims request body. */
export type ExtractClaimsRequest = ExtractClaimsBody;

export interface ExtractedClaim {
  claim_id: string;
  text: string;
  claim_type: string;
  status: string;
}

export interface ExtractClaimsResponse {
  claims: ExtractedClaim[];
  total: number;
  needs_evidence_count: number;
}

/** Alias for the schema-inferred NFF check request body. */
export type NffCheckRequest = NffCheckBody;

export interface NffCheckResponse {
  passed: boolean;
  total_claims: number;
  blocking_reasons: BlockingReason[];
}

export type AssumptionType =
  | 'IMPORT_SHARE'
  | 'PHASING'
  | 'DEFLATOR'
  | 'WAGE_PROXY'
  | 'CAPACITY_CAP'
  | 'JOBS_COEFF';

/** Alias for the schema-inferred create assumption request body. */
export type CreateAssumptionRequest = CreateAssumptionBody;

export interface CreateAssumptionResponse {
  assumption_id: string;
  status: string;
}

/**
 * Mutation variable for approving an assumption.
 * Includes assumption_id for path params; the rest becomes the body.
 */
export interface ApproveAssumptionInput {
  assumption_id: string;
  range_min: number;
  range_max: number;
  actor: string;
}

/** Re-export for backwards compatibility. */
export type ApproveAssumptionRequest = ApproveAssumptionInput;

export interface ApproveAssumptionResponse {
  assumption_id: string;
  status: string;
  range_min: number;
  range_max: number;
}

// ── Hooks ──────────────────────────────────────────────────────────────

/**
 * Fetch governance status for a run.
 * GET /v1/workspaces/{workspace_id}/governance/status/{run_id}
 */
export function useGovernanceStatus(workspaceId: string, runId: string) {
  return useQuery<GovernanceStatusResponse>({
    queryKey: ['governanceStatus', workspaceId, runId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/v1/workspaces/{workspace_id}/governance/status/{run_id}',
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
      return data as unknown as GovernanceStatusResponse;
    },
    enabled: !!runId,
  });
}

/**
 * Fetch blocking reasons for a run.
 * GET /v1/workspaces/{workspace_id}/governance/blocking-reasons/{run_id}
 */
export function useBlockingReasons(workspaceId: string, runId: string) {
  return useQuery<BlockingReasonsResponse>({
    queryKey: ['blockingReasons', workspaceId, runId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/v1/workspaces/{workspace_id}/governance/blocking-reasons/{run_id}',
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
      return data as unknown as BlockingReasonsResponse;
    },
    enabled: !!runId,
  });
}

/**
 * Extract claims from draft text.
 * POST /v1/workspaces/{workspace_id}/governance/claims/extract
 */
export function useExtractClaims(workspaceId: string) {
  return useMutation<ExtractClaimsResponse, Error, ExtractClaimsRequest>({
    mutationFn: async (request: ExtractClaimsRequest) => {
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/governance/claims/extract',
        {
          params: { path: { workspace_id: workspaceId } },
          body: request,
        }
      );
      if (error) throw error;
      return data as unknown as ExtractClaimsResponse;
    },
  });
}

/**
 * Run NFF gate check on a set of claims.
 * POST /v1/workspaces/{workspace_id}/governance/nff/check
 */
export function useNffCheck(workspaceId: string) {
  return useMutation<NffCheckResponse, Error, NffCheckRequest>({
    mutationFn: async (request: NffCheckRequest) => {
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/governance/nff/check',
        {
          params: { path: { workspace_id: workspaceId } },
          body: request,
        }
      );
      if (error) throw error;
      return data as unknown as NffCheckResponse;
    },
  });
}

/**
 * Create a new assumption.
 * POST /v1/workspaces/{workspace_id}/governance/assumptions
 */
export function useCreateAssumption(workspaceId: string) {
  return useMutation<CreateAssumptionResponse, Error, CreateAssumptionRequest>({
    mutationFn: async (request: CreateAssumptionRequest) => {
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/governance/assumptions',
        {
          params: { path: { workspace_id: workspaceId } },
          body: request,
        }
      );
      if (error) throw error;
      return data as unknown as CreateAssumptionResponse;
    },
  });
}

/**
 * Approve an assumption with range bounds.
 * POST /v1/workspaces/{workspace_id}/governance/assumptions/{assumption_id}/approve
 */
export function useApproveAssumption(workspaceId: string) {
  return useMutation<ApproveAssumptionResponse, Error, ApproveAssumptionInput>({
    mutationFn: async (request: ApproveAssumptionInput) => {
      const { assumption_id, ...rest } = request;
      const body: ApproveAssumptionBody = rest;
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/governance/assumptions/{assumption_id}/approve',
        {
          params: {
            path: {
              workspace_id: workspaceId,
              assumption_id,
            },
          },
          body,
        }
      );
      if (error) throw error;
      return data as unknown as ApproveAssumptionResponse;
    },
  });
}
