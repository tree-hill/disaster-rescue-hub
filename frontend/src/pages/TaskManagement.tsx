/**
 * 任务管理（对照 docs/prototypes/prototype_08_task_management.html，按 01-06 风格统一）。
 *
 * 后端：
 * - GET /tasks（status/priority/type/search/page/page_size）
 * - POST /tasks 创建任务（→ 自动触发拍卖，由 P5.7 dispatch_trigger 监听 task.created）
 * - POST /tasks/{id}/cancel {reason}
 * - WS commander 房间订阅 task.created / task.cancelled / task.reassigned
 *
 * 占位：
 * - 「立即拍卖」按钮 → 暂用 alert（实际任务 PENDING 30s 自动重扫，无需手动）
 * - 改派按钮 → P7.4 ReassignDialog
 * - 地图选区（创建表单）→ 当前用经纬度文本输入框替代真实地图绘制（react-konva 后续接入）
 */
import {
  CheckCircle2,
  Clock,
  Layers,
  MapPin,
  Plus,
  RefreshCw,
  Replace,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  cancelTask,
  createTask,
  getTaskDetail,
  listTasks,
  type TaskCreatePayload,
  type TaskDetailRead,
  type TaskRead,
  type TaskStatus,
  type TaskType,
} from '@/api/tasks';
import { getRobot, type RobotRead } from '@/api/robots';
import { AppShell } from '@/components/common/AppShell';
import { ReassignDialog } from '@/components/common/ReassignDialog';
import { useWSStore } from '@/store/ws';

type StatusTab = 'all' | 'PENDING' | 'EXECUTING' | 'COMPLETED' | 'failed';

const STATUS_FILTER: Record<StatusTab, TaskStatus[] | undefined> = {
  all: undefined,
  PENDING: ['PENDING'],
  EXECUTING: ['ASSIGNED', 'EXECUTING'],
  COMPLETED: ['COMPLETED'],
  failed: ['FAILED', 'CANCELLED'],
};

const STATUS_LABEL: Record<TaskStatus, { label: string; bg: string; fg: string }> = {
  PENDING:   { label: '○ 等待拍卖',  bg: 'rgba(245,158,11,0.15)', fg: 'var(--warning)' },
  ASSIGNED:  { label: '● 已分配',    bg: 'rgba(59,130,246,0.15)', fg: 'var(--accent-primary)' },
  EXECUTING: { label: '● EXECUTING', bg: 'rgba(6,182,212,0.15)',  fg: 'var(--info)' },
  COMPLETED: { label: '✓ COMPLETED', bg: 'rgba(16,185,129,0.15)', fg: 'var(--success)' },
  FAILED:    { label: '✕ 失败',      bg: 'rgba(239,68,68,0.15)',  fg: 'var(--danger)' },
  CANCELLED: { label: '— 已取消',    bg: 'rgba(92,101,128,0.15)', fg: 'var(--text-tertiary)' },
};

const PRIORITY_LABEL: Record<1 | 2 | 3, { label: string; bg: string; fg: string; side: string }> = {
  1: { label: '高', bg: 'rgba(239,68,68,0.15)',  fg: 'var(--danger)',         side: 'var(--danger)' },
  2: { label: '中', bg: 'rgba(245,158,11,0.15)', fg: 'var(--warning)',        side: 'var(--warning)' },
  3: { label: '低', bg: 'rgba(16,185,129,0.15)', fg: 'var(--success)',        side: 'var(--success)' },
};

const TYPE_LABEL: Record<TaskType, string> = {
  search_rescue: '搜救',
  recon: '侦察',
  transport: '物资运输',
  patrol: '巡逻',
};

