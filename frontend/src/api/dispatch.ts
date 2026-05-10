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

export type DispatchAlgorithm = 'AUCTION_HUNGARIAN' | 'GREEDY' | 'RANDOM';

export interface AlgorithmInfo {
  current: DispatchAlgorithm;
  available: DispatchAlgorithm[];
}

export async function getAlgorithm(): Promise<AlgorithmInfo> {
  const r: AxiosResponse<AlgorithmInfo> = await api.get('/dispatch/algorithm');
  return r.data;
}

export async function switchAlgorithm(
  algorithm: DispatchAlgorithm,
  reason: string,
): Promise<{ previous: DispatchAlgorithm; current: DispatchAlgorithm; intervention_id: string }> {
  const r = await api.post('/dispatch/algorithm', { algorithm, reason });
  return r.data;
}

export interface BidRead {
  id: string;
  auction_id: string;
  robot_id: string;
  bid_value: number;
  rank: number | null;
  is_winner: boolean;
  details: Record<string, unknown>;
}

export interface AuctionRead {
  id: string;
  task_id: string;
  algorithm: DispatchAlgorithm;
  started_at: string;
  completed_at: string | null;
  status: 'STARTED' | 'COMPLETED' | 'FAILED';
  winner_robot_id: string | null;
  bids: BidRead[];
}

export async function listAuctionsForTask(taskId: string): Promise<{ items: AuctionRead[]; total: number }> {
  const r = await api.get('/dispatch/auctions', { params: { task_id: taskId, page_size: 5 } });
  return r.data;
}

export async function getAuctionWithBids(auctionId: string): Promise<AuctionRead> {
  const r: AxiosResponse<AuctionRead> = await api.get(`/dispatch/auctions/${auctionId}`);
  return r.data;
}

export async function triggerAuction(taskId: string): Promise<AuctionRead> {
  const r: AxiosResponse<AuctionRead> = await api.post('/dispatch/auction', { task_id: taskId });
  return r.data;
}
