import { useQuery } from '@tanstack/react-query';
import { api } from '../client';

export interface HealthResponse {
  status: 'ok' | 'degraded';
  components?: Record<string, string>;
}

export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: async () => {
      const { data, error } = await api.GET('/health');
      if (error) throw error;
      // The OpenAPI schema types the response as Record<string, never>
      // but the actual API returns { status, components }
      return data as unknown as HealthResponse;
    },
    refetchInterval: 30_000,
  });
}
