/**
 * 机器人管理（对照 docs/prototypes/prototype_07_robot_management.html，按 01-06 设计标准统一）。
 *
 * 后端：
 * - GET /robots（type / group_id / search / only_active / page / page_size）
 * - GET /robots/{id}（详情 + 嵌入最新 RobotStateRead）
 * - POST /robots/{id}/recall {reason}
 *
 * 占位：
 * - 移动到编队 / 删除 / 编辑 → 暂未接 PUT/DELETE，按钮 alert() 提示「P8 实装」
 */
import {
  AlertTriangle,
  Anchor,
  Bot,
  ListFilter,
  Plane,
  RefreshCw,
  RotateCcw,
  Search,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  listRobots,
  getRobot,
  recallRobot,
  updateRobot,
  type FsmState,
  type RobotDetailRead,
  type RobotRead,
  type RobotType,
} from '@/api/robots';
import { AppShell } from '@/components/common/AppShell';

const TYPE_LABEL: Record<RobotType, string> = { uav: '无人机', ugv: '地面', usv: '水面' };
const TYPE_COLOR: Record<RobotType, string> = {
  uav: 'var(--robot-aerial)',
  ugv: 'var(--robot-ground)',
  usv: 'var(--robot-marine)',
};
const TYPE_BG: Record<RobotType, string> = {
  uav: 'rgba(96,165,250,0.15)',
  ugv: 'rgba(167,139,250,0.15)',
  usv: 'rgba(34,211,238,0.15)',
};

const FSM_BADGE: Record<FsmState, { bg: string; fg: string }> = {
  IDLE: { bg: 'rgba(16,185,129,0.15)', fg: 'var(--success)' },
  EXECUTING: { bg: 'rgba(6,182,212,0.15)', fg: 'var(--info)' },
  BIDDING: { bg: 'rgba(245,158,11,0.15)', fg: 'var(--warning)' },
  RETURNING: { bg: 'rgba(96,165,250,0.15)', fg: 'var(--robot-aerial)' },
  FAULT: { bg: 'rgba(239,68,68,0.15)', fg: 'var(--danger)' },
};

function batteryColor(pct: number): string {
  if (pct >= 60) return 'var(--success)';
  if (pct >= 30) return 'var(--warning)';
  return 'var(--danger)';
}

function TypeIcon({ type }: { type: RobotType }) {
  if (type === 'uav') return <Plane className="w-4 h-4" style={{ color: TYPE_COLOR.uav }} />;
  if (type === 'usv') return <Anchor className="w-4 h-4" style={{ color: TYPE_COLOR.usv }} />;
  return <Bot className="w-4 h-4" style={{ color: TYPE_COLOR.ugv }} />;
}

interface Row extends RobotRead {
  fsm?: FsmState;
  battery?: number;
}

