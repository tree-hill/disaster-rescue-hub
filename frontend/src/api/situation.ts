/**
 * 态势感知 REST。
 *
 * 对照 API_SPEC §6：
 * - GET /situation/kpi → KPISnapshot
 */
import type { AxiosResponse } from 'axios';

import { api } from '@/api/client';

export interface BatteryDistribution {
  high: number;
  mid: number;
  low: number;
}

export interface KPISnapshot {
  online_robots: number;
  total_robots: number;
  completion_rate: number;
  avg_response_sec: number;
  battery_distribution: BatteryDistribution;
  active_alerts: number;
  active_tasks: number;
}

export async function fetchKpi(): Promise<KPISnapshot> {
  const r: AxiosResponse<KPISnapshot> = await api.get('/situation/kpi');
  return r.data;
}
