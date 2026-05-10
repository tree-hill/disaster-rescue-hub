/**
 * Scenario REST. 对照 API_SPEC §8 与 backend/app/api/v1/scenarios.py。
 */
import type { AxiosResponse } from 'axios';

import { api } from '@/api/client';

export interface ScenarioRead {
  id: string;
  name: string;
  disaster_type: string;
  is_active: boolean;
}

export async function listScenarios(): Promise<ScenarioRead[]> {
  const r: AxiosResponse<ScenarioRead[]> = await api.get('/scenarios');
  return r.data;
}
