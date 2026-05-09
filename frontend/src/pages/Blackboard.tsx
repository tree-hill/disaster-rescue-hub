/**
 * 共享黑板可视化（对照 docs/prototypes/prototype_09_blackboard.html，按 01-06 风格统一）。
 *
 * 后端：
 * - GET /blackboard/stats
 * - GET /blackboard/entries（type/key_prefix/min_confidence/page）
 * - WS commander 房间订阅 'blackboard.updated' 实时刷新
 *
 * 占位：
 * - 视觉感知实时画面（左上 video grid + bbox 框）→ 没有真实视频流，用占位渐变 + 静态 bbox 演示效果（与原型一致）
 * - 模型信息（YOLOv8s / mAP / 推理速度）→ 静态展示（来自 BUSINESS_RULES）
 */
import {
  Activity,
  Cpu,
  Database,
  Flame,
  Layers,
  Search,
  Tv,
  Users,
  Zap,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  getBlackboardStats,
  listBlackboardEntries,
  type BlackboardEntry,
  type BlackboardStats,
} from '@/api/blackboard';
import { AppShell } from '@/components/common/AppShell';
import { useWSStore } from '@/store/ws';

interface DetectionEvent {
  id: string;
  ts: string;
  source: string;
  className: string;
  confidence: number;
  fused: boolean;
  dropped: boolean;
  position?: { lat: number; lng: number };
}

const TYPE_FILTERS: Array<{ k: string; label: string }> = [
  { k: '', label: '全部' },
  { k: 'survivor', label: '幸存者' },
  { k: 'fire', label: '火点' },
  { k: 'smoke', label: '烟雾' },
  { k: 'collapsed_building', label: '倒塌建筑' },
];

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('zh-CN', { hour12: false });
}