export function RobotManagement() {
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [type, setType] = useState<RobotType | ''>('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(15);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RobotDetailRead | null>(null);

  const refresh = useMemo(
    () => async () => {
      setLoading(true);
      try {
        const p = await listRobots({
          type: type || undefined,
          search: search || undefined,
          page,
          page_size: pageSize,
        });
        // 拉每行最新状态做混入（限 5 条避免 N+1 拥堵）
        const items = await Promise.all(
          p.items.map(async (r, idx): Promise<Row> => {
            if (idx >= 5) return r;
            try {
              const d = await getRobot(r.id);
              return { ...r, fsm: d.latest_state?.fsm_state, battery: d.latest_state?.battery };
            } catch {
              return r;
            }
          }),
        );
        setRows(items);
        setTotal(p.total);
        if (items.length > 0 && !items.find((x) => x.id === selectedId)) {
          setSelectedId(items[0].id);
        }
      } finally {
        setLoading(false);
      }
    },
    [type, search, page, pageSize, selectedId],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    getRobot(selectedId).then(setDetail).catch(() => setDetail(null));
  }, [selectedId]);

  const stats = useMemo(() => {
    const total = rows.length;
    const uav = rows.filter((r) => r.type === 'uav').length;
    const ugv = rows.filter((r) => r.type === 'ugv').length;
    const usv = rows.filter((r) => r.type === 'usv').length;
    const fault = rows.filter((r) => r.fsm === 'FAULT').length;
    return { total, uav, ugv, usv, fault };
  }, [rows]);

  const handleRecall = async (id: string) => {
    const reason = window.prompt('召回原因（必填，至少 5 字）');
    if (!reason || reason.trim().length < 5) return;
    try {
      await recallRobot(id, reason.trim());
      await refresh();
    } catch (e: unknown) {
      const m = (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? String(e);
      alert(`召回失败：${m}`);
    }
  };

  const handleQuickEdit = async (r: RobotRead) => {
    const newName = window.prompt(`重命名 ${r.code}（当前：${r.name}）`, r.name);
    if (newName == null) return;
    const trimmed = newName.trim();
    if (trimmed.length === 0 || trimmed === r.name) return;
    try {
      await updateRobot(r.id, { name: trimmed });
      await refresh();
    } catch (e: unknown) {
      const m = (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? String(e);
      alert(`保存失败：${m}`);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <AppShell>
      <div className="container mx-auto px-6 py-5">
        <div className="text-xs flex items-center gap-1.5 mb-4" style={{ color: 'var(--text-tertiary)' }}>
          <span>机器人管理</span>
          <span>/</span>
          <span style={{ color: 'var(--text-secondary)' }}>列表与详情</span>
        </div>

        {/* 顶部统计 */}
        <div className="grid grid-cols-5 gap-3 mb-4">
          <StatCard icon={<Bot className="w-5 h-5" />} label="总数" value={total} color="var(--accent-primary)" bg="rgba(59,130,246,0.15)" />
          <StatCard icon={<Plane className="w-5 h-5" />} label="无人机 (UAV)" value={stats.uav} color={TYPE_COLOR.uav} bg={TYPE_BG.uav} />
          <StatCard icon={<Bot className="w-5 h-5" />} label="地面 (UGV)" value={stats.ugv} color={TYPE_COLOR.ugv} bg={TYPE_BG.ugv} />
          <StatCard icon={<Anchor className="w-5 h-5" />} label="水面 (USV)" value={stats.usv} color={TYPE_COLOR.usv} bg={TYPE_BG.usv} />
          <StatCard icon={<AlertTriangle className="w-5 h-5" />} label="故障" value={stats.fault} color="var(--danger)" bg="rgba(239,68,68,0.15)" />
        </div>

        {/* 工具栏 */}
        <div className="panel p-3 flex items-center gap-2 mb-4">
          <div className="relative" style={{ width: 280 }}>
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
          <button className="btn-ghost flex items-center gap-1.5" onClick={() => { setSearch(''); setType(''); setPage(1); }}>
            <ListFilter className="w-3.5 h-3.5" /> 清空
          </button>
          <button className="btn-ghost flex items-center gap-1.5" onClick={refresh}>
            <RefreshCw className="w-3.5 h-3.5" /> 刷新
          </button>
          <div className="flex-1" />
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>共 {total} 台</span>
        </div>

        {/* 主体 */}
        <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 380px' }}>
          {/* 列表 */}
          <div className="panel overflow-hidden">
            <div className="overflow-x-auto">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>编号</th>
                    <th>名称</th>
                    <th>类型</th>
                    <th>型号</th>
                    <th>能力</th>
                    <th>状态</th>
                    <th className="text-right" style={{ textAlign: 'right' }}>电量</th>
                    <th className="text-right" style={{ textAlign: 'right' }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && (
                    <tr><td colSpan={8} className="text-center text-xs py-6" style={{ color: 'var(--text-tertiary)' }}>加载中…</td></tr>
                  )}
                  {!loading && rows.length === 0 && (
                    <tr><td colSpan={8} className="text-center text-xs py-6" style={{ color: 'var(--text-tertiary)' }}>暂无机器人</td></tr>
                  )}
                  {rows.map((r) => {
                    const fsm = r.fsm ?? 'IDLE';
                    const fsmStyle = FSM_BADGE[fsm];
                    return (
                      <tr
                        key={r.id}
                        onClick={() => setSelectedId(r.id)}
                        style={{
                          cursor: 'pointer',
                          background: selectedId === r.id ? 'rgba(59,130,246,0.08)' : undefined,
                        }}
                      >
                        <td className="mono font-semibold">
                          <span className="flex items-center gap-1.5">
                            <TypeIcon type={r.type} />
                            {r.code}
                          </span>
                        </td>
                        <td>{r.name}</td>
                        <td>
                          <span className="badge" style={{ background: TYPE_BG[r.type], color: TYPE_COLOR[r.type] }}>
                            {TYPE_LABEL[r.type]}
                          </span>
                        </td>
                        <td className="mono text-xs" style={{ color: 'var(--text-secondary)' }}>{r.model ?? '—'}</td>
                        <td>
                          <code className="px-2 py-0.5 rounded text-xs" style={{ background: 'var(--bg-tertiary)' }}>
                            {(r.capability.sensors || []).slice(0, 2).join(', ') || '—'}
                          </code>
                        </td>
                        <td>
                          <span className="badge" style={{ background: fsmStyle.bg, color: fsmStyle.fg }}>● {fsm}</span>
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          {r.battery != null ? (
                            <span className="mono text-xs" style={{ color: batteryColor(r.battery) }}>
                              {r.battery.toFixed(0)}%
                            </span>
                          ) : (
                            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>—</span>
                          )}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            className="text-xs hover:underline"
                            style={{ color: 'var(--accent-primary)' }}
                            onClick={(ev) => { ev.stopPropagation(); setSelectedId(r.id); }}
                          >
                            详情
                          </button>
                          <button
                            className="text-xs hover:underline ml-3"
                            style={{ color: 'var(--danger)' }}
                            onClick={(ev) => { ev.stopPropagation(); handleRecall(r.id); }}
                          >
                            召回
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {/* 分页 */}
            <div className="px-4 py-3 border-t flex items-center justify-between" style={{ borderColor: 'var(--border-subtle)' }}>
              <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>第 {page} / {totalPages} 页 · 共 {total} 条</span>
              <div className="flex items-center gap-1.5">
                <button className="btn-ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>‹</button>
                <span className="text-xs px-2">{page}</span>
                <button className="btn-ghost" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>›</button>
              </div>
            </div>
          </div>

          {/* 详情面板 */}
          <RobotDetailPanel detail={detail} onRecall={handleRecall} onQuickEdit={handleQuickEdit} />
        </div>
      </div>
    </AppShell>
  );
}

function StatCard({
  icon, label, value, color, bg,
}: { icon: React.ReactNode; label: string; value: number; color: string; bg: string }) {
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

function RobotDetailPanel({ detail, onRecall, onQuickEdit }: { detail: RobotDetailRead | null; onRecall: (id: string) => void; onQuickEdit: (r: RobotRead) => void }) {
  if (!detail) {
    return (
      <div className="panel p-6 text-sm text-center" style={{ color: 'var(--text-tertiary)' }}>
        从左侧列表选择机器人查看详情
      </div>
    );
  }
  const s = detail.latest_state;
  const fsm = s?.fsm_state ?? 'IDLE';
  const fsmStyle = FSM_BADGE[fsm];
  const battery = s?.battery ?? 0;
  return (
    <div className="panel p-5 sticky top-5">
      <div className="flex justify-between items-start pb-3 mb-4 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
        <div>
          <div className="text-base font-semibold flex items-center gap-2">
            <TypeIcon type={detail.type} />
            {detail.name}
          </div>
          <div className="text-xs mono mt-1" style={{ color: 'var(--text-tertiary)' }}>{detail.code} · {detail.model ?? '—'}</div>
        </div>
        <span className="badge" style={{ background: fsmStyle.bg, color: fsmStyle.fg }}>● {fsm}</span>
      </div>

      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <span>电量</span>
          <span className="mono font-semibold" style={{ color: batteryColor(battery) }}>{battery.toFixed(1)}%</span>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${battery}%`, background: battery < 25 ? 'var(--danger)' : undefined }} />
        </div>
      </div>

      <Section title="基础信息">
        <Row label="编号" value={detail.code} mono />
        <Row label="类型" value={TYPE_LABEL[detail.type]} />
        <Row label="型号" value={detail.model ?? '—'} mono />
        <Row label="编队" value={detail.group_id?.slice(0, 8) ?? '未分配'} mono />
        <Row label="状态" value={detail.is_active ? '启用' : '禁用'} valueColor={detail.is_active ? 'var(--success)' : 'var(--text-tertiary)'} />
      </Section>

      <Section title="位置 / 任务">
        {s ? (
          <>
            <Row label="位置" value={`${s.position.lat.toFixed(4)}, ${s.position.lng.toFixed(4)}`} mono />
            {s.position.altitude_m != null && <Row label="高度" value={`${s.position.altitude_m} m`} mono />}
            <Row label="当前任务" value={s.current_task_id?.slice(0, 8) ?? '空闲'} mono />
            <Row label="最后上报" value={new Date(s.recorded_at).toLocaleString('zh-CN', { hour12: false })} />
          </>
        ) : (
          <Row label="状态" value="尚未上报" />
        )}
      </Section>

      <Section title="能力清单">
        <Row label="传感器" value={detail.capability.sensors.join(', ') || '—'} />
        <Row label="负载" value={detail.capability.payloads.join(', ') || '—'} />
        <Row label="最大速度" value={`${detail.capability.max_speed_mps} m/s`} mono />
        <Row label="最大续航" value={`${detail.capability.max_battery_min} 分钟`} mono />
        <Row label="最大航程" value={`${detail.capability.max_range_km} km`} mono />
        <Row label="YOLO" value={detail.capability.has_yolo ? '✓ 已启用' : '— 未启用'} valueColor={detail.capability.has_yolo ? 'var(--success)' : 'var(--text-tertiary)'} />
      </Section>

      <div className="grid grid-cols-2 gap-2 mt-4">
        <button
          className="btn-ghost flex items-center justify-center gap-1.5"
          style={{ padding: 10 }}
          onClick={() => onQuickEdit(detail)}
          title="快速重命名（完整能力编辑请前往 /admin → 机器人注册）"
        >
          重命名
        </button>
        <button
          className="flex items-center justify-center gap-1.5"
          style={{ padding: 10, background: 'var(--danger)', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
          onClick={() => onRecall(detail.id)}
        >
          <RotateCcw className="w-4 h-4" /> 紧急召回
        </button>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="text-[11px] uppercase tracking-wider mb-2" style={{ color: 'var(--text-tertiary)' }}>{title}</div>
      {children}
    </div>
  );
}

function Row({ label, value, valueColor, mono }: { label: string; value: string; valueColor?: string; mono?: boolean }) {
  return (
    <div className="flex justify-between items-center py-1.5 text-xs border-b last:border-b-0" style={{ borderColor: 'var(--border-subtle)' }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span className={mono ? 'mono' : ''} style={{ color: valueColor ?? 'var(--text-primary)', fontWeight: 500, textAlign: 'right', maxWidth: '65%', wordBreak: 'break-all' }}>
        {value}
      </span>
    </div>
  );
}
