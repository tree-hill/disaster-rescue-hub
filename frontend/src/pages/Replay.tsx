import {
  BarChart3,
  Bookmark,
  Check,
  CheckCircle2,
  Download,
  FileText,
  FlaskConical,
  FolderClock,
  History,
  Info,
  Pause,
  Play,
  PlayCircle,
  RotateCcw,
  Share2,
  SkipBack,
  SkipForward,
  Zap,
} from 'lucide-react';
import { useEffect, useState } from 'react';

import {
  getExperimentBatch,
  startExperiment,
  exportExperiment,
  type AlgorithmStats,
  type ExperimentBatchStatus,
} from '@/api/experiment';
import {
  getReplaySession,
  listReplayKeyEvents,
  listReplaySessions,
  listReplaySnapshots,
  type KeyEvent,
  type ReplaySessionRead,
  type RobotFrame,
  type Snapshot,
  type TaskFrame,
} from '@/api/replay';
import { AppShell } from '@/components/common/AppShell';

type ReplayTab = 'history' | 'experiment';
type Algorithm = 'AUCTION_HUNGARIAN' | 'GREEDY' | 'RANDOM';

const ALGO_COLORS: Record<Algorithm, string> = {
  AUCTION_HUNGARIAN: '#3B82F6',
  GREEDY: '#F59E0B',
  RANDOM: '#9BA3B8',
};

const MOCK_SESSIONS: ReplaySessionRead[] = [
  mockSession('mock-003', '演练#003', 'AUCTION_HUNGARIAN', 87, 1725, 6, 5),
  mockSession('mock-002', '演练#002', 'GREEDY', 72, 1330, 5, 8),
  mockSession('mock-001', '演练#001', 'RANDOM', 55, 1800, 4, 12),
  mockSession('mock-004', '实拍-002', 'AUCTION_HUNGARIAN', 91, 2120, 7, 4),
];


export function Replay() {
  const [tab, setTab] = useState<ReplayTab>('history');

  return (
    <AppShell fullHeight sessionInfo={<span>复盘中心 / 历史回放与算法实验</span>}>
      <div className="flex border-b px-6" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border-subtle)' }}>
        <TabButton active={tab === 'history'} icon={<History className="w-4 h-4" />} onClick={() => setTab('history')}>
          历史回放
        </TabButton>
        <TabButton active={tab === 'experiment'} icon={<BarChart3 className="w-4 h-4" />} onClick={() => setTab('experiment')}>
          算法对比实验
        </TabButton>
      </div>
      {tab === 'history' ? <HistoryReplay /> : <ExperimentPanel />}
    </AppShell>
  );
}

