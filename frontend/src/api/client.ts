/**
 * Axios 客户端（P7.2）。
 *
 * 对照 BUILD_ORDER §P7.2：「axios 拦截器(自动加 Token,401 跳登录)」。
 *
 * 设计：
 * - baseURL 默认 '/api/v1'：开发模式由 vite dev server 代理到 :8000；生产同源部署
 *   时也走 /api/v1。可用 VITE_API_BASE_URL 覆盖。
 * - token 实时从 useAuthStore 读取，避免 localStorage / store 双源不一致
 * - 401 → 清空 auth + 跳 /login（已在登录页则不跳，避免循环）
 */
import axios from 'axios';

import { useAuthStore } from '@/store/auth';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  timeout: 10000,
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error?.response?.status === 401) {
      useAuthStore.getState().clear();
      if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);
