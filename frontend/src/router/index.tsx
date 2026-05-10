/**
 * 路由表（P7.2）。
 *
 * 对照 BUILD_ORDER §P7.2：「6 大页面路由 + 受保护路由组件」。
 *
 * 6 个核心页面：
 * - /cockpit              指挥工作台（默认落点）
 * - /robots               机器人管理
 * - /tasks                任务管理
 * - /blackboard           黑板可视化
 * - /alerts               告警中心
 * - /admin                管理员（仅 admin 角色，权限 system:admin）
 *
 * Replay / Experiment 已在 /replay 内以双 Tab 实现。
 */
import { createBrowserRouter, Navigate } from 'react-router-dom';

import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { Admin } from '@/pages/Admin';
import { AlertCenter } from '@/pages/AlertCenter';
import { Blackboard } from '@/pages/Blackboard';
import { Cockpit } from '@/pages/Cockpit';
import { Login } from '@/pages/Login';
import { Replay } from '@/pages/Replay';
import { RobotManagement } from '@/pages/RobotManagement';
import { TaskManagement } from '@/pages/TaskManagement';

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/cockpit" replace /> },
  { path: '/login', element: <Login /> },
  {
    element: <ProtectedRoute />,
    children: [
      { path: '/cockpit', element: <Cockpit /> },
      { path: '/robots', element: <RobotManagement /> },
      { path: '/tasks', element: <TaskManagement /> },
      { path: '/blackboard', element: <Blackboard /> },
      { path: '/alerts', element: <AlertCenter /> },
      { path: '/replay', element: <Replay /> },
    ],
  },
  {
    element: <ProtectedRoute permission="system:admin" />,
    children: [{ path: '/admin', element: <Admin /> }],
  },
  { path: '*', element: <Navigate to="/cockpit" replace /> },
]);
