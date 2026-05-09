/**
 * 管理后台（对照 docs/prototypes/prototype_06_admin.html，原型本身已是 01-06 标准）。
 *
 * 后端：
 * - GET /robots（type / search / page / page_size）— 用作机器人注册表
 * - 编辑 / 删除 / 启停 / 注册新机器人 → P8 实装（PUT/DELETE/POST 都已存在但本页占位）
 *
 * 占位（待 P8 / 用户决策）：
 * - 用户管理 / 角色权限 / 审计日志 / 场景剧本 / 系统配置 → 仅菜单导航，内容占位
 */
import {
  Anchor,
  Bot,
  Edit2,
  FileText,
  Filter,
  KeyRound,
  Map,
  Plane,
  Plus,
  Power,
  RefreshCw,
  Search,
  Settings2,
  Trash2,
  Upload,
  Users,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { listRobots, type RobotRead, type RobotType } from '@/api/robots';
import { AppShell } from '@/components/common/AppShell';

const TYPE_LABEL: Record<RobotType, string> = { uav: 'AERIAL', ugv: 'GROUND', usv: 'MARINE' };
const TYPE_COLOR: Record<RobotType, string> = { uav: 'var(--robot-aerial)', ugv: 'var(--robot-ground)', usv: 'var(--robot-marine)' };
const TYPE_BG: Record<RobotType, string> = { uav: 'rgba(96,165,250,0.15)', ugv: 'rgba(167,139,250,0.15)', usv: 'rgba(34,211,238,0.15)' };

type MenuKey = 'robots' | 'users' | 'roles' | 'audit' | 'scenarios' | 'config';

const MENU_ITEMS: Array<{ k: MenuKey; label: string; icon: React.ReactNode; tag?: string; tagColor?: string }> = [
  { k: 'robots',    label: '机器人注册', icon: <Bot className="w-4 h-4" />, tag: '25' },
  { k: 'users',     label: '用户管理',   icon: <Users className="w-4 h-4" />, tag: '8', tagColor: 'var(--text-tertiary)' },
  { k: 'roles',     label: '角色权限',   icon: <KeyRound className="w-4 h-4" />, tag: '3', tagColor: 'var(--text-tertiary)' },
  { k: 'audit',     label: '审计日志',   icon: <FileText className="w-4 h-4" />, tag: '156', tagColor: 'var(--warning)' },
  { k: 'scenarios', label: '场景剧本',   icon: <Map className="w-4 h-4" />, tag: '2', tagColor: 'var(--text-tertiary)' },
  { k: 'config',    label: '系统配置',   icon: <Settings2 className="w-4 h-4" /> },
];

export function Admin() {
  const [menu, setMenu] = useState<MenuKey>('robots');
  return (
    <AppShell>
      <div className="flex" style={{ minHeight: 'calc(100vh - 56px)' }}>
        {/* 左侧菜单 */}
        <aside className="panel my-3 ml-3 flex flex-col p-3 rounded-lg shrink-0" style={{ width: 240 }}>
          <div className="text-xs font-semibold mb-3 px-2" style={{ color: 'var(--text-tertiary)' }}>系统配置</div>
          <nav className="space-y-1">
            {MENU_ITEMS.map((it) => {
              const active = it.k === menu;
              return (
                <a
                  key={it.k}
                  onClick={() => setMenu(it.k)}
                  className="px-4 py-2.5 rounded-md cursor-pointer flex items-center gap-2.5 text-sm transition"
                  style={{
                    background: active ? 'var(--accent-primary)' : 'transparent',
                    color: active ? 'white' : 'var(--text-primary)',
                  }}
                >
                  {it.icon}
                  <span className="flex-1">{it.label}</span>
                  {it.tag && (
                    <span className="text-xs mono" style={{ color: active ? 'rgba(255,255,255,0.85)' : (it.tagColor ?? 'var(--text-secondary)') }}>
                      {it.tag}
                    </span>
                  )}
                </a>
              );
            })}
          </nav>

          <div className="mt-auto pt-4 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="px-3 py-3 rounded-lg text-xs" style={{ background: 'var(--bg-tertiary)' }}>
              <div className="font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>系统信息</div>
              <div className="space-y-1.5" style={{ color: 'var(--text-tertiary)' }}>
                <div className="flex justify-between"><span>版本</span><span className="mono">v1.0.0</span></div>
                <div className="flex justify-between"><span>API 状态</span><span style={{ color: 'var(--success)' }}>● 在线</span></div>
                <div className="flex justify-between"><span>DB 端口</span><span className="mono">5433</span></div>
              </div>
            </div>
          </div>
        </aside>

        {/* 右侧内容 */}
        <main className="flex-1 p-3 flex flex-col gap-3 overflow-hidden">
          {menu === 'robots' && <RobotsPanel />}
          {menu !== 'robots' && <PlaceholderPanel menu={menu} />}
        </main>
      </div>
    </AppShell>
  );
}

function PlaceholderPanel({ menu }: { menu: MenuKey }) {
  const it = MENU_ITEMS.find((m) => m.k === menu);
  return (
    <div className="panel flex-1 flex flex-col items-center justify-center p-12 text-center">
      <div
        className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
        style={{ background: 'rgba(59,130,246,0.15)', border: '1px solid var(--accent-primary)' }}
      >
        {it?.icon}
      </div>
      <div className="text-lg font-semibold mb-2">{it?.label}</div>
      <p className="text-sm max-w-md" style={{ color: 'var(--text-secondary)' }}>
        本模块将在 P8（实验复盘 + 论文素材）阶段实装，目前后端尚未提供专用 API。
      </p>
    </div>
  );
}

function RobotsPanel() {
  const [items, setItems] = useState<RobotRead[]>([]);
  const [total, setTotal] = useState(0);
  const [type, setType] = useState<RobotType | ''>('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(15);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const refresh = useMemo(
    () => async () => {
      setLoading(true);
      try {
        const p = await listRobots({
          type: type || undefined,
          search: search || undefined,
          page,
          page_size: pageSize,
          only_active: false,
        });
        setItems(p.items);
        setTotal(p.total);
      } finally {
        setLoading(false);
      }
    },
    [type, search, page, pageSize],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const stats = useMemo(() => {
    const total_ = items.length;
    const uav = items.filter((r) => r.type === 'uav').length;
    const ugv = items.filter((r) => r.type === 'ugv').length;
    const usv = items.filter((r) => r.type === 'usv').length;
    return { total_, uav, ugv, usv };
  }, [items]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <>
      {/* 面包屑 + 标题 */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs flex items-center gap-1.5" style={{ color: 'var(--text-tertiary)' }}>
            <span>管理后台</span><span>›</span><span style={{ color: 'var(--text-secondary)' }}>机器人注册</span>
          </div>
          <h1 className="text-xl font-bold mt-1">机器人注册</h1>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-ghost flex items-center gap-1.5" onClick={() => alert('批量导入 — P8 实装')}>
            <Upload className="w-3.5 h-3.5" /> 批量导入
          </button>
          <button
            className="btn-primary flex items-center gap-1.5"
            style={{ padding: '8px 16px', fontSize: 13, fontWeight: 600 }}
            onClick={() => alert('注册新机器人 — P8 实装')}
          >
            <Plus className="w-4 h-4" /> 注册新机器人
          </button>
        </div>
      </div>

      {/* 统计 */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard icon={<Bot />} label="本页总数" value={total} color="var(--accent-primary)" bg="rgba(59,130,246,0.15)" />
        <StatCard icon={<Plane />} label="无人机" value={stats.uav} color={TYPE_COLOR.uav} bg={TYPE_BG.uav} />
        <StatCard icon={<Bot />} label="地面" value={stats.ugv} color={TYPE_COLOR.ugv} bg={TYPE_BG.ugv} />
        <StatCard icon={<Anchor />} label="水面" value={stats.usv} color={TYPE_COLOR.usv} bg={TYPE_BG.usv} />
      </div>

      {/* 表格 */}
      <div className="panel flex-1 flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b flex items-center gap-3" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="relative" style={{ flex: 1, maxWidth: 300 }}>
            <Search className="w-4 h-4 absolute left-3 top-2.5" style={{ color: 'var(--text-tertiary)' }} />
            <input
              type="text"
              placeholder="搜索编号 / 名称 / 型号..."
              className="w-full pl-9 pr-3 py-2 text-sm rounded"
              style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }}
              value={search}
              onChange={(e) => { setPage(1); setSearch(e.target.value); }}
            />
          </div>
          <select
            className="px-3 py-2 text-sm rounded"
            style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }}
            value={type}
            onChange={(e) => { setPage(1); setType(e.target.value as RobotType | ''); }}
          >
            <option value="">类型: 全部</option>
            <option value="uav">无人机</option>
            <option value="ugv">地面</option>
            <option value="usv">水面</option>
          </select>
          <div className="flex-1" />
          <button className="btn-ghost flex items-center gap-1.5" onClick={() => { setSearch(''); setType(''); setPage(1); }}>
            <Filter className="w-3.5 h-3.5" /> 清空
          </button>
          <button className="btn-ghost flex items-center gap-1.5" onClick={refresh}>
            <RefreshCw className="w-3.5 h-3.5" /> 刷新
          </button>
        </div>

        <div className="flex-1 overflow-auto">
          <table className="app-table">
            <thead>
              <tr>
                <th style={{ width: 40 }}><input type="checkbox" /></th>
                <th>编号</th>
                <th>名称</th>
                <th>类型</th>
                <th>型号</th>
                <th>能力</th>
                <th>编队</th>
                <th>状态</th>
                <th>注册时间</th>
                <th style={{ textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={10} className="text-center text-xs py-6" style={{ color: 'var(--text-tertiary)' }}>加载中…</td></tr>
              )}
              {!loading && items.length === 0 && (
                <tr><td colSpan={10} className="text-center text-xs py-6" style={{ color: 'var(--text-tertiary)' }}>暂无机器人</td></tr>
              )}
              {items.map((r) => (
                <tr key={r.id} className={!r.is_active ? 'opacity-60' : ''}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(r.id)}
                      onChange={() => toggleSelect(r.id)}
                    />
                  </td>
                  <td className="mono font-semibold">{r.code}</td>
                  <td>{r.name}</td>
                  <td>
                    <span className="badge" style={{ background: TYPE_BG[r.type], color: TYPE_COLOR[r.type] }}>{TYPE_LABEL[r.type]}</span>
                  </td>
                  <td className="mono text-xs" style={{ color: 'var(--text-secondary)' }}>{r.model ?? '—'}</td>
                  <td>
                    <code className="px-2 py-0.5 rounded text-xs" style={{ background: 'var(--bg-tertiary)' }}>
                      {`{${(r.capability.sensors || []).slice(0, 2).join(', ')}${(r.capability.sensors || []).length > 2 ? ', ...' : ''}}`}
                    </code>
                  </td>
                  <td className="text-xs" style={{ color: 'var(--text-secondary)' }}>{r.group_id?.slice(0, 8) ?? '—'}</td>
                  <td>
                    {r.is_active ? (
                      <span className="badge badge-success">● 启用</span>
                    ) : (
                      <span className="badge" style={{ background: 'rgba(92,101,128,0.15)', color: 'var(--text-tertiary)' }}>● 停用</span>
                    )}
                  </td>
                  <td className="mono text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {new Date(r.created_at).toISOString().slice(0, 10)}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button className="btn-icon" title="编辑" onClick={() => alert('编辑 — P8 实装')}>
                      <Edit2 className="w-4 h-4" style={{ color: 'var(--accent-primary)' }} />
                    </button>
                    <button className="btn-icon" title={r.is_active ? '停用' : '启用'} onClick={() => alert('启停 — P8 实装')}>
                      <Power className="w-4 h-4" style={{ color: r.is_active ? 'var(--text-secondary)' : 'var(--success)' }} />
                    </button>
                    <button className="btn-icon" title="删除" onClick={() => alert('删除 — P8 实装')}>
                      <Trash2 className="w-4 h-4" style={{ color: 'var(--danger)' }} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* 底栏 */}
        <div className="px-4 py-3 border-t flex items-center justify-between" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-center gap-3">
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              已选 <span className="font-bold text-white">{selected.size}</span> 条 | 共 {total} 条
            </span>
            <button className="btn-ghost" style={{ padding: '4px 10px' }} disabled={selected.size === 0} onClick={() => alert('批量启用 — P8 实装')}>启用</button>
            <button className="btn-ghost" style={{ padding: '4px 10px' }} disabled={selected.size === 0} onClick={() => alert('批量禁用 — P8 实装')}>禁用</button>
            <button className="btn-ghost" style={{ padding: '4px 10px', color: 'var(--danger)', borderColor: 'var(--danger)' }} disabled={selected.size === 0} onClick={() => alert('批量删除 — P8 实装')}>删除</button>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <button className="btn-ghost" style={{ padding: '4px 10px' }} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>‹</button>
            <span className="px-2">第 {page} / {totalPages} 页</span>
            <button className="btn-ghost" style={{ padding: '4px 10px' }} disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>›</button>
          </div>
        </div>
      </div>
    </>
  );
}

function StatCard({ icon, label, value, color, bg }: { icon: React.ReactNode; label: string; value: number; color: string; bg: string }) {
  return (
    <div className="panel p-4 flex items-center gap-3">
      <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: bg, color }}>
        {icon}
      </div>
      <div>
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</div>
        <div className="text-xl font-bold mono" style={{ color }}>{value}</div>
      </div>
    </div>
  );
}
