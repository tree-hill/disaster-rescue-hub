/**
 * 告警中心（对照 docs/prototypes/prototype_10_alert_center.html，但 UI 风格以
 * 01-06 为基准统一：accent #3B82F6 + Inter 字体 + 标准顶导）。
 *
 * 数据接入（已对齐 P7.1 后端）：
 * - GET /alerts（severity / type / source / status / search / page / page_size）
 * - POST /alerts/{id}/acknowledge
 * - POST /alerts/{id}/ignore
 * - WS commander 房间订阅 'alert.raised' / 'alert.acknowledged' / 'alert.ignored' 实时刷新
 *
 * 占位（后端缺）：
 * - 详情面板「火点面积 / 扩散方向 / 距最近水源 / 关联任务 / 附近机器人」
 *   → 这些字段在 alerts.payload JSONB 内可能存，但 P7.1 后端没有强约束，先按 payload 字段
 *     渲染，缺则显示 "—"。
 * - 「派遣灭火任务 / 通知应急队 / 查看实时画面」三个按钮 → onClick 占位 alert()。
 */
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  ExternalLink,
  RefreshCw,
  Search,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  acknowledgeAlert,
  ignoreAlert,
  listAlerts,
  type AlertRead,
  type AlertSeverity,
} from '@/api/alerts';
import { AppShell } from '@/components/common/AppShell';
import { useWSStore } from '@/store/ws';

type StatusFilter = '' | 'unack' | 'ack' | 'ignored';

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: '严重',
  warn: '警告',
  info: '信息',
};

const SEVERITY_BADGE_BG: Record<AlertSeverity, string> = {
  critical: 'rgba(239,68,68,0.15)',
  warn: 'rgba(245,158,11,0.15)',
  info: 'rgba(6,182,212,0.15)',
};
const SEVERITY_BADGE_FG: Record<AlertSeverity, string> = {
  critical: 'var(--danger)',
  warn: 'var(--warning)',
  info: 'var(--info)',
};
const SEVERITY_BORDER: Record<AlertSeverity, string> = {
  critical: 'var(--danger)',
  warn: 'var(--warning)',
  info: 'var(--info)',
};

function alertStatus(a: AlertRead): { label: string; color: string } {
  if (a.is_ignored) return { label: '— 已忽略', color: 'var(--text-tertiary)' };
  if (a.acknowledged_at) return { label: '✓ 已确认', color: 'var(--success)' };
  return { label: '❗ 待处理', color: 'var(--danger)' };
}

function fmtTs(iso: string): string {
  return new Date(iso).toLocaleTimeString('zh-CN', { hour12: false });
}