function fmtAge(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

export function TaskManagement() {
  const [tab, setTab] = useState<StatusTab>('all');
  const [items, setItems] = useState<TaskRead[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [reassignTarget, setReassignTarget] = useState<TaskRead | null>(null);
  const [detailTarget, setDetailTarget] = useState<TaskRead | null>(null);

  const wsConnect = useWSStore((s) => s.connect);
  const wsSubscribe = useWSStore((s) => s.subscribe);
  const wsAddListener = useWSStore((s) => s.addListener);

  const refresh = useMemo(
    () => async () => {
      setLoading(true);
      try {
        const status = STATUS_FILTER[tab];
        const p = await listTasks({ status, page: 1, page_size: 20 });
        setItems(p.items);
        setTotal(p.total);
      } finally {
        setLoading(false);
      }
    },
    [tab],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    wsConnect();
    wsSubscribe('commander');
    const offs = [
      wsAddListener('task.created', () => refresh()),
      wsAddListener('task.cancelled', () => refresh()),
      wsAddListener('task.reassigned', () => refresh()),
      wsAddListener('auction.completed', () => refresh()),
    ];
    return () => offs.forEach((f) => f());
  }, [wsConnect, wsSubscribe, wsAddListener, refresh]);

  const counts = useMemo(() => {
    const all = total;
    const pending = items.filter((t) => t.status === 'PENDING').length;
    const exec = items.filter((t) => t.status === 'ASSIGNED' || t.status === 'EXECUTING').length;
    const done = items.filter((t) => t.status === 'COMPLETED').length;
    const fail = items.filter((t) => t.status === 'FAILED' || t.status === 'CANCELLED').length;
    return { all, pending, exec, done, fail };
  }, [items, total]);

  const handleCancel = async (t: TaskRead) => {
    const reason = window.prompt('取消任务原因（必填，至少 5 字）');
    if (!reason || reason.trim().length < 5) return;
    try {
      await cancelTask(t.id, reason);
      await refresh();
    } catch (e: unknown) {
      const m = (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? String(e);
      alert(`取消失败：${m}`);
    }
  };

  return (
    <AppShell>
      <div className="container mx-auto px-6 py-5">
        <div className="text-xs flex items-center gap-1.5 mb-4" style={{ color: 'var(--text-tertiary)' }}>
          <span>任务管理</span>
          <span>/</span>
          <span style={{ color: 'var(--text-secondary)' }}>任务列表</span>
        </div>

        <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 460px' }}>
          {/* 左：任务列表 */}
          <div>
            {/* Tabs */}
            <div className="panel p-1.5 flex gap-1 mb-4">
              {[
                { k: 'all' as const, label: `全部 ${counts.all}` },
                { k: 'PENDING' as const, label: `待分配 ${counts.pending}` },
                { k: 'EXECUTING' as const, label: `执行中 ${counts.exec}` },
                { k: 'COMPLETED' as const, label: `完成 ${counts.done}` },
                { k: 'failed' as const, label: `失败/取消 ${counts.fail}` },
              ].map((t) => (
                <button
                  key={t.k}
                  onClick={() => setTab(t.k)}
                  className="flex-1 py-2 px-4 text-sm rounded font-medium transition"
                  style={{
                    background: tab === t.k ? 'var(--accent-primary)' : 'transparent',
                    color: tab === t.k ? 'white' : 'var(--text-secondary)',
                  }}
                >
                  {t.label}
                </button>
              ))}
              <button className="btn-ghost ml-2" onClick={refresh}>
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* 任务卡列表 */}
            <div className="space-y-3">
              {loading && (
                <div className="panel p-6 text-center text-xs" style={{ color: 'var(--text-tertiary)' }}>加载中…</div>
              )}
              {!loading && items.length === 0 && (
                <div className="panel p-8 text-center text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  暂无任务 · 在右侧创建一条新任务即可触发拍卖
                </div>
              )}
              {items.map((t) => (
                <TaskCard
                  key={t.id}
                  task={t}
                  onCancel={() => handleCancel(t)}
                  onReassign={() => setReassignTarget(t)}
                  onDetail={() => setDetailTarget(t)}
                />
              ))}
            </div>
          </div>

          {/* 右：创建表单（粘性） */}
          <div className="sticky top-5 self-start">
            {showCreate ? (
              <CreateForm onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); refresh(); }} />
            ) : (
              <div className="panel p-5">
                <div className="flex items-center justify-between mb-3">
                  <div className="text-base font-semibold flex items-center gap-2">
                    <Plus className="w-4 h-4" style={{ color: 'var(--accent-primary)' }} />
                    创建新任务
                  </div>
                </div>
                <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>
                  填写任务信息,系统将自动触发拍卖分配（P5.7 dispatch_trigger 监听 task.created → start_auction）
                </p>
                <button className="btn-primary w-full flex items-center justify-center gap-2" onClick={() => setShowCreate(true)}>
                  <Plus className="w-4 h-4" /> 打开创建表单
                </button>
                <div className="mt-5 text-xs space-y-2" style={{ color: 'var(--text-tertiary)' }}>
                  <div className="flex items-center gap-1.5"><Layers className="w-3.5 h-3.5" /> 4 种类型: 搜救 / 侦察 / 物资运输 / 巡逻</div>
                  <div className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5" /> 3 档优先级: 高 / 中 / 低</div>
                  <div className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> 自动 SLA: 默认 30 分钟</div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <ReassignDialog
        open={reassignTarget !== null}
        task={reassignTarget}
        onClose={() => setReassignTarget(null)}
        onSuccess={() => refresh()}
      />

      {detailTarget && (
        <TaskDetailDialog task={detailTarget} onClose={() => setDetailTarget(null)} />
      )}
    </AppShell>
  );
}

