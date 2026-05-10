import type { AxiosResponse } from 'axios';

import { api } from '@/api/client';
import type { Page } from '@/api/alerts';
import type { Position } from '@/api/robots';

export type ReplayAlgorithm = 'AUCTION_HUNGARIAN' | 'GREEDY' | 'RANDOM' | string;

export interface RobotFrame {
  robot_id: string;
  code: string;
  fsm_state: string;
  position: Position | null;
  battery: number;
  current_task_id: string | null;
}

export interface TaskFrame {
  task_id: string;
  code: string;
  status: string;
  progress: number;
  assigned_robot_ids: string[];
}

export interface Snapshot {
  ts: string;
  robots: RobotFrame[];
  tasks: TaskFrame[];
  blackboard: {
    total_entries: number;
    by_type: Record<string, number>;
  };
}

export interface KeyEvent {
  ts: string;
  type:
    | 'task_completed'
    | 'task_failed'
    | 'task_cancelled'
    | 'task_reassigned'
    | 'intervention'
    | 'alert'
    | 'auction_completed'
    | 'recall';
  description: string;
  related_id: string | null;
}

export interface ReplaySummary {
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  total_robots_used: number;
  total_interventions: number;
  total_alerts: number;
  yolo_detections_summary: {
    survivor: number;
    fire: number;
    smoke: number;
    collapsed_building: number;
  };
  snapshots: Snapshot[];
  key_events: KeyEvent[];
}

export interface ReplaySessionRead {
  id: string;
  name: string;
  scenario_id: string | null;
  algorithm: ReplayAlgorithm;
  started_at: string;
  ended_at: string | null;
  duration_sec: number | null;
  completion_rate: number | null;
  summary: ReplaySummary;
  created_by: string;
  created_at: string;
}

export interface ReplaySessionListParams {
  start_time?: string;
  end_time?: string;
  algorithm?: string;
  scenario_id?: string;
  page?: number;
  page_size?: number;
}

export async function listReplaySessions(
  params: ReplaySessionListParams = {},
): Promise<Page<ReplaySessionRead>> {
  const r: AxiosResponse<Page<ReplaySessionRead>> = await api.get('/replay/sessions', { params });
  return r.data;
}

export async function getReplaySession(id: string): Promise<ReplaySessionRead> {
  const r: AxiosResponse<ReplaySessionRead> = await api.get(`/replay/sessions/${id}`);
  return r.data;
}

export async function listReplaySnapshots(
  id: string,
  params: { start_time?: string; end_time?: string; interval_sec?: number } = {},
): Promise<Snapshot[]> {
  const r: AxiosResponse<Snapshot[]> = await api.get(`/replay/sessions/${id}/snapshots`, {
    params,
  });
  return r.data;
}

export async function listReplayKeyEvents(
  id: string,
  params: { start_time?: string; end_time?: string } = {},
): Promise<KeyEvent[]> {
  const r: AxiosResponse<KeyEvent[]> = await api.get(`/replay/sessions/${id}/key-events`, {
    params,
  });
  return r.data;
}
