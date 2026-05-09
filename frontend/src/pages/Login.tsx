/**
 * 登录页（对照 docs/prototypes/prototype_03_login.html）。
 *
 * 流程：
 * 1) POST /auth/login → 拿 access_token / refresh_token
 * 2) GET /auth/me → 拿 CurrentUser（roles / permissions）
 * 3) setSession 写入 store；4) ws.connect()；5) 跳 /cockpit
 *
 * 角色按钮（指挥员 / 管理员）只是 UI 提示，不参与请求 —— 后端按用户名 / 密码校验。
 */
import { ArrowRight, Crosshair, Eye, EyeOff, Lock, RadioTower, Settings, ShieldCheck, User } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { fetchMe, login as loginApi } from '@/api/auth';
import { useAuthStore } from '@/store/auth';
import { useWSStore } from '@/store/ws';

type RoleHint = 'commander' | 'admin';

export function Login() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const wsConnect = useWSStore((s) => s.connect);

  const [role, setRole] = useState<RoleHint>('commander');
  const [username, setUsername] = useState('commander001');
  const [password, setPassword] = useState('password123');
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const tokens = await loginApi(username.trim(), password);
      // 临时把 token 注入 store，让后续 /auth/me 拦截器能带上 Bearer
      setSession({
        user: { id: '', username: '', display_name: '', roles: [], permissions: [] },
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
      });
      const user = await fetchMe();
      setSession({
        user,
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
      });
      wsConnect();
      navigate('/cockpit', { replace: true });
    } catch (err: unknown) {
      const e_ = err as { response?: { data?: { message?: string } } };
      setError(e_?.response?.data?.message ?? '登录失败,请检查用户名或密码');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="h-screen flex" style={{ background: 'var(--bg-primary)' }}>
      {/* 左侧装饰区 */}
      <div
        className="flex-1 relative flex flex-col justify-between p-12 overflow-hidden"
        style={{
          background: `radial-gradient(circle at 20% 30%, rgba(59,130,246,0.12) 0%, transparent 50%),
                       radial-gradient(circle at 80% 70%, rgba(16,185,129,0.10) 0%, transparent 50%),
                       radial-gradient(circle at 50% 50%, rgba(245,158,11,0.05) 0%, transparent 60%),
                       var(--bg-secondary)`,
          backgroundImage: `linear-gradient(rgba(58,66,88,0.15) 1px, transparent 1px),
                            linear-gradient(90deg, rgba(58,66,88,0.15) 1px, transparent 1px)`,
          backgroundSize: '40px 40px',
        }}
      >
        <div className="flex items-center gap-3 z-10">
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(59,130,246,0.2)', border: '1px solid var(--accent-primary)' }}
          >
            <ShieldCheck className="w-7 h-7" style={{ color: 'var(--accent-primary)' }} />
          </div>
          <div>
            <div className="text-xl font-bold">救灾中枢</div>
            <div className="text-xs mono" style={{ color: 'var(--text-tertiary)' }}>
              Disaster Rescue Hub
            </div>
          </div>
        </div>

        <div className="relative flex-1 flex items-center justify-center">
          <div className="text-center z-10 relative">
            <div
              className="inline-flex items-center justify-center w-24 h-24 rounded-2xl mb-4"
              style={{
                background: 'rgba(59,130,246,0.15)',
                border: '2px solid var(--accent-primary)',
                boxShadow: '0 0 60px rgba(59,130,246,0.3)',
              }}
            >
              <RadioTower className="w-12 h-12" style={{ color: 'var(--accent-primary)' }} />
            </div>
            <div className="text-2xl font-bold mb-2">异构多机器人协同指挥中枢</div>
            <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              海陆空协同 · 智能调度 · 人机共治
            </div>

            <div className="flex gap-3 mt-8 justify-center">
              {[
                { label: '在线机器人', value: '25', color: 'var(--success)' },
                { label: '活跃会话', value: '3', color: 'var(--accent-primary)' },
              ].map((it) => (
                <div
                  key={it.label}
                  className="px-5 py-3 rounded-lg"
                  style={{
                    background: 'rgba(26,31,46,0.8)',
                    border: '1px solid var(--border-subtle)',
                    backdropFilter: 'blur(8px)',
                  }}
                >
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {it.label}
                  </div>
                  <div className="text-xl font-bold mono" style={{ color: it.color }}>
                    {it.value}
                  </div>
                </div>
              ))}
              <div
                className="px-5 py-3 rounded-lg"
                style={{
                  background: 'rgba(26,31,46,0.8)',
                  border: '1px solid var(--border-subtle)',
                  backdropFilter: 'blur(8px)',
                }}
              >
                <div
                  className="text-xs flex items-center gap-1.5"
                  style={{ color: 'var(--text-tertiary)' }}
                >
                  <span className="pulse-dot"></span>系统运行
                </div>
                <div className="text-xl font-bold mono" style={{ color: 'var(--text-primary)' }}>
                  正常
                </div>
              </div>
            </div>
          </div>
        </div>

        <div
          className="z-10 text-xs flex items-center justify-between"
          style={{ color: 'var(--text-tertiary)' }}
        >
          <div className="mono">© 2026 Disaster Rescue Hub · v1.0</div>
          <div>[Powered by FastAPI + React]</div>
        </div>
      </div>

      {/* 右侧登录卡 */}
      <div
        className="w-[480px] flex items-center justify-center p-12"
        style={{ background: 'var(--bg-primary)' }}
      >
        <form className="w-full max-w-sm" onSubmit={handleSubmit}>
          <div className="mb-8">
            <h1 className="text-2xl font-bold mb-2">欢迎登录</h1>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              使用您的指挥员或管理员账号登录系统
            </p>
          </div>

          {/* 角色选择 */}
          <div className="mb-5">
            <label
              className="text-xs font-semibold mb-2 block"
              style={{ color: 'var(--text-secondary)' }}
            >
              选择登录身份
            </label>
            <div className="flex gap-3">
              {(['commander', 'admin'] as RoleHint[]).map((r) => {
                const selected = r === role;
                const Icon = r === 'commander' ? Crosshair : Settings;
                return (
                  <div
                    key={r}
                    onClick={() => setRole(r)}
                    style={{
                      flex: 1,
                      padding: 14,
                      borderRadius: 8,
                      cursor: 'pointer',
                      textAlign: 'center',
                      background: selected ? 'rgba(59,130,246,0.1)' : 'var(--bg-tertiary)',
                      border: `1px solid ${selected ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                      boxShadow: selected ? '0 0 0 1px var(--accent-primary)' : undefined,
                    }}
                  >
                    <Icon
                      className="w-5 h-5 mx-auto mb-1.5"
                      style={{ color: selected ? 'var(--accent-primary)' : 'var(--text-secondary)' }}
                    />
                    <div className="text-sm font-semibold">
                      {r === 'commander' ? '指挥员' : '管理员'}
                    </div>
                    <div
                      className="text-xs mt-0.5"
                      style={{ color: 'var(--text-tertiary)' }}
                    >
                      {r === 'commander' ? 'Commander' : 'Admin'}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 用户名 */}
          <div className="mb-4">
            <label
              className="text-xs font-semibold mb-2 block"
              style={{ color: 'var(--text-secondary)' }}
            >
              用户名
            </label>
            <div className="relative">
              <User
                className="w-4 h-4 absolute left-3 top-3.5"
                style={{ color: 'var(--text-tertiary)' }}
              />
              <input
                type="text"
                className="input-field pl-10"
                placeholder="请输入用户名"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </div>
          </div>

          {/* 密码 */}
          <div className="mb-4">
            <label
              className="text-xs font-semibold mb-2 block"
              style={{ color: 'var(--text-secondary)' }}
            >
              密码
            </label>
            <div className="relative">
              <Lock
                className="w-4 h-4 absolute left-3 top-3.5"
                style={{ color: 'var(--text-tertiary)' }}
              />
              <input
                type={showPassword ? 'text' : 'password'}
                className="input-field pl-10 pr-10"
                placeholder="请输入密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="absolute right-3 top-3.5"
                onClick={() => setShowPassword((v) => !v)}
              >
                {showPassword ? (
                  <EyeOff className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />
                ) : (
                  <Eye className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />
                )}
              </button>
            </div>
          </div>

          {/* 选项 */}
          <div className="flex items-center justify-between mb-6 text-xs">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="accent-blue-500"
              />
              <span style={{ color: 'var(--text-secondary)' }}>记住我</span>
            </label>
            <a href="#" className="font-semibold" style={{ color: 'var(--accent-primary)' }}>
              忘记密码?
            </a>
          </div>

          {error && (
            <div
              className="mb-4 px-3 py-2 rounded text-xs"
              style={{
                background: 'rgba(239,68,68,0.1)',
                border: '1px solid rgba(239,68,68,0.3)',
                color: 'var(--danger)',
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="mb-4 flex items-center justify-center gap-2 w-full"
            style={{
              background: 'linear-gradient(90deg, var(--accent-primary), #2563EB)',
              color: 'white',
              padding: 12,
              borderRadius: 8,
              fontSize: 15,
              fontWeight: 600,
              border: 'none',
              cursor: submitting ? 'not-allowed' : 'pointer',
              boxShadow: '0 4px 12px rgba(59,130,246,0.25)',
              opacity: submitting ? 0.7 : 1,
            }}
          >
            {submitting ? '登录中…' : '登 录'}
            <ArrowRight className="w-4 h-4" />
          </button>

          <div
            className="text-center text-xs"
            style={{ color: 'var(--text-tertiary)' }}
          >
            登录即表示您同意系统使用规范与审计政策
          </div>

          <div
            className="mt-12 pt-6 border-t"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div
              className="text-xs space-y-1.5"
              style={{ color: 'var(--text-tertiary)' }}
            >
              <div className="flex items-center justify-between">
                <span>系统版本</span>
                <span className="mono">v1.0.0</span>
              </div>
              <div className="flex items-center justify-between">
                <span>API 状态</span>
                <span className="flex items-center gap-1.5">
                  <span className="pulse-dot"></span>
                  <span style={{ color: 'var(--success)' }}>在线</span>
                </span>
              </div>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