function TaskDetailDialog({ task, onClose }: { task: TaskRead; onClose: () => void }) {
  const [detail, setDetail] = useState<TaskDetailRead | null>(null);
  const [robotMap, setRobotMap] = useState<Record<string, RobotRead>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getTaskDetail(task.id)
      .then(async (d) => {
        if (!alive) return;
        setDetail(d);
        const robotIds = Array.from(new Set(d.assignments.map((a) => a.robot_id)));
        const fetched = await Promise.all(
          robotIds.map((id) => getRobot(id).catch(() => null)),
        );
        if (!alive) return;
        const map: Record<string, RobotRead> = {};
        fetched.forEach((r, i) => {
          if (r) map[robotIds[i]] = r;
        });
        setRobotMap(map);
      })
      .catch(() => undefined)
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [task.id]);

  const cp = task.target_area.center_point;
  const status = STATUS_LABEL[task.status];
  const pri = PRIORITY_LABEL[task.priority];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(6px)' }}
      onClick={onClose}
    >
      <div
        className="rounded-xl overflow-hidden flex flex-col"
        style={{
          width: 720,
          maxWidth: '95vw',
          maxHeight: '90vh',
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-default)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 flex items-center justify-between border-b" style={{ borderColor: 'var(--border-subtle)' }}>
          <div>
            <div className="text-base font-bold flex items-center gap-2">
              {task.name}
              <span className={`badge ${pri.fg ? '' : ''}`} style={{ background: pri.bg, color: pri.fg }}>● {pri.label}</span>
              <span className="badge" style={{ background: status.bg, color: status.fg }}>{status.label}</span>
            </div>
            <div className="text-xs mono mt-1" style={{ color: 'var(--text-tertiary)' }}>{task.code}</div>
          </div>
          <button className="btn-icon" onClick={onClose}><X className="w-5 h-5" /></button>
        </div>

        <div className="px-6 py-4 overflow-y-auto scroll-thin" style={{ flex: 1 }}>
          <Section title="基础信息">
            <DetailRow label="任务编号" value={task.code} mono />
            <DetailRow label="类型" value={TYPE_LABEL[task.type]} />
            <DetailRow label="优先级" value={`${pri.label} (${task.priority})`} />
            <DetailRow label="状态" value={task.status} mono />
            <DetailRow label="进度" value={`${Number(task.progress).toFixed(0)}%`} />
            <DetailRow label="创建时间" value={new Date(task.created_at).toLocaleString('zh-CN', { hour12: false })} />
            <DetailRow label="开始时间" value={task.started_at ? new Date(task.started_at).toLocaleString('zh-CN', { hour12: false }) : '—'} />
            <DetailRow label="完成时间" value={task.completed_at ? new Date(task.completed_at).toLocaleString('zh-CN', { hour12: false }) : '—'} />
            <DetailRow label="SLA 截止" value={task.sla_deadline ? new Date(task.sla_deadline).toLocaleString('zh-CN', { hour12: false }) : '无 SLA'} />
          </Section>

          <Section title="目标区域">
            <DetailRow label="形状" value={task.target_area.type} />
            <DetailRow label="中心点" value={`${cp.lat.toFixed(4)}, ${cp.lng.toFixed(4)}`} mono />
            <DetailRow label="面积" value={`${task.target_area.area_km2.toFixed(3)} km²`} />
            {task.target_area.radius_m && (
              <DetailRow label="半径" value={`${task.target_area.radius_m} m`} />
            )}
          </Section>

          <Section title="所需能力">
            <DetailRow label="传感器" value={task.required_capabilities.sensors.join(', ') || '—'} />
            <DetailRow label="负载" value={task.required_capabilities.payloads.join(', ') || '—'} />
            <DetailRow label="最低电量" value={`${task.required_capabilities.min_battery_pct}%`} />
            {task.required_capabilities.robot_type && (
              <DetailRow label="机器人类型" value={task.required_capabilities.robot_type.join(', ')} />
            )}
          </Section>

          <Section title="分配历史">
            {loading && <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>加载中…</div>}
            {!loading && (!detail || detail.assignments.length === 0) && (
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>暂无分配记录</div>
            )}
            {!loading && detail?.assignments.map((a) => {
              const r = robotMap[a.robot_id];
              return (
                <div
                  key={a.id}
                  className="rounded p-2.5 mb-2 text-xs flex items-center justify-between"
                  style={{
                    background: 'var(--bg-tertiary)',
                    borderLeft: `3px solid ${a.is_active ? 'var(--success)' : 'var(--text-tertiary)'}`,
                  }}
                >
                  <div>
                    <div className="mono font-semibold">{r?.code ?? a.robot_id.slice(0, 8)}</div>
                    <div style={{ color: 'var(--text-tertiary)' }} className="mt-0.5">
                      分配于 {new Date(a.assigned_at).toLocaleString('zh-CN', { hour12: false })}
                      {a.released_at && ` · 释放 ${new Date(a.released_at).toLocaleString('zh-CN', { hour12: false })}`}
                    </div>
                  </div>
                  <span className={`badge ${a.is_active ? 'badge-success' : ''}`} style={!a.is_active ? { background: 'var(--bg-secondary)', color: 'var(--text-tertiary)' } : undefined}>
                    {a.is_active ? '生效中' : '已释放'}
                  </span>
                </div>
              );
            })}
          </Section>
        </div>

        <div className="px-6 py-3 border-t flex justify-end" style={{ borderColor: 'var(--border-subtle)' }}>
          <button className="btn-ghost" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <div className="text-[11px] uppercase tracking-wider mb-2" style={{ color: 'var(--text-tertiary)' }}>{title}</div>
      {children}
    </div>
  );
}

