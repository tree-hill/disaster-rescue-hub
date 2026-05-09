/**
 * Auth API 封装。
 *
 * 对照 API_SPEC §1：
 * - POST /auth/login {username, password} → TokenResponse + 嵌入用户信息
 * - GET  /auth/me 返回 CurrentUser
 *
 * 后端 login 响应字段已知 access_token / refresh_token；CurrentUser 用 /auth/me 拉。
 */
import type { AxiosResponse } from 'axios';

import { api } from '@/api/client';
import type { AuthUser } from '@/store/auth';

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const r: AxiosResponse<LoginResponse> = await api.post('/auth/login', {
    username,
    password,
  });
  return r.data;
}

export async function fetchMe(): Promise<AuthUser> {
  // 后端无单独 /auth/me 时由 caller fallback 到 token 解析；此处先尝试。
  const r: AxiosResponse<AuthUser> = await api.get('/auth/me');
  return r.data;
}