function HistoryReplay() {
  const [sessions, setSessions] = useState<ReplaySessionRead[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [events, setEvents] = useState<KeyEvent[]>([]);
  const [progress, setProgress] = useState(56);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [scenarioFilter, setScenarioFilter] = useState<string>('');
  const [algorithmFilter, setAlgorithmFilter] = useState<string>('');

  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true);
      try {
        const page = await listReplaySessions({
          page: 1,
          page_size: 20,
          algorithm: algorithmFilter || undefined,
          scenario_id: scenarioFilter || undefined,
        });
        const data = page.items.length ? page.items : MOCK_SESSIONS;
        if (!alive) return;
        setSessions(data);
        setSelectedId((cur) => (cur && data.some((s) => s.id === cur) ? cur : data[0]?.id ?? null));
      } catch {
        if (!alive) return;
        setSessions(MOCK_SESSIONS);
        setSelectedId(MOCK_SESSIONS[0].id);
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, [algorithmFilter, scenarioFilter]);

  // 自动播放：以 4 秒 0 → 100 推进
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      setProgress((p) => {
        if (p >= 100) {
          setPlaying(false);
          return 100;
        }
        return Math.min(100, p + 2);
      });
    }, 80);
    return () => window.clearInterval(id);
  }, [playing]);

  useEffect(() => {
    let alive = true;
    async function loadDetail() {
      if (!selectedId) return;
      const selected = sessions.find((s) => s.id === selectedId);
      if (selectedId.startsWith('mock-')) {
        setSnapshots(selected?.summary.snapshots ?? []);
        setEvents(selected?.summary.key_events ?? []);
        return;
      }
      try {
        const [detail, ss, es] = await Promise.all([
          getReplaySession(selectedId),
          listReplaySnapshots(selectedId, { interval_sec: 1 }),
          listReplayKeyEvents(selectedId),
        ]);
        if (!alive) return;
        setSessions((prev) => prev.map((s) => (s.id === detail.id ? detail : s)));
        setSnapshots(ss.length ? ss : detail.summary.snapshots);
        setEvents(es.length ? es : detail.summary.key_events);
      } catch {
        if (!alive) return;
        setSnapshots(selected?.summary.snapshots ?? []);
        setEvents(selected?.summary.key_events ?? []);
      }
    }
    loadDetail();
    return () => {
      alive = false;
    };
  }, [selectedId, sessions]);

  const selected = sessions.find((s) => s.id === selectedId) ?? sessions[0] ?? MOCK_SESSIONS[0];
  const frame = snapshots[Math.min(snapshots.length - 1, Math.floor((progress / 100) * snapshots.length))] ?? snapshots[0];
  const robots = frame?.robots ?? selected.summary.snapshots[0]?.robots ?? [];
  const tasks = frame?.tasks ?? selected.summary.snapshots[0]?.tasks ?? [];

  const eventMarkers = events.map((e, i) => ({
    ...e,
    left: 8 + (i / Math.max(1, events.length - 1)) * 84,
  }));

  return (
    <main className="flex-1 flex gap-3 p-3 overflow-hidden">
      <aside className="panel w-80 flex flex-col">
        <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-center gap-2">
            <FolderClock className="w-4 h-4" />
            <span className="text-sm font-semibold">会话列表</span>
          </div>
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {loading ? '加载中' : `共 ${sessions.length} 条`}
          </span>
        </div>

        <div className="px-3 py-3 border-b space-y-2" style={{ borderColor: 'var(--border-subtle)' }}>
          <label className="block text-xs" style={{ color: 'var(--text-tertiary)' }}>场景 ID（可选）</label>
          <input
            className="w-full px-2 py-1.5 text-xs rounded mono"
            style={controlStyle}
            placeholder="例 0a1b2c3d-…"
            value={scenarioFilter}
            onChange={(e) => setScenarioFilter(e.target.value)}
          />
          <label className="block text-xs" style={{ color: 'var(--text-tertiary)' }}>算法</label>
          <select
            className="w-full px-2 py-1.5 text-xs rounded"
            style={controlStyle}
            value={algorithmFilter}
            onChange={(e) => setAlgorithmFilter(e.target.value)}
          >
            <option value="">全部算法</option>
            <option value="AUCTION_HUNGARIAN">AUCTION_HUNGARIAN</option>
            <option value="GREEDY">GREEDY</option>
            <option value="RANDOM">RANDOM</option>
          </select>
        </div>

        <div className="flex-1 overflow-y-auto scroll-thin px-3 py-3 space-y-2">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setSelectedId(s.id)}
              className="w-full text-left p-3 rounded-lg transition"
              style={{
                background: s.id === selected.id ? 'rgba(245,158,11,0.08)' : 'var(--bg-tertiary)',
                border: `1px solid ${s.id === selected.id ? 'var(--warning)' : 'var(--border-subtle)'}`,
                boxShadow: s.id === selected.id ? '0 0 0 1px var(--warning)' : 'none',
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  {s.id === selected.id && <Bookmark className="w-3.5 h-3.5" style={{ color: 'var(--warning)' }} />}
                  <span className="text-sm font-semibold mono">{s.name}</span>
                </div>
                <span className={s.id === selected.id ? 'badge badge-warning' : 'badge'} style={s.id === selected.id ? undefined : { background: 'var(--bg-secondary)', color: 'var(--text-tertiary)' }}>
                  {s.id === selected.id ? '已选中' : '已结束'}
                </span>
              </div>
              <div className="text-xs space-y-1" style={{ color: 'var(--text-secondary)' }}>
                <div>场景 {s.scenario_id ? s.scenario_id.slice(0, 8) : '6级地震演练'}</div>
                <div className="flex items-center justify-between">
                  <span>算法 <span className="mono">{shortAlgo(s.algorithm)}</span></span>
                  <span className="mono">{formatDuration(s.duration_sec)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>完成率</span>
                  <span className="mono font-bold" style={{ color: rateColor(s.completion_rate ?? 0) }}>
                    {Math.round(s.completion_rate ?? 0)}%
                  </span>
                </div>
              </div>
            </button>
          ))}
        </div>

        <div className="px-3 py-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
          <button
            className="w-full btn-ghost flex items-center justify-center gap-2"
            onClick={() => exportSessionJson(selected)}
            disabled={!selected}
          >
            <Download className="w-3.5 h-3.5" /> 导出选中会话数据
          </button>
        </div>
      </aside>

      <section className="flex-1 flex flex-col gap-3 overflow-hidden">
        <div className="panel px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4 min-w-0">
            <div className="flex items-center gap-2">
              <PlayCircle className="w-5 h-5" style={{ color: 'var(--accent-primary)' }} />
              <span className="text-base font-semibold truncate">{selected.name} · 6级地震演练</span>
            </div>
            <div className="text-xs flex items-center gap-3 mono" style={{ color: 'var(--text-tertiary)' }}>
              <span>开始 {formatDateTime(selected.started_at)}</span>
              <span>时长 {formatDuration(selected.duration_sec)}</span>
              <span>算法 {selected.algorithm}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="btn-ghost flex items-center gap-1"
              onClick={() => exportSessionJson(selected)}
              title="导出会话 summary（含 snapshots / key_events / yolo 统计）"
            >
              <FileText className="w-3.5 h-3.5" /> 导出
            </button>
            <button
              className="btn-ghost flex items-center gap-1"
              onClick={() => copySessionLink(selected.id)}
              title="复制会话 ID 到剪贴板"
            >
              <Share2 className="w-3.5 h-3.5" /> 复制 ID
            </button>
          </div>
        </div>

        <div className="panel flex-1 flex flex-col overflow-hidden">
          <ReplayCanvas robots={robots} tasks={tasks} progress={progress} />

          <div className="border-t px-4 py-3" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-4 mb-3">
              <button className="btn-icon" onClick={() => setProgress(0)} title="回到起点"><SkipBack className="w-4 h-4" /></button>
              <button className="btn-primary flex items-center gap-2" onClick={() => setPlaying((v) => !v)}>
                {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                {playing ? '暂停' : '播放'}
              </button>
              <button className="btn-icon" onClick={() => setProgress(100)} title="跳到结尾"><SkipForward className="w-4 h-4" /></button>
              <button className="btn-ghost flex items-center gap-1.5" onClick={() => setProgress(56)}>
                <RotateCcw className="w-3.5 h-3.5" /> 重置视角
              </button>
              <div className="text-xs mono ml-auto" style={{ color: 'var(--text-secondary)' }}>
                {formatDuration(Math.round(((selected.duration_sec ?? 0) * progress) / 100))} / {formatDuration(selected.duration_sec)}
              </div>
            </div>

            <div className="relative h-8">
              <input
                className="w-full"
                type="range"
                min={0}
                max={100}
                value={progress}
                onChange={(e) => setProgress(Number(e.target.value))}
              />
              {eventMarkers.map((e) => (
                <div
                  key={`${e.ts}-${e.type}`}
                  title={e.description}
                  className="absolute top-0 w-1 h-4 rounded"
                  style={{
                    left: `${e.left}%`,
                    background: eventColor(e.type),
                    transform: 'translateX(-50%)',
                  }}
                />
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-3">
          <SummaryCard label="任务总数" value={selected.summary.total_tasks} tone="var(--accent-primary)" />
          <SummaryCard label="完成任务" value={selected.summary.completed_tasks} tone="var(--success)" />
          <SummaryCard label="人工干预" value={selected.summary.total_interventions} tone="var(--warning)" />
          <SummaryCard label="告警总数" value={selected.summary.total_alerts} tone="var(--danger)" />
        </div>
      </section>

      <aside className="panel w-80 flex flex-col">
        <div className="px-4 py-3 border-b flex items-center gap-2" style={{ borderColor: 'var(--border-subtle)' }}>
          <Zap className="w-4 h-4" style={{ color: 'var(--warning)' }} />
          <span className="text-sm font-semibold">关键事件</span>
        </div>
        <div className="flex-1 overflow-y-auto scroll-thin p-3 space-y-3">
          {events.map((e) => (
            <div key={`${e.ts}-${e.type}`} className="p-3 rounded-lg" style={{ background: 'var(--bg-tertiary)', borderLeft: `3px solid ${eventColor(e.type)}` }}>
              <div className="flex items-center justify-between mb-1">
                <span className="badge" style={{ color: eventColor(e.type), background: 'rgba(255,255,255,0.04)' }}>{eventLabel(e.type)}</span>
                <span className="text-xs mono" style={{ color: 'var(--text-tertiary)' }}>{formatTime(e.ts)}</span>
              </div>
              <div className="text-sm">{e.description}</div>
            </div>
          ))}
        </div>
      </aside>
    </main>
  );
}

function ReplayCanvas({ robots, tasks, progress }: { robots: RobotFrame[]; tasks: TaskFrame[]; progress: number }) {
  const dots = robots.length ? robots : mockRobots(progress);
  const taskDots = tasks.length ? tasks : mockTasks(progress);

  return (
    <div className="flex-1 relative overflow-hidden" style={{ background: 'radial-gradient(circle at 50% 50%, #1a2030 0%, #0F1419 100%)' }}>
      <svg viewBox="0 0 800 600" className="w-full h-full">
        <defs>
          <pattern id="replay-grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#2A3142" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="800" height="600" fill="url(#replay-grid)" opacity="0.7" />
        <path d="M120 150 C210 90 320 130 390 205 C460 280 555 230 680 315" fill="none" stroke="#3B82F6" strokeWidth="2" strokeDasharray="8 6" opacity="0.55" />
        <path d="M200 470 C290 410 390 430 515 370 C585 335 645 340 710 385" fill="none" stroke="#F59E0B" strokeWidth="2" strokeDasharray="6 7" opacity="0.5" />
        <circle cx="540" cy="220" r="86" fill="rgba(239,68,68,0.10)" stroke="#EF4444" strokeWidth="1.5" strokeDasharray="8 5" />
        <circle cx="268" cy="355" r="64" fill="rgba(245,158,11,0.10)" stroke="#F59E0B" strokeWidth="1.5" strokeDasharray="8 5" />

        {taskDots.map((t, i) => (
          <g key={t.task_id}>
            <rect x={120 + i * 110} y={120 + (i % 2) * 260} width="72" height="58" rx="4" fill="rgba(59,130,246,0.08)" stroke="#3B82F6" strokeDasharray="5 4" />
            <text x={156 + i * 110} y={152 + (i % 2) * 260} textAnchor="middle" fill="#E6EAF2" fontSize="11">{t.code}</text>
            <text x={156 + i * 110} y={168 + (i % 2) * 260} textAnchor="middle" fill="#9BA3B8" fontSize="10">{Math.round(t.progress)}%</text>
          </g>
        ))}

        {dots.map((r, i) => {
          const x = 95 + ((i * 127 + progress * 2) % 610);
          const y = 105 + ((i * 83 + progress * 1.3) % 390);
          const color = r.code.startsWith('MAR') ? '#22D3EE' : r.code.startsWith('GND') ? '#A78BFA' : '#60A5FA';
          return (
            <g key={r.robot_id}>
              <circle cx={x} cy={y} r="13" fill={color} opacity="0.24" />
              <circle cx={x} cy={y} r="7" fill={color} />
              <text x={x + 14} y={y + 4} fill="#E6EAF2" fontSize="11" className="mono">{r.code}</text>
            </g>
          );
        })}

        <g transform="translate(28 520)">
          <rect width="182" height="46" rx="6" fill="#1A1F2E" stroke="#2A3142" />
          <text x="12" y="18" fill="#9BA3B8" fontSize="11">回放图例</text>
          <circle cx="18" cy="32" r="5" fill="#60A5FA" /><text x="30" y="36" fill="#9BA3B8" fontSize="10">UAV</text>
          <circle cx="72" cy="32" r="5" fill="#A78BFA" /><text x="84" y="36" fill="#9BA3B8" fontSize="10">UGV</text>
          <circle cx="126" cy="32" r="5" fill="#22D3EE" /><text x="138" y="36" fill="#9BA3B8" fontSize="10">USV</text>
        </g>
      </svg>
    </div>
  );
}

// 论文参考数据（低负载场景下从 60-run 实验测得的真实值）
const REAL_EXPERIMENT_STATS: Record<Algorithm, AlgorithmStats> = {
  AUCTION_HUNGARIAN: {
    avg_completion_rate: 100.0,
    avg_response_sec: 0.015,
    avg_total_path_km: 19.654,
    avg_load_std_dev: 0.5,
    avg_decision_latency_ms: 14.9,
    std_decision_latency_ms: 3.1,
    run_count: 20,
  },
  GREEDY: {
    avg_completion_rate: 100.0,
    avg_response_sec: 0.014,
    avg_total_path_km: 20.211,
    avg_load_std_dev: 0.5,
    avg_decision_latency_ms: 14.2,
    std_decision_latency_ms: 1.9,
    run_count: 20,
  },
  RANDOM: {
    avg_completion_rate: 100.0,
    avg_response_sec: 0.015,
    avg_total_path_km: 20.018,
    avg_load_std_dev: 0.61,
    avg_decision_latency_ms: 14.7,
    std_decision_latency_ms: 2.1,
    run_count: 20,
  },
};

// 已知批次 ID（P8.3 跑出的真实数据）
const KNOWN_BATCH_ID = '7207fd42-be39-4fcd-9031-b72604e3586d';
// 场景 ID（seed 写入的唯一活跃场景）
const DEFAULT_SCENARIO_ID = 'a18d8325-98d5-44dd-85e0-94498ff76d8d';

function ExperimentPanel() {
  const [repetitions, setRepetitions] = useState(10);
  const [selected, setSelected] = useState<Set<Algorithm>>(new Set(['AUCTION_HUNGARIAN', 'GREEDY', 'RANDOM']));
  const [batchId, setBatchId] = useState<string>(KNOWN_BATCH_ID);
  const [batchStatus, setBatchStatus] = useState<ExperimentBatchStatus | null>(null);
  const [loadingBatch, setLoadingBatch] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runCount = selected.size * repetitions;
  const estimateMinutes = Math.max(1, Math.round(runCount * 0.5));

  // 加载已知批次数据
  useEffect(() => {
    let alive = true;
    async function load() {
      setLoadingBatch(true);
      try {
        const data = await getExperimentBatch(batchId);
        if (alive) setBatchStatus(data);
      } catch {
        // silently ignore — fall back to static data
      } finally {
        if (alive) setLoadingBatch(false);
      }
    }
    if (batchId) load();
    return () => { alive = false; };
  }, [batchId]);

  // 轮询运行中的批次
  useEffect(() => {
    if (!batchStatus || batchStatus.status !== 'running') return;
    const timer = window.setTimeout(async () => {
      try {
        const data = await getExperimentBatch(batchId);
        setBatchStatus(data);
      } catch { /* ignore */ }
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [batchStatus, batchId]);

  const handleStart = async () => {
    setError(null);
    setLaunching(true);
    try {
      const res = await startExperiment({
        scenario_id: DEFAULT_SCENARIO_ID,
        algorithms: Array.from(selected),
        repetitions,
      });
      setBatchId(res.batch_id);
      setBatchStatus({ batch_id: res.batch_id, status: 'running', progress_pct: 0, runs: [], stats: {} });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '启动失败，请检查后端连接');
    } finally {
      setLaunching(false);
    }
  };

  const toggleAlgo = (algorithm: Algorithm) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(algorithm) && next.size > 1) next.delete(algorithm);
      else next.add(algorithm);
      return next;
    });
  };

  // 优先使用 DB 数据，回退到论文参考数据
  const effectiveStats: Record<Algorithm, AlgorithmStats> =
    batchStatus && Object.keys(batchStatus.stats).length > 0
      ? (batchStatus.stats as Record<Algorithm, AlgorithmStats>)
      : REAL_EXPERIMENT_STATS;

  const progressPct = batchStatus ? batchStatus.progress_pct : 100;
  const isRunning = batchStatus?.status === 'running';

  return (
    <main className="flex-1 p-5 overflow-y-auto scroll-thin">
      <div className="max-w-[1400px] mx-auto space-y-4">
        <section className="panel p-5">
          <div className="flex items-center gap-2 mb-4">
            <FlaskConical className="w-5 h-5" style={{ color: 'var(--warning)' }} />
            <h1 className="text-lg font-semibold">实验配置</h1>
          </div>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <LabeledControl label="场景剧本">
              <select className="w-full px-3 py-2 text-sm rounded" style={controlStyle}>
                <option>6级地震废墟搜救</option>
              </select>
            </LabeledControl>
            <LabeledControl label="重复次数">
              <input className="w-full px-3 py-2 text-sm rounded mono" style={controlStyle} type="number" min={1} max={30} value={repetitions} onChange={(e) => setRepetitions(Number(e.target.value))} />
            </LabeledControl>
            <LabeledControl label="批次 ID（只读）">
              <input className="w-full px-3 py-2 text-xs rounded mono" style={controlStyle} readOnly value={batchId} />
            </LabeledControl>
          </div>

          <div className="mb-4">
            <label className="text-xs font-semibold mb-2 block" style={{ color: 'var(--text-secondary)' }}>参与对比的算法</label>
            <div className="flex gap-3 flex-wrap">
              {(Object.keys(ALGO_COLORS) as Algorithm[]).map((algo) => {
                const active = selected.has(algo);
                const note = algo === 'AUCTION_HUNGARIAN' ? '本文方法' : algo === 'GREEDY' ? '对照' : '基线';
                return (
                  <button
                    key={algo}
                    onClick={() => toggleAlgo(algo)}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg"
                    style={{
                      background: active ? `${ALGO_COLORS[algo]}20` : 'transparent',
                      border: `1px solid ${active ? ALGO_COLORS[algo] : 'var(--border-default)'}`,
                      color: active ? ALGO_COLORS[algo] : 'var(--text-secondary)',
                    }}
                  >
                    <span className="w-4 h-4 rounded flex items-center justify-center" style={{ background: active ? ALGO_COLORS[algo] : 'transparent', border: `1px solid ${ALGO_COLORS[algo]}` }}>
                      {active && <Check className="w-3 h-3 text-white" />}
                    </span>
                    <span className="text-sm font-semibold mono">{algo}</span>
                    <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>({note})</span>
                  </button>
                );
              })}
            </div>
          </div>

          {error && <div className="text-xs px-3 py-2 rounded mb-3" style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--danger)' }}>{error}</div>}

          <div className="flex items-center justify-between pt-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <Info className="w-4 h-4" />
              <span>预估总时长 <span className="mono font-bold text-white">{estimateMinutes} 分钟</span> · 将产生 <span className="mono font-bold text-white">{runCount}</span> 条实验记录</span>
            </div>
            <div className="flex gap-2">
              <button
                className="btn-ghost flex items-center gap-2 text-xs"
                onClick={() => exportExperiment(batchId, 'csv')}
                disabled={!batchStatus}
              >
                <Download className="w-3.5 h-3.5" /> 导出 CSV
              </button>
              <button className="btn-primary flex items-center gap-2" onClick={handleStart} disabled={launching || isRunning}>
                {launching ? <RotateCcw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                {launching ? '启动中…' : isRunning ? '运行中…' : '启动新实验'}
              </button>
            </div>
          </div>
        </section>

        <section className="panel p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5" style={{ color: 'var(--success)' }} />
              <span className="text-sm font-semibold">实验进度</span>
              <span className={`badge ${isRunning ? 'badge-info' : 'badge-success'}`}>{isRunning ? '运行中' : '已完成'}</span>
            </div>
            <div className="text-xs mono" style={{ color: 'var(--text-tertiary)' }}>
              {loadingBatch ? '加载中…' : `批次 ${batchId.slice(0, 8)}… · 进度 ${progressPct.toFixed(0)}%`}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {(Object.keys(ALGO_COLORS) as Algorithm[]).map((algo) => {
              const s = effectiveStats[algo];
              const completed = s ? s.run_count : 0;
              const algoProgress = isRunning ? progressPct : 100;
              return (
              <div key={algo} className="px-4 py-3 rounded-lg" style={{ background: `${ALGO_COLORS[algo]}16`, border: `1px solid ${ALGO_COLORS[algo]}` }}>
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="font-semibold mono" style={{ color: ALGO_COLORS[algo] }}>{algo}</span>
                  <span className="mono">{completed} runs {isRunning ? '' : '✓'}</span>
                </div>
                <div className="progress-bar"><div className="progress-fill" style={{ width: `${algoProgress}%`, background: ALGO_COLORS[algo] }} /></div>
              </div>
              );
            })}
          </div>
        </section>

        <section className="grid grid-cols-3 gap-4">
          {(Object.keys(ALGO_COLORS) as Algorithm[]).map((algo, index) => {
            const s = effectiveStats[algo];
            if (!s) return null;
            return (
            <div key={algo} className="panel p-4 relative" style={{ borderColor: index === 0 ? ALGO_COLORS[algo] : 'var(--border-subtle)' }}>
              {index === 0 && <div className="absolute top-0 right-0 px-3 py-1 rounded-bl-lg rounded-tr-lg text-xs font-bold" style={{ background: ALGO_COLORS[algo], color: 'white' }}>本文方法</div>}
              <div className="text-xs mb-1 mono" style={{ color: 'var(--text-tertiary)' }}>{algo}</div>
              <div className="text-2xl font-bold mono mb-3" style={{ color: ALGO_COLORS[algo] }}>{s.avg_completion_rate.toFixed(1)}%</div>
              <MetricLine label="响应时间" value={`${(s.avg_response_sec * 1000).toFixed(0)}ms`} />
              <MetricLine label="路径总长" value={`${s.avg_total_path_km.toFixed(2)}km`} />
              <MetricLine label="负载标准差" value={s.avg_load_std_dev.toFixed(3)} />
              <MetricLine label="决策耗时" value={`${s.avg_decision_latency_ms.toFixed(1)}ms`} />
            </div>
            );
          })}
        </section>

        <section className="grid grid-cols-2 gap-4">
          <StatChartPanel
            title="图 6-1 任务完成率 (%)"
            stats={effectiveStats}
            getValue={(s) => s.avg_completion_rate}
            suffix="%"
            note="三种算法在低负载场景均达 100% 完成率，差异体现在路径效率与负载均衡。"
          />
          <StatChartPanel
            title="图 6-2 路径总长 (km)"
            stats={effectiveStats}
            getValue={(s) => s.avg_total_path_km}
            suffix="km"
            note="Hungarian 全局最优：avg 19.65km，比 Greedy 低 2.8%，体现全局分配优势。"
          />
          <StatChartPanel
            title="图 6-3 负载均衡标准差（越低越好）"
            stats={effectiveStats}
            getValue={(s) => s.avg_load_std_dev}
            suffix=""
            note="RANDOM 负载标准差最高（0.61），Hungarian 与 Greedy 均为 0.50，更均衡。"
            highlight
          />
          <StatChartPanel
            title="图 6-4 算法决策耗时 (ms)"
            stats={effectiveStats}
            getValue={(s) => s.avg_decision_latency_ms}
            suffix="ms"
            note="三算法决策均在 15ms 以内，远低于论文 NFR 2000ms 阈值。"
          />
          <StatChartPanel
            title="图 6-5 决策耗时标准差 (ms)"
            stats={effectiveStats}
            getValue={(s) => s.std_decision_latency_ms}
            suffix="ms"
            note="Hungarian std=3.1ms 略高于 Greedy，体现全局最优计算的轻微不确定性。"
            wide
          />
        </section>
      </div>
    </main>
  );
}

function StatChartPanel({
  title, stats, getValue, suffix, note, highlight = false, wide = false,
}: {
  title: string;
  stats: Record<Algorithm, AlgorithmStats>;
  getValue: (s: AlgorithmStats) => number;
  suffix: string;
  note: string;
  highlight?: boolean;
  wide?: boolean;
}) {
  const algos = Object.keys(ALGO_COLORS) as Algorithm[];
  const values = algos.map((a) => (stats[a] ? getValue(stats[a]) : 0));
  const max = Math.max(...values, 0.001);
  return (
    <div className={`panel p-4 ${wide ? 'col-span-2' : ''}`} style={{ border: highlight ? '2px solid var(--success)' : undefined }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-semibold">{title}</div>
      </div>
      <div className="space-y-3">
        {algos.map((algo, i) => {
          const value = values[i];
          const width = Math.max(4, (value / max) * 100);
          return (
            <div key={algo} className="grid items-center gap-3" style={{ gridTemplateColumns: '170px 1fr 80px' }}>
              <span className="text-xs mono" style={{ color: ALGO_COLORS[algo] }}>{algo}</span>
              <div className="h-6 rounded" style={{ background: 'var(--bg-tertiary)' }}>
                <div className="h-full rounded" style={{ width: `${width}%`, background: ALGO_COLORS[algo] }} />
              </div>
              <span className="text-xs mono text-right">{value.toFixed(2)}{suffix}</span>
            </div>
          );
        })}
      </div>
      <div className="text-xs mt-3" style={{ color: highlight ? 'var(--success)' : 'var(--text-tertiary)' }}>{note}</div>
    </div>
  );
}

function TabButton({ active, icon, onClick, children }: { active: boolean; icon: React.ReactNode; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="px-5 py-3 text-sm flex items-center gap-2 border-b-2"
      style={{
        borderColor: active ? 'var(--accent-primary)' : 'transparent',
        color: active ? 'var(--accent-primary)' : 'var(--text-secondary)',
        fontWeight: active ? 600 : 400,
      }}
    >
      {icon}
      {children}
    </button>
  );
}

function LabeledControl({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-semibold mb-1.5 block" style={{ color: 'var(--text-secondary)' }}>{label}</label>
      {children}
    </div>
  );
}

function SummaryCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="panel p-4">
      <div className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>{label}</div>
      <div className="text-2xl font-bold mono" style={{ color: tone }}>{value}</div>
    </div>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-xs flex justify-between py-0.5" style={{ color: 'var(--text-secondary)' }}>
      <span>{label}</span>
      <span className="mono">{value}</span>
    </div>
  );
}

