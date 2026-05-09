/**
 * AppShell — 受保护页面共用布局（顶部导航 + 内容区）。
 *
 * 对照 docs/prototypes/prototype_01/06：
 * - 顶导左：logo（shield-check + 救灾中枢）+ 7 项菜单（指挥工作台 / 机器人管理 / 任务管理 / 协同通信 / 态势感知 / 复盘中心 / 管理后台）
 * - 顶导右：会话状态 + 主题 + 通知 + 用户头像
 *
 * 路由映射：
 * - 指挥工作台 → /cockpit
 * - 机器人管理 → /robots
 * - 任务管理 → /tasks
 * - 协同通信 → /blackboard      （原型 09 标题为「共享黑板」，归在「协同通信」菜单下）
 * - 态势感知 → /alerts          （原型 10 告警中心，归在「态势感知」菜单下）
 * - 复盘中心 → /replay          （P8 实装，路由占位 → 暂时跳到 /cockpit）
 * - 管理后台 → /admin
 */
import { Bell, ChevronDown, Moon, ShieldCheck } from 'lucide-react';
import { ReactNode } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';

import { useAuthStore } from '@/store/auth';

interface NavEntry {
  label: string;
  to: string;
  /** 路由不存在时点击降级跳到 fallback */
  fallback?: string;
}

const NAV_ENTRIES: NavEntry[] = [
  { label: '指挥工作台', to: '/cockpit' },
  { label: '机器人管理', to: '/robots' },
  { label: '任务管理', to: '/tasks' },
  { label: '协同通信', to: '/blackboard' },
  { label: '态势感知', to: '/alerts' },
  { label: '复盘中心', to: '/replay', fallback: '/cockpit' },
  { label: '管理后台', to: '/admin' },
];

interface AppShellProps {
  children: ReactNode;
  /** 顶导可选副标题（会话名 / 算法等）；不填用默认占位 */
  sessionInfo?: ReactNode;
  /** 内容区是否填满高度（cockpit 用 true；列表页 false 默认 padding） */
  fullHeight?: boolean;
}

export function AppShell({ children, sessionInfo, fullHeight = false }: AppShellProps) {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();

  const initial = user?.display_name?.[0] || user?.username?.[0] || 'U';

  const handleLogout = () => {
    clear();
    navigate('/login', { replace: true });
  };

  return (
    <div className={fullHeight ? 'h-screen flex flex-col' : 'min-h-screen flex flex-col'}>
      <header
        className="h-14 flex items-center justify-between px-6 border-b shrink-0"
        style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border-subtle)' }}
      >
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-6 h-6" style={{ color: 'var(--accent-primary)' }} />
            <span className="text-base font-bold">救灾中枢</span>
          </div>
          <nav className="flex items-center gap-1">
            {NAV_ENTRIES.map((e) => (
              <NavLink
                key={e.to}
                to={e.fallback ?? e.to}
                className={({ isActive }) =>
                  `nav-item ${isActive ? 'nav-item-active' : 'nav-item-inactive'}`
                }
              >
                {e.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-5">
          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
            <span className="pulse-dot"></span>
            {sessionInfo ?? (
              <span>当前会话: <span className="text-white">演练 / 默认</span></span>
            )}
          </div>
          <button className="btn-ghost flex items-center gap-1.5">
            <Moon className="w-3.5 h-3.5" /> 主题
          </button>
          <div className="relative cursor-pointer" onClick={() => navigate('/alerts')}>
            <Bell className="w-5 h-5" style={{ color: 'var(--text-secondary)' }} />
          </div>
          <div className="flex items-center gap-2 cursor-pointer" onClick={handleLogout} title="点击登出">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold"
              style={{ background: 'var(--accent-primary)' }}
            >
              {initial.toUpperCase()}
            </div>
            <span className="text-sm">{user?.username ?? '...'}</span>
            <ChevronDown className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />
          </div>
        </div>
      </header>

      <div className={fullHeight ? 'flex-1 overflow-hidden flex flex-col' : 'flex-1'}>
        {children}
      </div>
    </div>
  );
}