export function Blackboard() {
  const [stats, setStats] = useState<BlackboardStats | null>(null);
  const [entries, setEntries] = useState<BlackboardEntry[]>([]);
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [search, setSearch] = useState('');
  const [timeline, setTimeline] = useState<DetectionEvent[]>([]);

  const wsConnect = useWSStore((s) => s.connect);
  const wsSubscribe = useWSStore((s) => s.subscribe);
  const wsAddListener = useWSStore((s) => s.addListener);

  const refresh = useMemo(
    () => async () => {
      const [s, p] = await Promise.all([
        getBlackboardStats(),
        listBlackboardEntries({
          type: typeFilter || undefined,
          key_prefix: search || undefined,
          page: 1,
          page_size: 30,
        }),
      ]);
      setStats(s);
      setEntries(p.items);
    },
    [typeFilter, search],
  );

  useEffect(() => {
    refresh().catch(() => undefined);
  }, [refresh]);

  // 周期 polling stats（黑板写入频率高，stats 数字应该实时变）
  useEffect(() => {
    const id = setInterval(() => refresh().catch(() => undefined), 5000);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    wsConnect();
    wsSubscribe('commander');
    const off1 = wsAddListener<{ key: string; value: Record<string, unknown>; confidence: number; source_robot_id: string | null; is_fused: boolean }>(
      'blackboard.updated',
      (payload) => {
        const cls = (payload.value?.type as string) ?? 'unknown';
        const ev: DetectionEvent = {
          id: `${Date.now()}-${Math.random()}`,
          ts: new Date().toISOString(),
          source: payload.source_robot_id?.slice(0, 8) ?? '—',
          className: cls,
          confidence: payload.confidence,
          fused: payload.is_fused,
          dropped: false,
        };
        setTimeline((prev) => [ev, ...prev].slice(0, 20));
        refresh().catch(() => undefined);
      },
    );
    const off2 = wsAddListener<{ class_name: string; confidence: number; source_robot_code?: string }>(
      'perception.detection',
      (p) => {
        const ev: DetectionEvent = {
          id: `${Date.now()}-${Math.random()}`,
          ts: new Date().toISOString(),
          source: p.source_robot_code ?? '—',
          className: p.class_name,
          confidence: p.confidence,
          fused: false,
          dropped: p.confidence < 0.5,
        };
        setTimeline((prev) => [ev, ...prev].slice(0, 20));
      },
    );
    return () => { off1(); off2(); };
  }, [wsConnect, wsSubscribe, wsAddListener, refresh]);

  const survivorCount = stats?.by_type?.survivor ?? 0;
  const fireCount = stats?.by_type?.fire ?? 0;

  return (
    <AppShell>
      <div className="container mx-auto px-6 py-5">
        <div className="text-xs flex items-center gap-1.5 mb-4" style={{ color: 'var(--text-tertiary)' }}>
          <span>协同通信</span>
          <span>/</span>
          <span style={{ color: 'var(--text-secondary)' }}>共享黑板可视化</span>
        </div>

        {/* 顶部统计 */}
        <div className="grid grid-cols-5 gap-3 mb-5">
          <StatCard icon={<Database className="w-5 h-5" />} label="黑板条目数" value={stats?.total_entries ?? 0} sub="活跃数据" color="var(--accent-primary)" bg="rgba(59,130,246,0.15)" />
          <StatCard icon={<Users className="w-5 h-5" />} label="活跃订阅者" value={stats?.active_subscribers ?? 0} sub="领域模块" color="var(--info)" bg="rgba(6,182,212,0.15)" />
          <StatCard icon={<Activity className="w-5 h-5" />} label="融合延迟 (ms)" value={(stats?.avg_fusion_latency_ms ?? 0).toFixed(0)} sub="P95" color="var(--success)" bg="rgba(16,185,129,0.15)" />
          <StatCard icon={<Zap className="w-5 h-5" />} label="吞吐 / 分" value={(stats?.throughput_per_min ?? 0).toFixed(0)} sub="近 60s" color="var(--warning)" bg="rgba(245,158,11,0.15)" />
          <StatCard icon={<Cpu className="w-5 h-5" />} label="YOLO 识别" value={`${survivorCount} / ${fireCount}`} sub="幸存者 / 火点" color="var(--accent-primary)" bg="rgba(59,130,246,0.15)" highlight />
        </div>

        {/* 主体 */}
        <div className="grid gap-4" style={{ gridTemplateColumns: '1.05fr 1fr' }}>
          {/* 左 */}
          <div className="panel p-5">
            <div className="text-base font-semibold mb-4 flex items-center gap-2">
              <Tv className="w-4 h-4" /> 视觉感知实时画面
              <span className="badge badge-danger ml-1 pulse-dot-wrap" style={{ background: 'rgba(239,68,68,0.15)', color: 'var(--danger)' }}>
                ● LIVE
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <VideoCard label="UAV-001" tint="normal" detections={[
                { type: 'survivor', conf: 0.92, x: 25, y: 35, w: 18, h: 30 },
                { type: 'survivor', conf: 0.85, x: 60, y: 55, w: 14, h: 22 },
              ]} />
              <VideoCard label="UAV-003" tint="fire" detections={[
                { type: 'fire', conf: 0.96, x: 25, y: 30, w: 25, h: 35 },
                { type: 'smoke', conf: 0.78, x: 55, y: 15, w: 30, h: 25 },
              ]} />
            </div>

            <div className="text-xs mb-2 flex items-center justify-between">
              <span className="font-semibold" style={{ color: 'var(--text-secondary)' }}>检测时间线</span>
              <span style={{ color: 'var(--text-tertiary)' }}>最近 {timeline.length} 条</span>
            </div>
            <div className="rounded-lg overflow-y-auto scroll-thin" style={{ maxHeight: 240, background: 'var(--bg-tertiary)', padding: 10 }}>
              {timeline.length === 0 && (
                <div className="text-center text-xs py-4" style={{ color: 'var(--text-tertiary)' }}>
                  等待 WebSocket 推送 perception.detection / blackboard.updated…
                </div>
              )}
              {timeline.map((e) => (
                <div
                  key={e.id}
                  className="px-3 py-2 mb-1.5 rounded text-xs flex items-center gap-2"
                  style={{
                    background: e.dropped ? 'rgba(92,101,128,0.08)' : 'var(--bg-secondary)',
                    borderLeft: `3px solid ${e.dropped ? 'var(--text-tertiary)' : e.fused ? 'var(--success)' : e.className === 'fire' ? 'var(--danger)' : 'var(--accent-primary)'}`,
                    opacity: e.dropped ? 0.4 : 1,
                  }}
                >
                  <span className="mono" style={{ color: 'var(--accent-primary)' }}>{fmtTime(e.ts)}</span>
                  <span className="mono" style={{ color: 'var(--warning)' }}>{e.source}</span>
                  <span style={{ color: 'var(--text-primary)' }}>· {e.className}</span>
                  <span className="mono font-semibold" style={{ color: e.dropped ? 'var(--text-tertiary)' : 'var(--success)' }}>
                    conf={e.confidence.toFixed(2)}
                  </span>
                  <span className="ml-auto text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                    {e.dropped ? '丢弃' : e.fused ? '融合' : '写入黑板'}
                  </span>
                </div>
              ))}
            </div>

            {/* 模型信息 */}
            <div
              className="mt-4 rounded-lg p-3.5"
              style={{
                background: 'linear-gradient(135deg, rgba(59,130,246,0.06), rgba(59,130,246,0.02))',
                border: '1px solid rgba(59,130,246,0.2)',
              }}
            >
              <div className="text-xs font-semibold mb-2 flex items-center gap-1.5" style={{ color: 'var(--accent-primary)' }}>
                <Cpu className="w-3.5 h-3.5" /> YOLOv8 模型信息
              </div>
              <div className="grid grid-cols-2 gap-x-5 gap-y-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
                <div>模型 <span className="mono font-semibold" style={{ color: 'var(--text-primary)' }}>YOLOv8s</span></div>
                <div>输入 <span className="mono font-semibold" style={{ color: 'var(--text-primary)' }}>640×640</span></div>
                <div>类别 <span className="mono font-semibold" style={{ color: 'var(--text-primary)' }}>4 类</span></div>
                <div>mAP@0.5 <span className="mono font-semibold" style={{ color: 'var(--text-primary)' }}>0.785</span></div>
                <div>推理速度 <span className="mono font-semibold" style={{ color: 'var(--text-primary)' }}>~25 ms</span></div>
                <div>置信度阈值 <span className="mono font-semibold" style={{ color: 'var(--text-primary)' }}>0.5</span></div>
              </div>
            </div>
          </div>

          {/* 右 */}
          <div className="panel p-5">
            <div className="text-base font-semibold mb-4 flex items-center gap-2">
              <Layers className="w-4 h-4" /> 黑板条目实时浏览
            </div>

            {/* Filter chips */}
            <div className="flex flex-wrap gap-2 mb-3">
              {TYPE_FILTERS.map((t) => (
                <span
                  key={t.k}
                  onClick={() => setTypeFilter(t.k)}
                  className="px-3 py-1.5 rounded-full text-xs cursor-pointer transition"
                  style={{
                    background: typeFilter === t.k ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
                    border: `1px solid ${typeFilter === t.k ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                    color: typeFilter === t.k ? 'white' : 'var(--text-secondary)',
                    fontWeight: typeFilter === t.k ? 600 : 400,
                  }}
                >
                  {t.label} {t.k && stats?.by_type?.[t.k] != null ? `· ${stats.by_type[t.k]}` : ''}
                </span>
              ))}
            </div>

            {/* Search */}
            <div className="relative mb-4">
              <Search className="w-4 h-4 absolute left-3 top-2.5" style={{ color: 'var(--text-tertiary)' }} />
              <input
                type="text"
                placeholder="搜索 Key 前缀,例如 survivor:30"
                className="w-full pl-9 pr-3 py-2 text-sm rounded"
                style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            {/* Entries */}
            <div className="space-y-2 overflow-y-auto scroll-thin" style={{ maxHeight: 480 }}>
              {entries.length === 0 && (
                <div className="text-center text-xs py-8" style={{ color: 'var(--text-tertiary)' }}>
                  暂无黑板条目（视觉数据流默认关闭，可在 .env 设 MOCK_PERCEPTION_ENABLED=true）
                </div>
              )}
              {entries.map((e) => {
                const fused = e.fused_from && e.fused_from.length > 1;
                const isFire = e.key.startsWith('fire:');
                const sources = (e.fused_from && e.fused_from.length > 0) ? e.fused_from : [{ robot_id: e.source_robot_id, confidence: e.confidence }];
                const updatedAge = Math.max(0, Math.round((Date.now() - new Date(e.updated_at).getTime()) / 1000));
                const ttlSec = Math.max(0, Math.round((new Date(e.expires_at).getTime() - Date.now()) / 1000));
                return (
                  <div
                    key={e.key}
                    className="rounded-lg p-3 mono text-xs"
                    style={{
                      background: isFire
                        ? 'linear-gradient(135deg, rgba(239,68,68,0.08), rgba(239,68,68,0.02))'
                        : fused
                        ? 'linear-gradient(135deg, rgba(16,185,129,0.08), rgba(16,185,129,0.02))'
                        : 'var(--bg-tertiary)',
                      border: `1px solid ${isFire ? 'rgba(239,68,68,0.3)' : fused ? 'rgba(16,185,129,0.3)' : 'var(--border-default)'}`,
                    }}
                  >
                    <div className="flex items-center justify-between mb-2 pb-2 border-b" style={{ borderColor: 'var(--border-default)' }}>
                      <span className="font-semibold flex items-center gap-1.5" style={{ color: isFire ? 'var(--danger)' : 'var(--accent-primary)' }}>
                        {isFire && <Flame className="w-3.5 h-3.5" />}
                        {e.key}
                      </span>
                      <span className="text-sm font-bold" style={{ color: 'var(--success)' }}>
                        {fused && '↑ '}{e.confidence.toFixed(2)}
                      </span>
                    </div>
                    <div className="leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                      <div>
                        <span style={{ color: 'var(--text-tertiary)' }}>value: </span>
                        <span style={{ color: 'var(--text-primary)' }}>
                          {JSON.stringify(e.value).slice(0, 70)}{JSON.stringify(e.value).length > 70 ? '…' : ''}
                        </span>
                      </div>
                      <div>
                        <span style={{ color: 'var(--text-tertiary)' }}>sources: </span>
                        {sources.map((src, i) => (
                          <span key={i} style={{ color: 'var(--warning)' }}>
                            {(src.robot_id as string)?.slice(0, 8) ?? '?'} ({(src.confidence as number)?.toFixed?.(2) ?? '?'})
                            {i < sources.length - 1 && <span style={{ color: 'var(--text-tertiary)' }}> + </span>}
                          </span>
                        ))}
                      </div>
                      <div>
                        <span style={{ color: 'var(--text-tertiary)' }}>updated: </span>
                        <span>{updatedAge}s 前</span>
                        <span style={{ color: 'var(--text-tertiary)' }}> · TTL: </span>
                        <span>{ttlSec}s</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

interface DetMock {
  type: 'survivor' | 'fire' | 'smoke';
  conf: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

function VideoCard({ label, tint, detections }: { label: string; tint: 'normal' | 'fire'; detections: DetMock[] }) {
  return (
    <div
      className="relative rounded-lg overflow-hidden border"
      style={{
        aspectRatio: '16/10',
        background: tint === 'fire'
          ? 'radial-gradient(circle at 35% 50%, rgba(255,80,40,0.5), rgba(180,60,30,0.3) 20%, transparent 35%), radial-gradient(circle at 60% 40%, rgba(120,120,120,0.3), transparent 30%), linear-gradient(135deg, #162342 0%, #0a1228 100%)'
          : 'radial-gradient(circle at 20% 30%, rgba(120,80,40,0.3), transparent 25%), radial-gradient(circle at 70% 60%, rgba(80,60,30,0.4), transparent 30%), linear-gradient(135deg, #162342 0%, #0a1228 100%)',
        borderColor: 'var(--border-subtle)',
      }}
    >
      <div className="absolute top-2 left-2 px-2.5 py-1 rounded text-[11px] font-semibold" style={{ background: 'rgba(0,0,0,0.6)', color: 'var(--accent-primary)', backdropFilter: 'blur(4px)' }}>
        📹 {label}
      </div>
      <div className="absolute top-2 right-2 flex items-center gap-1 text-[11px]" style={{ color: 'var(--danger)' }}>
        <span className="w-2 h-2 rounded-full pulse-dot" style={{ background: 'var(--danger)' }} />
        REC
      </div>
      {detections.map((d, i) => {
        const color = d.type === 'fire' ? 'var(--danger)' : d.type === 'smoke' ? '#aaa' : 'var(--info)';
        return (
          <div
            key={i}
            className="absolute"
            style={{
              top: `${d.y}%`,
              left: `${d.x}%`,
              width: `${d.w}%`,
              height: `${d.h}%`,
              border: `2px ${d.type === 'smoke' ? 'dashed' : 'solid'} ${color}`,
              boxShadow: `0 0 8px ${color}`,
            }}
          >
            <span
              className="absolute mono font-semibold"
              style={{
                top: -22,
                left: -2,
                padding: '2px 6px',
                fontSize: 10,
                background: color,
                color: d.type === 'smoke' ? '#fff' : d.type === 'fire' ? '#fff' : '#0a0e1a',
              }}
            >
              {d.type} {d.conf.toFixed(2)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  sub: string;
  color: string;
  bg: string;
  highlight?: boolean;
}

function StatCard({ icon, label, value, sub, color, bg, highlight }: StatCardProps) {
  return (
    <div
      className="panel p-4 flex items-center gap-3"
      style={{
        background: highlight ? 'linear-gradient(135deg, rgba(59,130,246,0.08), rgba(59,130,246,0.02))' : undefined,
        borderColor: highlight ? 'rgba(59,130,246,0.3)' : undefined,
      }}
    >
      <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: bg, color }}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</div>
        <div className="text-xl font-bold mono truncate" style={{ color }}>{value}</div>
        <div className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{sub}</div>
      </div>
    </div>
  );
}
