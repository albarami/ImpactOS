import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '../client';

// ── Response interfaces ──────────────────────────────────────────────
// Defined locally because the generated schema types may not export these
// directly in a convenient form.

export interface UploadResponse {
  doc_id: string;
  status: string;
  hash_sha256: string;
}

export interface ExtractResponse {
  job_id: string;
  status: string;
}

export interface JobStatusResponse {
  job_id: string;
  doc_id: string;
  status: string;
  error_message: string | null;
}

export interface BoQLineItem {
  line_item_id: string;
  doc_id: string;
  raw_text: string;
  description: string;
  quantity: number | null;
  unit: string | null;
  unit_price: number | null;
  total_value: number | null;
  currency_code: string;
  year_or_phase: string | null;
  vendor: string | null;
  category_code: string | null;
  page_ref: number;
  evidence_snippet_ids: string[];
  completeness_score: number | null;
  created_at: string;
}

export interface LineItemsResponse {
  items: BoQLineItem[];
}

// ── Hooks ────────────────────────────────────────────────────────────

/**
 * Upload a document via multipart form-data.
 *
 * openapi-fetch does not natively serialise FormData for multipart
 * endpoints, so we pass the FormData directly using `bodySerializer`.
 * The `body` cast to `any` is the only intentional escape from strict
 * typing in this module — documented per task spec.
 */
export function useUploadDocument(workspaceId: string) {
  return useMutation<UploadResponse, Error, FormData>({
    mutationFn: async (formData: FormData) => {
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/documents',
        {
          params: { path: { workspace_id: workspaceId } },
          // eslint-disable-next-line @typescript-eslint/no-explicit-any -- FormData cannot match typed body schema
          body: formData as any,
          bodySerializer: (body) => body as unknown as FormData,
        }
      );
      if (error) throw error;
      return data as unknown as UploadResponse;
    },
  });
}

/**
 * Trigger extraction on an already-uploaded document.
 * Accepts the doc_id as the mutation variable.
 */
export function useExtractDocument(workspaceId: string) {
  return useMutation<ExtractResponse, Error, string>({
    mutationFn: async (docId: string) => {
      const { data, error } = await api.POST(
        '/v1/workspaces/{workspace_id}/documents/{doc_id}/extract',
        {
          params: { path: { workspace_id: workspaceId, doc_id: docId } },
          body: {
            extract_tables: true,
            extract_line_items: true,
            language_hint: 'en',
          },
        }
      );
      if (error) throw error;
      return data as unknown as ExtractResponse;
    },
  });
}

/**
 * Poll job status.  Enabled only when `jobId` is non-null.
 * Polls every 2 s until the job reaches a terminal state
 * (COMPLETED | FAILED).
 */
export function useJobStatus(workspaceId: string, jobId: string | null) {
  return useQuery<JobStatusResponse>({
    queryKey: ['jobStatus', workspaceId, jobId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/v1/workspaces/{workspace_id}/jobs/{job_id}',
        {
          params: { path: { workspace_id: workspaceId, job_id: jobId! } },
        }
      );
      if (error) throw error;
      return data as unknown as JobStatusResponse;
    },
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'COMPLETED' || status === 'FAILED' ? false : 2000;
    },
  });
}

/**
 * Fetch extracted line items for a document.
 */
export function useLineItems(workspaceId: string, docId: string) {
  return useQuery<LineItemsResponse>({
    queryKey: ['lineItems', workspaceId, docId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/v1/workspaces/{workspace_id}/documents/{doc_id}/line-items',
        {
          params: { path: { workspace_id: workspaceId, doc_id: docId } },
        }
      );
      if (error) throw error;
      return data as unknown as LineItemsResponse;
    },
  });
}
