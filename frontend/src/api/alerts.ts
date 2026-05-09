/**
 * 告警 REST。
 *
 * 对照 API_SPEC §6：
 * - GET /alerts (severity/type/source/status/start_time/end_time/search/page/page_size)
 * - GET /alerts/{id}
 * - POST /alerts/{id}/acknowledge {note?}
 * - POST /alerts/{id}/ignore {reason}
 * - POST /alerts/batch-acknowledge {alert_ids[]}
 */
import type { AxiosResponse } from 'axios';

import { api } from '@/api/client';

export type AlertSeverity = 'info' | 'warn' | 'critical';

export interface AlertRead {
  id: string;
  code: string;
  type: string;
  severity: AlertSeverity;
  source: string;
  message: string;
  payload: Record<string, unknown>;
  related_task_id: string | null;
  related_robot_id: string | null;
  raised_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  is_ignored: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AlertListParams {
  severity?: AlertSeverity;
  type?: string;
  source?: string;
  status?: 'unack' | 'ack' | 'ignored';
  start_time?: string;
  end_time?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export async function listAlerts(params: AlertListParams = {}): Promise<Page<AlertRead>> {
  const r: AxiosResponse<Page<AlertRead>> = await api.get('/alerts', { params });
  return r.data;
}

export async function getAlert(id: string): Promise<AlertRead> {
  const r: AxiosResponse<AlertRead> = await api.get(`/alerts/${id}`);
  return r.data;
}

export async function acknowledgeAlert(id: string, note?: string): Promise<AlertRead> {
  const r: AxiosResponse<AlertRead> = await api.post(`/alerts/${id}/acknowledge`, { note });
  return r.data;
}

export async function ignoreAlert(id: string, reason: string): Promise<AlertRead> {
  const r: AxiosResponse<AlertRead> = await api.post(`/alerts/${id}/ignore`, { reason });
  return r.data;
}
