/**
 * 受保护路由（P7.2）。
 *
 * 用法（router/index.tsx）：
 *   { element: <ProtectedRoute />,                         children: [...] }   // 仅要求登录
 *   { element: <ProtectedRoute permission="alert:read" />, children: [...] }   // 还要求权限
 *
 * 行为：
 * - 未登录 → /login，并把当前 location 写到 state.from（登录后可跳回）
 * - 登录但无权限 → /cockpit（默认安全落点；不弹错误页避免与 React Router 错误边界冲突）
 */
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { selectIsAuthenticated, useAuthStore } from '@/store/auth';

interface Props {
  permission?: string;
}

export function ProtectedRoute({ permission }: Props) {
  const location = useLocation();
  const isAuth = useAuthStore(selectIsAuthenticated);
  const hasPerm = useAuthStore((s) =>
    permission ? Boolean(s.user?.permissions.includes(permission)) : true,
  );

  if (!isAuth) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (!hasPerm) {
    return <Navigate to="/cockpit" replace />;
  }
  return <Outlet />;
}