function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between items-center py-1.5 text-xs border-b last:border-b-0" style={{ borderColor: 'var(--border-subtle)' }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span className={mono ? 'mono' : ''} style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
        {value}
      </span>
    </div>
  );
}

function TaskCard({ task, onCancel, onReassign, onDetail }: { task: TaskRead; onCancel: () => void; onReassign: () => void; onDetail: () => void }) {
  const pri = PRIORITY_LABEL[task.priority];
  const st = STATUS_LABEL[task.status];
  const completed = task.status === 'COMPLETED';
  const dim = task.status === 'CANCELLED' || task.status === 'FAILED';
  const cp = task.target_area.center_point;
  return (
    <div
      className="panel p-4 transition hover:opacity-95"
      style={{
        borderLeft: `4px solid ${pri.side}`,
        opacity: dim ? 0.65 : 1,
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-base font-semibold mb-1">{task.name}</div>
          <div className="text-xs mono" style={{ color: 'var(--text-tertiary)' }}>
            {task.code} · {fmtAge(task.created_at)}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge" style={{ background: pri.bg, color: pri.fg }}>● {pri.label}</span>
          <span className="badge" style={{ background: st.bg, color: st.fg }}>{st.label}</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>
        <div className="flex items-center gap-1.5">
          <MapPin className="w-3.5 h-3.5" />
          <span className="mono" title={`${cp.lat}, ${cp.lng}`}>
            {cp.lat.toFixed(3)}, {cp.lng.toFixed(3)}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5" />
          <span>{TYPE_LABEL[task.type]} · {task.target_area.area_km2.toFixed(2)} km²</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" />
          <span>{task.sla_deadline ? `SLA ${new Date(task.sla_deadline).toLocaleString('zh-CN', { hour12: false }).slice(5, 16)}` : '无 SLA'}</span>
        </div>
      </div>

      <div className="flex items-center gap-3 mb-3">
        <div className="flex-1 progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${task.progress}%`, background: completed ? 'var(--success)' : undefined }}
          />
        </div>
        <span className="text-xs mono font-semibold">{Number(task.progress).toFixed(0)}%</span>
      </div>

      <div className="flex items-center justify-end gap-3 pt-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
        <button className="text-xs hover:underline" style={{ color: 'var(--accent-primary)' }} onClick={onDetail}>
          查看详情
        </button>
        {(task.status === 'EXECUTING' || task.status === 'ASSIGNED') && (
          <button className="text-xs hover:underline flex items-center gap-1" style={{ color: 'var(--warning)' }} onClick={onReassign}>
            <Replace className="w-3 h-3" /> 改派
          </button>
        )}
        {!['COMPLETED', 'CANCELLED', 'FAILED'].includes(task.status) && (
          <button className="text-xs hover:underline flex items-center gap-1" style={{ color: 'var(--danger)' }} onClick={onCancel}>
            <X className="w-3 h-3" /> 取消
          </button>
        )}
      </div>
    </div>
  );
}

function CreateForm({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('');
  const [type, setType] = useState<TaskType>('search_rescue');
  const [priority, setPriority] = useState<1 | 2 | 3>(2);
  const [centerLat, setCenterLat] = useState(30.225);
  const [centerLng, setCenterLng] = useState(120.525);
  const [radiusM, setRadiusM] = useState(300);
  const [sensors, setSensors] = useState<string[]>([]);
  const [payloads, setPayloads] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleSensor = (s: string) => {
    setSensors((prev) => prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]);
  };
  const togglePayload = (p: string) => {
    setPayloads((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const r = radiusM;
      const areaKm2 = +((Math.PI * (r / 1000) ** 2).toFixed(3));
      const payload: TaskCreatePayload = {
        name: name.trim() || '未命名任务',
        type,
        priority,
        target_area: {
          type: 'circle',
          center: { lat: centerLat, lng: centerLng },
          radius_m: r,
          area_km2: Math.max(0.001, areaKm2),
          center_point: { lat: centerLat, lng: centerLng },
        },
        required_capabilities: {
          sensors,
          payloads,
          min_battery_pct: 20,
        },
      };
      await createTask(payload);
      onCreated();
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { message?: string } } })?.response?.data?.message ?? String(err);
      setError(m);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="panel p-5" onSubmit={handleSubmit}>
      <div className="flex items-center justify-between mb-4">
        <div className="text-base font-semibold flex items-center gap-2">
          <Plus className="w-4 h-4" style={{ color: 'var(--accent-primary)' }} /> 创建新任务
        </div>
        <button type="button" className="btn-icon" onClick={onClose}>
          <X className="w-4 h-4" />
        </button>
      </div>
      <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>
        创建后系统将自动触发拍卖（P5.7 dispatch_trigger）
      </p>

      <Field label="任务名称" required>
        <input
          className="input-field"
          placeholder="例如:搜救任务 - 废墟 E 区"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </Field>

      <Field label="任务类型" required>
        <div className="grid grid-cols-2 gap-2">
          {(['search_rescue', 'recon', 'transport', 'patrol'] as TaskType[]).map((tp) => (
            <RadioBtn key={tp} selected={type === tp} onClick={() => setType(tp)} label={TYPE_LABEL[tp]} />
          ))}
        </div>
      </Field>

      <Field label="优先级" required>
        <div className="grid grid-cols-3 gap-2">
          {([1, 2, 3] as const).map((p) => (
            <RadioBtn key={p} selected={priority === p} onClick={() => setPriority(p)} label={`${PRIORITY_LABEL[p].label} (${p})`} />
          ))}
        </div>
      </Field>

      <Field label="目标区域 (圆心 + 半径)" required>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <input
            type="number"
            step="0.0001"
            className="input-field"
            placeholder="纬度"
            value={centerLat}
            onChange={(e) => setCenterLat(parseFloat(e.target.value) || 0)}
          />
          <input
            type="number"
            step="0.0001"
            className="input-field"
            placeholder="经度"
            value={centerLng}
            onChange={(e) => setCenterLng(parseFloat(e.target.value) || 0)}
          />
        </div>
        <input
          type="number"
          step="50"
          min={50}
          max={5000}
          className="input-field"
          placeholder="半径 (m)"
          value={radiusM}
          onChange={(e) => setRadiusM(parseInt(e.target.value) || 100)}
        />
        <div className="text-[11px] mt-1.5" style={{ color: 'var(--text-tertiary)' }}>
          中心 ({centerLat.toFixed(4)}, {centerLng.toFixed(4)}) · 半径 {radiusM} m · 面积 ≈ {(Math.PI * (radiusM / 1000) ** 2).toFixed(3)} km²
        </div>
      </Field>

      <Field label="所需传感器 (多选，不选则不限)">
        <div className="flex flex-wrap gap-2">
          {['camera_4k', 'thermal', 'camera', 'lidar', 'sonar'].map((s) => {
            const sel = sensors.includes(s);
            return (
              <span
                key={s}
                onClick={() => toggleSensor(s)}
                className="px-3 py-1.5 rounded text-xs cursor-pointer transition"
                style={{
                  background: sel ? 'rgba(59,130,246,0.15)' : 'var(--bg-tertiary)',
                  border: `1px solid ${sel ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                  color: sel ? 'var(--accent-primary)' : 'var(--text-secondary)',
                }}
              >
                {s}
              </span>
            );
          })}
        </div>
        <div className="text-[11px] mt-1.5" style={{ color: 'var(--text-tertiary)' }}>
          UAV: camera_4k, thermal &nbsp;|&nbsp; UGV: camera, lidar &nbsp;|&nbsp; USV: camera, sonar
        </div>
      </Field>

      <Field label="所需负载 (多选，不选则不限)">
        <div className="flex flex-wrap gap-2">
          {['rescue_kit', 'winch'].map((p) => {
            const sel = payloads.includes(p);
            return (
              <span
                key={p}
                onClick={() => togglePayload(p)}
                className="px-3 py-1.5 rounded text-xs cursor-pointer transition"
                style={{
                  background: sel ? 'rgba(16,185,129,0.15)' : 'var(--bg-tertiary)',
                  border: `1px solid ${sel ? 'var(--success)' : 'var(--border-default)'}`,
                  color: sel ? 'var(--success)' : 'var(--text-secondary)',
                }}
              >
                {p}
              </span>
            );
          })}
        </div>
        <div className="text-[11px] mt-1.5" style={{ color: 'var(--text-tertiary)' }}>
          UGV 携带: rescue_kit, winch
        </div>
      </Field>

      {error && (
        <div className="mb-3 px-3 py-2 rounded text-xs"
          style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: 'var(--danger)' }}
        >
          {error}
        </div>
      )}

      <div className="flex gap-2 mt-4">
        <button type="button" className="btn-ghost flex-1" onClick={onClose}>取消</button>
        <button
          type="submit"
          disabled={submitting}
          className="btn-primary flex-1 flex items-center justify-center gap-1"
          style={{ opacity: submitting ? 0.6 : 1 }}
        >
          {submitting ? '创建中…' : '创建并触发拍卖 →'}
        </button>
      </div>
    </form>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <label className="text-xs font-semibold mb-2 block" style={{ color: 'var(--text-secondary)' }}>
        {label} {required && <span style={{ color: 'var(--danger)' }}>*</span>}
      </label>
      {children}
    </div>
  );
}

function RadioBtn({ selected, onClick, label }: { selected: boolean; onClick: () => void; label: string }) {
  return (
    <div
      onClick={onClick}
      className="px-3 py-2.5 rounded text-sm cursor-pointer transition"
      style={{
        background: selected ? 'rgba(59,130,246,0.1)' : 'var(--bg-tertiary)',
        border: `1px solid ${selected ? 'var(--accent-primary)' : 'var(--border-default)'}`,
        color: selected ? 'var(--accent-primary)' : 'var(--text-primary)',
        textAlign: 'center',
        fontWeight: selected ? 600 : 400,
      }}
    >
      {selected ? '●' : '○'} {label}
    </div>
  );
}