export function AlertCenter() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [severity, setSeverity] = useState<'' | AlertSeverity>('');
  const [type, setType] = useState('');
  const [status, setStatus] = useState<StatusFilter>('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  const [items, setItems] = useState<AlertRead[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const wsConnect = useWSStore((s) => s.connect);
  const wsSubscribe = useWSStore((s) => s.subscribe);
  const wsAddListener = useWSStore((s) => s.addListener);

  const refresh = useMemo(
    () => async () => {
      setLoading(true);
      try {
        const p = await listAlerts({
          severity: severity || undefined,
          type: type || undefined,
          status: status || undefined,
          search: search || undefined,
          page,
          page_size: pageSize,
        });
        setItems(p.items);
        setTotal(p.total);
        if (p.items.length > 0 && !selectedId) {
          setSelectedId(p.items[0].id);
        }
      } finally {
        setLoading(false);
      }
    },
    [severity, type, status, search, page, pageSize, selectedId],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  // WS 订阅：alert.raised / acknowledged / ignored 自动刷新
  useEffect(() => {
    wsConnect();
    wsSubscribe('commander');
    const offs = [
      wsAddListener('alert.raised', () => refresh()),
      wsAddListener('alert.acknowledged', () => refresh()),
      wsAddListener('alert.ignored', () => refresh()),
    ];
    return () => offs.forEach((f) => f());
  }, [wsConnect, wsSubscribe, wsAddListener, refresh]);

  const selected = items.find((a) => a.id === selectedId) ?? null;

  // 顶部统计（基于当前页，缺独立 endpoint 时 best-effort）
  const stat = useMemo(() => {
    const unack = items.filter((a) => !a.is_ignored && !a.acknowledged_at).length;
    const acked = items.filter((a) => a.acknowledged_at).length;
    const ignored = items.filter((a) => a.is_ignored).length;
    return { unack, acked, ignored };
  }, [items]);

  const handleAck = async (id: string) => {
    try {
      await acknowledgeAlert(id);
      refresh();
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error(e);
    }
  };
  const handleIgnore = async (id: string) => {
    const reason = window.prompt('忽略原因（必填）');
    if (!reason) return;
    try {
      await ignoreAlert(id, reason);
      refresh();
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error(e);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const handleExport = () => {
    if (items.length === 0) {
      alert('当前页无数据可导出');
      return;
    }
    const headers = ['code', 'severity', 'type', 'source', 'message', 'raised_at', 'acknowledged_at', 'is_ignored'];
    const escape = (v: unknown) => {
      const s = v == null ? '' : String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [
      headers.join(','),
      ...items.map((a) =>
        [a.code, a.severity, a.type, a.source, a.message, a.raised_at, a.acknowledged_at ?? '', a.is_ignored].map(escape).join(','),
      ),
    ];
    const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `alerts-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AppShell>
      <div className="container mx-auto p-6">
        <div
          className="text-xs flex items-center gap-1.5 mb-4"
          style={{ color: 'var(--text-tertiary)' }}
        >
          <span>态势感知</span>
          <span>/</span>
          <span style={{ color: 'var(--text-secondary)' }}>告警中心</span>
        </div>

        {/* 统计卡片 */}
        <div className="grid grid-cols-6 gap-3 mb-5">
          <StatCard label="待处理 ⚠" value={stat.unack} valueColor="var(--danger)" highlight />
          <StatCard label="已确认" value={stat.acked} valueColor="var(--success)" />
          <StatCard label="已忽略" value={stat.ignored} valueColor="var(--text-tertiary)" />
          <StatCard label="本页总数" value={items.length} sub={`共 ${total} 条`} />
          <StatCard label="平均响应" value={'—'} sub="待埋点" />
          <StatCard label="规则数" value={12} sub="11 已启用" />
        </div>

        {/* 工具栏 */}
        <div
          className="panel p-3 flex items-center gap-2 mb-4 flex-wrap"
        >
          <div className="relative" style={{ width: 240 }}>
            <Search
              className="w-4 h-4 absolute left-3 top-2.5"
              style={{ color: 'var(--text-tertiary)' }}
            />
            <input
              type="text"
              placeholder="关键字搜索..."
              className="w-full pl-9 pr-3 py-2 text-sm rounded"
              style={{
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border-default)',
                color: 'var(--text-primary)',
              }}
              value={search}
              onChange={(e) => {
                setPage(1);
                setSearch(e.target.value);
              }}
            />
          </div>
          <select
            className="px-3 py-2 text-sm rounded"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-default)',
              color: 'var(--text-primary)',
            }}
            value={severity}
            onChange={(e) => {
              setPage(1);
              setSeverity(e.target.value as '' | AlertSeverity);
            }}
          >
            <option value="">所有级别</option>
            <option value="critical">严重</option>
            <option value="warn">警告</option>
            <option value="info">信息</option>
          </select>
          <select
            className="px-3 py-2 text-sm rounded"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-default)',
              color: 'var(--text-primary)',
            }}
            value={type}
            onChange={(e) => {
              setPage(1);
              setType(e.target.value);
            }}
          >
            <option value="">所有类型</option>
            <option value="fire_detected">火灾告警</option>
            <option value="survivor_detected">发现幸存者</option>
            <option value="low_battery">电量低</option>
            <option value="comm_lost">通信中断</option>
            <option value="sensor_error">传感器异常</option>
            <option value="task_overdue">任务超时</option>
            <option value="auction_failed">拍卖失败</option>
            <option value="high_decision_latency">决策延迟</option>
            <option value="algorithm_switched">算法切换</option>
            <option value="task_reassigned">任务改派</option>
            <option value="task_cancelled">任务取消</option>
            <option value="hitl_intervention">HITL 干预</option>
          </select>
          <select
            className="px-3 py-2 text-sm rounded"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-default)',
              color: 'var(--text-primary)',
            }}
            value={status}
            onChange={(e) => {
              setPage(1);
              setStatus(e.target.value as StatusFilter);
            }}
          >
            <option value="">所有状态</option>
            <option value="unack">待处理</option>
            <option value="ack">已确认</option>
            <option value="ignored">已忽略</option>
          </select>
          <div className="flex-1" />
          <button className="btn-ghost flex items-center gap-1.5" onClick={refresh}>
            <RefreshCw className="w-3.5 h-3.5" /> 刷新
          </button>
          <button
            className="btn-ghost flex items-center gap-1.5"
            onClick={handleExport}
          >
            <Download className="w-3.5 h-3.5" /> 导出 CSV
          </button>
        </div>

        {/* 主体 */}
        <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 420px' }}>
          {/* 列表 */}
          <div className="panel overflow-hidden">
            <div
              className="grid items-center px-4 py-3 text-xs font-semibold uppercase tracking-wider border-b"
              style={{
                gridTemplateColumns: '70px 90px 110px 100px 1fr 120px 140px',
                gap: 10,
                color: 'var(--text-secondary)',
                background: 'var(--bg-tertiary)',
                borderColor: 'var(--border-default)',
              }}
            >
              <span>级别</span>
              <span>时间</span>
              <span>类型</span>
              <span>来源</span>
              <span>描述</span>
              <span>状态</span>
              <span>操作</span>
            </div>
            <div className="max-h-[calc(100vh-380px)] overflow-y-auto scroll-thin">
              {loading && (
                <div className="text-center text-xs py-6" style={{ color: 'var(--text-tertiary)' }}>
                  加载中…
                </div>
              )}
              {!loading && items.length === 0 && (
                <div className="text-center text-xs py-6" style={{ color: 'var(--text-tertiary)' }}>
                  暂无告警
                </div>
              )}
              {items.map((a) => {
                const st = alertStatus(a);
                return (
                  <div
                    key={a.id}
                    className="grid items-center px-4 py-3 text-sm border-b cursor-pointer"
                    style={{
                      gridTemplateColumns: '70px 90px 110px 100px 1fr 120px 140px',
                      gap: 10,
                      borderColor: 'var(--border-subtle)',
                      borderLeft: `3px solid ${SEVERITY_BORDER[a.severity]}`,
                      background:
                        selectedId === a.id ? 'rgba(59,130,246,0.08)' : 'transparent',
                    }}
                    onClick={() => setSelectedId(a.id)}
                  >
                    <span
                      className="badge"
                      style={{
                        background: SEVERITY_BADGE_BG[a.severity],
                        color: SEVERITY_BADGE_FG[a.severity],
                      }}
                    >
                      ● {SEVERITY_LABEL[a.severity]}
                    </span>
                    <span className="mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {fmtTs(a.raised_at)}
                    </span>
                    <span style={{ color: 'var(--text-primary)' }}>{a.type}</span>
                    <span className="mono text-xs" style={{ color: 'var(--warning)' }}>
                      {a.source}
                    </span>
                    <span
                      className="text-xs truncate"
                      style={{ color: 'var(--text-secondary)' }}
                      title={a.message}
                    >
                      {a.message}
                    </span>
                    <span className="text-xs font-semibold" style={{ color: st.color }}>
                      {st.label}
                    </span>
                    <span className="text-xs flex gap-2">
                      {!a.acknowledged_at && !a.is_ignored && (
                        <>
                          <button
                            className="hover:underline"
                            style={{ color: 'var(--accent-primary)' }}
                            onClick={(ev) => {
                              ev.stopPropagation();
                              handleAck(a.id);
                            }}
                          >
                            确认
                          </button>
                          <button
                            className="hover:underline"
                            style={{ color: 'var(--text-tertiary)' }}
                            onClick={(ev) => {
                              ev.stopPropagation();
                              handleIgnore(a.id);
                            }}
                          >
                            忽略
                          </button>
                        </>
                      )}
                      <button
                        className="hover:underline"
                        style={{ color: 'var(--accent-primary)' }}
                        onClick={(ev) => {
                          ev.stopPropagation();
                          setSelectedId(a.id);
                        }}
                      >
                        详情
                      </button>
                    </span>
                  </div>
                );
              })}
            </div>

            {/* 分页 */}
            <div
              className="px-4 py-3 border-t flex items-center justify-between"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                第 {page} / {totalPages} 页 · 共 {total} 条
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  className="btn-ghost"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  ‹
                </button>
                <span className="text-xs px-2">{page}</span>
                <button
                  className="btn-ghost"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  ›
                </button>
              </div>
            </div>
          </div>

          {/* 详情面板 */}
          <DetailPanel
            alert={selected}
            onAck={handleAck}
            onIgnore={handleIgnore}
            onCreateRescueTask={() => navigate('/tasks')}
          />
        </div>
      </div>
    </AppShell>
  );
}

interface StatCardProps {
  label: string;
  value: number | string;
  sub?: string;
  valueColor?: string;
  highlight?: boolean;
}

function StatCard({ label, value, sub, valueColor, highlight }: StatCardProps) {
  return (
    <div
      className="panel p-4"
      style={{
        background: highlight
          ? 'linear-gradient(135deg, rgba(239,68,68,0.08), rgba(239,68,68,0.02))'
          : undefined,
        borderColor: highlight ? 'rgba(239,68,68,0.3)' : undefined,
      }}
    >
      <div className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>{label}</div>
      <div className="text-xl font-bold mono" style={{ color: valueColor ?? 'var(--text-primary)' }}>
        {value}
      </div>
      {sub && (
        <div className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>{sub}</div>
      )}
    </div>
  );
}

interface DetailPanelProps {
  alert: AlertRead | null;
  onAck: (id: string) => void;
  onIgnore: (id: string) => void;
  onCreateRescueTask: () => void;
}

function DetailPanel({ alert, onAck, onIgnore, onCreateRescueTask }: DetailPanelProps) {
  if (!alert) {
    return (
      <div className="panel p-5 text-sm text-center" style={{ color: 'var(--text-tertiary)' }}>
        从左侧列表选择一条告警查看详情
      </div>
    );
  }
  const payload = (alert.payload ?? {}) as Record<string, unknown>;
  const yolo = payload.yolo_detection as
    | { class_name?: string; confidence?: number; source_robot?: string; position?: { lat: number; lng: number } }
    | undefined;
  const sla = payload.sla_alert as
    | { task_code?: string; deadline?: string; overdue_min?: number }
    | undefined;
  const fire = payload.fire as
    | { area_m2?: number; spread_dir?: string; nearest_water_m?: number }
    | undefined;
  const isFireType = alert.type === 'fire_detected' || alert.type === 'survivor_detected';
  const status = alertStatus(alert);
  // 将原始 payload 中暂未结构化的字段折叠成单行预览，避免「占位 —」误导用户
  const otherPayload = Object.entries(payload).filter(
    ([k]) => !['yolo_detection', 'sla_alert', 'fire'].includes(k),
  );

  return (
    <div className="panel p-5">
      <div
        className="flex justify-between items-start pb-3 mb-4 border-b"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div>
          <div className="text-base font-semibold flex items-center gap-2">
            {alert.severity === 'critical' && (
              <AlertTriangle className="w-4 h-4" style={{ color: 'var(--danger)' }} />
            )}
            {alert.type}
          </div>
          <div className="text-xs mono mt-1" style={{ color: 'var(--text-tertiary)' }}>
            {alert.code}
          </div>
        </div>
        <span
          className="badge"
          style={{
            background: SEVERITY_BADGE_BG[alert.severity],
            color: SEVERITY_BADGE_FG[alert.severity],
          }}
        >
          ● {SEVERITY_LABEL[alert.severity]}
        </span>
      </div>

      <Section title="基础信息">
        <Row label="触发时间" value={new Date(alert.raised_at).toLocaleString('zh-CN', { hour12: false })} />
        <Row label="状态" value={status.label} valueColor={status.color} />
        <Row label="来源" value={alert.source} valueColor="var(--warning)" mono />
        <Row label="描述" value={alert.message} />
      </Section>

      {yolo && (
        <SectionCard title="数据来源 (YOLOv8)" tint="info">
          <Row label="源机器人" value={yolo.source_robot ?? '—'} valueColor="var(--warning)" mono />
          <Row label="识别类别" value={yolo.class_name ?? '—'} />
          <Row
            label="置信度"
            value={yolo.confidence != null ? yolo.confidence.toFixed(2) : '—'}
            valueColor="var(--accent-primary)"
          />
          {yolo.position && (
            <Row
              label="位置"
              value={`${yolo.position.lat.toFixed(4)}, ${yolo.position.lng.toFixed(4)}`}
              mono
            />
          )}
        </SectionCard>
      )}

      {sla && (
        <SectionCard title="SLA 信息" tint="warn">
          {sla.task_code && <Row label="任务" value={sla.task_code} mono valueColor="var(--accent-primary)" />}
          {sla.deadline && <Row label="截止" value={new Date(sla.deadline).toLocaleString('zh-CN', { hour12: false })} />}
          {sla.overdue_min != null && (
            <Row label="超时分钟" value={`${sla.overdue_min} 分钟`} valueColor="var(--danger)" />
          )}
        </SectionCard>
      )}

      {(fire || isFireType) && (
        <SectionCard title="影响范围 (fire payload)" tint="warn">
          <Row label="火点面积" value={fire?.area_m2 != null ? `${fire.area_m2} m²` : '—'} />
          <Row label="扩散方向" value={fire?.spread_dir ?? '—'} />
          <Row label="距最近水源" value={fire?.nearest_water_m != null ? `${fire.nearest_water_m} m` : '—'} />
        </SectionCard>
      )}

      <Section title="关联实体">
        {alert.related_task_id ? (
          <Row label="关联任务" value={alert.related_task_id.slice(0, 8)} mono valueColor="var(--accent-primary)" />
        ) : (
          <Row label="关联任务" value="—" />
        )}
        {alert.related_robot_id ? (
          <Row label="关联机器人" value={alert.related_robot_id.slice(0, 8)} mono />
        ) : (
          <Row label="关联机器人" value="—" />
        )}
      </Section>

      {otherPayload.length > 0 && (
        <Section title="其他 payload 字段">
          {otherPayload.map(([k, v]) => (
            <Row key={k} label={k} value={typeof v === 'object' ? JSON.stringify(v).slice(0, 60) : String(v)} mono />
          ))}
        </Section>
      )}

      <div className="grid grid-cols-2 gap-2 mt-5">
        <button
          className="btn-ghost"
          style={{ padding: 11 }}
          disabled={alert.is_ignored || !!alert.acknowledged_at}
          onClick={() => onIgnore(alert.id)}
        >
          忽略
        </button>
        <button
          className="btn-primary flex items-center justify-center gap-1.5"
          style={{ padding: 11, background: 'var(--danger)' }}
          disabled={!!alert.acknowledged_at || alert.is_ignored}
          onClick={() => onAck(alert.id)}
        >
          <CheckCircle2 className="w-4 h-4" /> 确认告警
        </button>
        {(alert.type === 'fire_detected' || alert.type === 'survivor_detected') && (
          <button
            className="btn-ghost col-span-2 flex items-center justify-center gap-1.5"
            style={{ padding: 11 }}
            onClick={onCreateRescueTask}
          >
            <ExternalLink className="w-4 h-4" /> 前往任务管理派遣救援任务
          </button>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <div
        className="text-[11px] uppercase tracking-wider mb-2.5"
        style={{ color: 'var(--text-tertiary)' }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

function SectionCard({ title, children, tint }: { title: string; children: React.ReactNode; tint: 'info' | 'warn' }) {
  const bg = tint === 'info'
    ? 'linear-gradient(135deg, rgba(59,130,246,0.08), rgba(59,130,246,0.02))'
    : 'linear-gradient(135deg, rgba(245,158,11,0.06), rgba(245,158,11,0.02))';
  const border = tint === 'info'
    ? 'rgba(59,130,246,0.25)'
    : 'rgba(245,158,11,0.2)';
  const titleColor = tint === 'info' ? 'var(--accent-primary)' : 'var(--warning)';
  return (
    <div
      className="rounded-lg p-3.5 mb-4"
      style={{ background: bg, border: `1px solid ${border}` }}
    >
      <div
        className="text-[11px] uppercase tracking-wider mb-2.5 font-semibold"
        style={{ color: titleColor }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

function Row({
  label,
  value,
  valueColor,
  mono,
}: {
  label: string;
  value: string;
  valueColor?: string;
  mono?: boolean;
}) {
  return (
    <div
      className="flex justify-between items-center py-1.5 text-xs border-b last:border-b-0"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span
        className={mono ? 'mono' : ''}
        style={{
          color: valueColor ?? 'var(--text-primary)',
          fontWeight: 500,
          textAlign: 'right',
          maxWidth: '60%',
          wordBreak: 'break-all',
        }}
      >
        {value}
      </span>
    </div>
  );
}
