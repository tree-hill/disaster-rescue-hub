/**
 * 实验模块 API 客户端（P8.2/P8.4）。
 * 对照 API_SPEC §7 POST/GET /experiments。
 */
import { api } from './client';

export interface ExperimentBatchRequest {
  scenario_id: string;
  algorithms: string[];
  repetitions: number;
}

export interface ExperimentBatchStart {
  batch_id: string;
  status: string;
  estimated_duration_sec: number;
}

export interface ExperimentRunRead {
  id: string;
  batch_id: string;
  scenario_id: string;
  algorithm: string;
  run_index: number;
  completion_rate: number | null;
  avg_response_sec: number | null;
  total_path_km: number | null;
  load_std_dev: number | null;
  decision_latency_ms: number | null;
  raw_metrics: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
}

export interface AlgorithmStats {
  avg_completion_rate: number;
  avg_response_sec: number;
  avg_total_path_km: number;
  avg_load_std_dev: number;
  avg_decision_latency_ms: number;
  std_decision_latency_ms: number;
  run_count: number;
}

export interface ExperimentBatchStatus {
  batch_id: string;
  status: 'running' | 'completed' | 'failed';
  progress_pct: number;
  runs: ExperimentRunRead[];
  stats: Record<string, AlgorithmStats>;
}

export interface ChartDataset {
  label: string;
  data: number[];
}

export interface ChartData {
  labels: string[];
  datasets: ChartDataset[];
}

export interface ExperimentChartsResponse {
  completion_rate_chart: ChartData;
  response_time_chart: ChartData;
  path_length_chart: ChartData;
  load_balance_chart: ChartData;
  decision_latency_chart: ChartData;
}

export async function startExperiment(
  payload: ExperimentBatchRequest,
): Promise<ExperimentBatchStart> {
  const res = await api.post<ExperimentBatchStart>('/experiments', payload);
  return res.data;
}

export async function getExperimentBatch(batchId: string): Promise<ExperimentBatchStatus> {
  const res = await api.get<ExperimentBatchStatus>(`/experiments/${batchId}`);
  return res.data;
}

export async function getExperimentCharts(batchId: string): Promise<ExperimentChartsResponse> {
  const res = await api.get<ExperimentChartsResponse>(`/experiments/${batchId}/charts`);
  return res.data;
}

export async function exportExperiment(
  batchId: string,
  format: 'json' | 'csv',
): Promise<void> {
  const a = document.createElement('a');
  a.href = `/api/v1/experiments/${batchId}/export?format=${format}`;
  a.download = `experiment_${batchId}.${format}`;
  a.click();
}
