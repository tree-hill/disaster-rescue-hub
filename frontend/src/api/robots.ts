/**
 * 机器人 REST。对照 API_SPEC §2。
 */
import type { AxiosResponse } from 'axios';

import { api } from '@/api/client';
import type { Page } from '@/api/alerts';

export type RobotType = 'uav' | 'ugv' | 'usv';
export type FsmState = 'IDLE' | 'BIDDING' | 'EXECUTING' | 'RETURNING' | 'FAULT';

export interface Position {
  lat: number;
  lng: number;
  altitude_m?: number | null;
  heading_deg?: number | null;
}

export interface RobotCapability {
  sensors: string[];
  payloads: string[];
  max_speed_mps: number;
  max_battery_min: number;
  max_range_km: number;
  has_yolo: boolean;
  weight_kg: number;
}

export interface RobotRead {
  id: string;
  code: string;
  name: string;
  type: RobotType;
  model: string | null;
  capability: RobotCapability;
  group_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RobotStateRead {
  id: number;
  robot_id: string;
  recorded_at: string;
  fsm_state: FsmState;
  position: Position;
  battery: number;
  sensor_data: Record<string, unknown>;
  current_task_id: string | null;
}

export interface RobotDetailRead extends RobotRead {
  latest_state: RobotStateRead | null;
}

export interface RobotListParams {
  type?: RobotType;
  group_id?: string;
  search?: string;
  only_active?: boolean;
  page?: number;
  page_size?: number;
}

export async function listRobots(params: RobotListParams = {}): Promise<Page<RobotRead>> {
  const { only_active, ...rest } = params;
  const queryParams: Record<string, unknown> = { ...rest };
  if (only_active !== undefined) {
    // backend uses include_inactive (inverted semantics)
    queryParams.include_inactive = !only_active;
  }
  const r: AxiosResponse<Page<RobotRead>> = await api.get('/robots', { params: queryParams });
  return r.data;
}

export async function getRobot(id: string): Promise<RobotDetailRead> {
  const r: AxiosResponse<RobotDetailRead> = await api.get(`/robots/${id}`);
  return r.data;
}

export async function listRobotStates(robotId: string, limit = 1): Promise<RobotStateRead[]> {
  const r: AxiosResponse<RobotStateRead[]> = await api.get(`/robots/${robotId}/states`, {
    params: { limit },
  });
  return r.data;
}

export async function recallRobot(robotId: string, reason: string): Promise<void> {
  await api.post(`/robots/${robotId}/recall`, { reason });
}

export interface RobotCreatePayload {
  code: string;
  name: string;
  type: RobotType;
  model?: string | null;
  capability: RobotCapability;
  group_id?: string | null;
}

export interface RobotUpdatePayload {
  name?: string;
  model?: string | null;
  capability?: RobotCapability;
  group_id?: string | null;
  is_active?: boolean;
}

export async function createRobot(payload: RobotCreatePayload): Promise<RobotRead> {
  const r: AxiosResponse<RobotRead> = await api.post('/robots', payload);
  return r.data;
}

export async function updateRobot(id: string, payload: RobotUpdatePayload): Promise<RobotRead> {
  const r: AxiosResponse<RobotRead> = await api.put(`/robots/${id}`, payload);
  return r.data;
}

export async function deleteRobot(id: string): Promise<void> {
  await api.delete(`/robots/${id}`);
}
