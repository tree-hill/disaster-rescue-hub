/**
 * Auth Store（P7.2）。
 *
 * 对照：
 * - DATA_CONTRACTS §5 CurrentUser
 * - API_SPEC §1 /auth/login → TokenResponse + UserRead
 *
 * 设计：
 * - persist 到 localStorage（key='drh-auth'）：刷新页面不丢登录态；客户端 401
 *   或主动登出时调 clear() 同步清空 localStorage
 * - hasPermission 用同步 selector，与 axios 拦截器 / ProtectedRoute 一致
 * - 不在 store 内调 axios（避免循环依赖）；登录请求由 Login 页面直调，再 setSession
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  roles: string[];
  permissions: string[];
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  setSession: (data: {
    user: AuthUser;
    accessToken: string;
    refreshToken: string;
  }) => void;
  clear: () => void;
  hasPermission: (perm: string) => boolean;
  hasAnyRole: (...roles: string[]) => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      setSession: ({ user, accessToken, refreshToken }) =>
        set({ user, accessToken, refreshToken }),
      clear: () => set({ user: null, accessToken: null, refreshToken: null }),
      hasPermission: (perm) => Boolean(get().user?.permissions.includes(perm)),
      hasAnyRole: (...roles) => {
        const u = get().user;
        if (!u) return false;
        return roles.some((r) => u.roles.includes(r));
      },
    }),
    { name: 'drh-auth' },
  ),
);

/** 派生 selector：是否已登录（accessToken 存在即视为登录）。 */
export const selectIsAuthenticated = (s: AuthState) => Boolean(s.accessToken);
