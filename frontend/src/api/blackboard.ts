/**
 * 黑板 REST。对照 API_SPEC §5。
 */
import type { AxiosResponse } from 'axios';

import { api } from '@/api/client';
import type { Page } from '@/api/alerts';

export interface BlackboardEntry {
  id: string | null;
  key: string;
  value: Record<string, unknown>;
  confidence: number;
  source_robot_id: string | null;
  fused_from: Array<Record<string, unknown>>;
  expires_at: string;
  updated_at: string;
}

export interface BlackboardStats {
  total_entries: number;
  by_type: Record<string, number>;
  active_subscribers: number;
  avg_fusion_latency_ms: number;
  throughput_per_min: number;
}

export interface BlackboardListParams {
  type?: string;
  key_prefix?: string;
  min_confidence?: number;
  include_expired?: boolean;
  page?: number;
  page_size?: number;
}

export async function listBlackboardEntries(
  params: BlackboardListParams = {},
): Promise<Page<BlackboardEntry>> {
  const r: AxiosResponse<Page<BlackboardEntry>> = await api.get('/blackboard/entries', { params });
  return r.data;
}

export async function getBlackboardStats(): Promise<BlackboardStats> {
  const r: AxiosResponse<BlackboardStats> = await api.get('/blackboard/stats');
  return r.data;
}
