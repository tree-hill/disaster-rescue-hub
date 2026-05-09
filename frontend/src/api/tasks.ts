/**
 * 任务 REST。对照 API_SPEC §3。
 */
import type { AxiosResponse } from 'axios';

import { api } from '@/api/client';
import type { Page } from '@/api/alerts';
import type { Position } from '@/api/robots';

export type TaskStatus =
  | 'PENDING'
  | 'ASSIGNED'
  | 'EXECUTING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export type TaskType = 'search_rescue' | 'recon' | 'transport' | 'patrol';

export interface TargetArea {
  type: 'rectangle' | 'polygon' | 'circle';
  bounds?: { sw: Position; ne: Position };
  vertices?: Position[];
  center?: Position;
  radius_m?: number;
  area_km2: number;
  center_point: Position;
}

export interface TaskRequiredCapabilities {
  sensors: string[];
  payloads: string[];
  min_battery_pct: number;
  robot_type?: ('uav' | 'ugv' | 'usv')[] | null;
}

export interface TaskRead {
  id: string;
  code: string;
  name: string;
  type: TaskType;
  priority: 1 | 2 | 3;
  status: TaskStatus;
  target_area: TargetArea;
  required_capabilities: TaskRequiredCapabilities;
  parent_id: string | null;
  progress: number;
  sla_deadline: string | null;
  created_by: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}

export interface TaskListParams {
  status?: TaskStatus[] | TaskStatus;
  priority?: 1 | 2 | 3;
  type?: TaskType;
  search?: string;
  page?: number;
  page_size?: number;
}

export interface TaskCreatePayload {
  name: string;
  type: TaskType;
  priority: 1 | 2 | 3;
  target_area: TargetArea;
  required_capabilities: TaskRequiredCapabilities;
  sla_deadline?: string | null;
}

export async function listTasks(params: TaskListParams = {}): Promise<Page<TaskRead>> {
  const r: AxiosResponse<Page<TaskRead>> = await api.get('/tasks', { params });
  return r.data;
}

export async function getTask(id: string): Promise<TaskRead> {
  const r: AxiosResponse<TaskRead> = await api.get(`/tasks/${id}`);
  return r.data;
}

export async function createTask(payload: TaskCreatePayload): Promise<TaskRead> {
  const r: AxiosResponse<TaskRead> = await api.post('/tasks', payload);
  return r.data;
}

export async function cancelTask(id: string, reason: string): Promise<TaskRead> {
  const r: AxiosResponse<TaskRead> = await api.post(`/tasks/${id}/cancel`, { reason });
  return r.data;
}
