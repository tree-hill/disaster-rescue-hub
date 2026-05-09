/**
 * 调度 REST。对照 API_SPEC §4。
 *
 * P7.4 仅用 reassign。算法切换 / 拍卖查询留给后续接入。
 */
import type { AxiosResponse } from 'axios';

import { api } from '@/api/client';
import type { TaskRead } from '@/api/tasks';

export interface ReassignRequest {
  task_id: string;
  new_robot_id: string;
  reason: string; // 至少 5 个非空白字符
}

export interface ReassignResponse {
  task: TaskRead;
  intervention_id: string;
}

export async function reassignTask(payload: ReassignRequest): Promise<ReassignResponse> {
  const r: AxiosResponse<ReassignResponse> = await api.post('/dispatch/reassign', payload);
  return r.data;
}