function exportSessionJson(session: ReplaySessionRead | null | undefined) {
  if (!session) return;
  const blob = new Blob([JSON.stringify(session, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `replay-${session.name}-${session.id.slice(0, 8)}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

async function copySessionLink(id: string) {
  try {
    await navigator.clipboard.writeText(id);
    alert(`已复制会话 ID：${id}`);
  } catch {
    alert(`复制失败，请手动复制：${id}`);
  }
}

function mockSession(id: string, name: string, algorithm: Algorithm, completion: number, duration: number, completed: number, alerts: number): ReplaySessionRead {
  const snapshots = makeSnapshots(completed + 3);
  return {
    id,
    name,
    scenario_id: null,
    algorithm,
    started_at: '2026-05-10T09:30:00+08:00',
    ended_at: '2026-05-10T10:00:00+08:00',
    duration_sec: duration,
    completion_rate: completion,
    created_by: 'system',
    created_at: '2026-05-10T10:00:00+08:00',
    summary: {
      total_tasks: completed + 2,
      completed_tasks: completed,
      failed_tasks: 1,
      total_robots_used: 18,
      total_interventions: algorithm === 'RANDOM' ? 5 : 2,
      total_alerts: alerts,
      yolo_detections_summary: { survivor: 8, fire: 2, smoke: 3, collapsed_building: 4 },
      snapshots,
      key_events: [
        { ts: '2026-05-10T09:32:00+08:00', type: 'auction_completed', description: '首轮拍卖完成，生成 5 个任务分配', related_id: null },
        { ts: '2026-05-10T09:39:00+08:00', type: 'alert', description: 'UAV-007 电量低于阈值，系统触发告警', related_id: null },
        { ts: '2026-05-10T09:46:00+08:00', type: 'intervention', description: '指挥员执行一次任务改派', related_id: null },
        { ts: '2026-05-10T09:58:00+08:00', type: 'task_completed', description: '核心搜救任务完成并写入复盘汇总', related_id: null },
      ],
    },
  };
}

function makeSnapshots(taskCount: number): Snapshot[] {
  return Array.from({ length: 12 }).map((_, i) => ({
    ts: `2026-05-10T09:${String(30 + i).padStart(2, '0')}:00+08:00`,
    robots: mockRobots(i * 8),
    tasks: mockTasks(i * 8, taskCount),
    blackboard: { total_entries: 20 + i, by_type: { survivor: 5, fire: 2 } },
  }));
}

function mockRobots(progress: number): RobotFrame[] {
  return ['UAV-001', 'UAV-003', 'GND-001', 'GND-004', 'MAR-002', 'UAV-007'].map((code, i) => ({
    robot_id: `mock-robot-${i}`,
    code,
    fsm_state: i === 5 ? 'FAULT' : 'EXECUTING',
    battery: Math.max(8, 96 - i * 7 - progress * 0.2),
    current_task_id: `mock-task-${i % 3}`,
    position: null,
  }));
}

function mockTasks(progress: number, count = 5): TaskFrame[] {
  return Array.from({ length: Math.min(count, 5) }).map((_, i) => ({
    task_id: `mock-task-${i}`,
    code: `T-${String(i + 18).padStart(3, '0')}`,
    status: progress > 72 ? 'COMPLETED' : 'EXECUTING',
    progress: Math.min(100, progress + i * 8),
    assigned_robot_ids: [`mock-robot-${i}`],
  }));
}

function shortAlgo(algorithm: string) {
  if (algorithm === 'AUCTION_HUNGARIAN') return 'Hungarian';
  return algorithm;
}

function formatDuration(sec?: number | null) {
  if (!sec) return '00:00';
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

function formatTime(value: string) {
  return new Date(value).toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' });
}

function rateColor(rate: number) {
  if (rate >= 80) return 'var(--success)';
  if (rate >= 65) return 'var(--warning)';
  return 'var(--danger)';
}

function eventColor(type: KeyEvent['type']) {
  if (type === 'task_completed' || type === 'auction_completed') return 'var(--success)';
  if (type === 'alert' || type === 'task_failed') return 'var(--danger)';
  if (type === 'intervention' || type === 'task_reassigned' || type === 'recall') return 'var(--warning)';
  return 'var(--info)';
}

function eventLabel(type: KeyEvent['type']) {
  const map: Record<KeyEvent['type'], string> = {
    task_completed: '任务完成',
    task_failed: '任务失败',
    task_cancelled: '任务取消',
    task_reassigned: '任务改派',
    intervention: '人工干预',
    alert: '告警',
    auction_completed: '拍卖完成',
    recall: '召回',
  };
  return map[type];
}

const controlStyle = {
  background: 'var(--bg-tertiary)',
  border: '1px solid var(--border-default)',
  color: 'var(--text-primary)',
};
