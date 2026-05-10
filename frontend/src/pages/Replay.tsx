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

const EXPERIMENT_ROWS = [
  {
    algorithm: 'AUCTION_HUNGARIAN' as Algorithm,
    completionRate: 87.3,
    responseSec: 42.5,
    pathKm: 8.2,
    loadStd: 1.21,
    decisionMs: 1842,
    note: '本文方法',
  },
  {
    algorithm: 'GREEDY' as Algorithm,
    completionRate: 72.1,
    responseSec: 38.2,
    pathKm: 7.5,
    loadStd: 3.84,
    decisionMs: 125,
    note: '对照',
  },
  {
    algorithm: 'RANDOM' as Algorithm,
    completionRate: 54.7,
    responseSec: 63.8,
    pathKm: 12.6,
    loadStd: 5.67,
    decisionMs: 8,
    note: '基线',
  },
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

function ExperimentPanel() {
  const [repetitions, setRepetitions] = useState(10);
  const [taskCount, setTaskCount] = useState(30);
  const [selected, setSelected] = useState<Set<Algorithm>>(new Set(['AUCTION_HUNGARIAN', 'GREEDY', 'RANDOM']));

  const runCount = selected.size * repetitions;
  const estimateMinutes = Math.max(1, Math.round(runCount * 0.5));

  // 实验编排目前不在线运行，参数变化即视为对照表静态展示
  const handleStart = () => {
    alert(
      '算法对比实验需后端 ExperimentRunner（P8 实装）。当前页面下方的对照表来自论文预设的离线统计数据，可作为答辩材料；启动按钮在 P8 接入后会触发批量回放。',
    );
  };

  const toggleAlgo = (algorithm: Algorithm) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(algorithm) && next.size > 1) next.delete(algorithm);
      else next.add(algorithm);
      return next;
    });
  };

  return (
    <main className="flex-1 p-5 overflow-y-auto scroll-thin">
      <div className="max-w-[1400px] mx-auto space-y-4">
        <section className="panel p-5">
          <div className="flex items-center gap-2 mb-4">
            <FlaskConical className="w-5 h-5" style={{ color: 'var(--warning)' }} />
            <h1 className="text-lg font-semibold">实验配置</h1>
          </div>
          <div className="grid grid-cols-4 gap-4 mb-4">
            <LabeledControl label="场景剧本">
              <select className="w-full px-3 py-2 text-sm rounded" style={controlStyle}>
                <option>6级地震废墟搜救</option>
                <option>森林火灾监测</option>
              </select>
            </LabeledControl>
            <LabeledControl label="任务数量">
              <input className="w-full px-3 py-2 text-sm rounded mono" style={controlStyle} type="number" min={1} value={taskCount} onChange={(e) => setTaskCount(Number(e.target.value))} />
            </LabeledControl>
            <LabeledControl label="重复次数">
              <input className="w-full px-3 py-2 text-sm rounded mono" style={controlStyle} type="number" min={1} max={30} value={repetitions} onChange={(e) => setRepetitions(Number(e.target.value))} />
            </LabeledControl>
            <LabeledControl label="执行模式">
              <select className="w-full px-3 py-2 text-sm rounded" style={controlStyle}>
                <option>快速验证</option>
                <option>论文完整实验</option>
              </select>
            </LabeledControl>
          </div>

          <div className="mb-4">
            <label className="text-xs font-semibold mb-2 block" style={{ color: 'var(--text-secondary)' }}>参与对比的算法</label>
            <div className="flex gap-3 flex-wrap">
              {EXPERIMENT_ROWS.map((row) => {
                const active = selected.has(row.algorithm);
                return (
                  <button
                    key={row.algorithm}
                    onClick={() => toggleAlgo(row.algorithm)}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg"
                    style={{
                      background: active ? `${ALGO_COLORS[row.algorithm]}20` : 'transparent',
                      border: `1px solid ${active ? ALGO_COLORS[row.algorithm] : 'var(--border-default)'}`,
                      color: active ? ALGO_COLORS[row.algorithm] : 'var(--text-secondary)',
                    }}
                  >
                    <span className="w-4 h-4 rounded flex items-center justify-center" style={{ background: active ? ALGO_COLORS[row.algorithm] : 'transparent', border: `1px solid ${ALGO_COLORS[row.algorithm]}` }}>
                      {active && <Check className="w-3 h-3 text-white" />}
                    </span>
                    <span className="text-sm font-semibold mono">{row.algorithm}</span>
                    <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>({row.note})</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex items-center justify-between pt-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <Info className="w-4 h-4" />
              <span>预估总时长 <span className="mono font-bold text-white">{estimateMinutes} 分钟</span> · 将产生 <span className="mono font-bold text-white">{runCount}</span> 条实验记录 · 每轮 {taskCount} 个任务</span>
            </div>
            <button className="btn-primary flex items-center gap-2" onClick={handleStart}>
              <Play className="w-4 h-4" /> 启动实验
            </button>
          </div>
        </section>

        <section className="panel p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5" style={{ color: 'var(--success)' }} />
              <span className="text-sm font-semibold">实验进度</span>
              <span className="badge badge-success">已完成</span>
            </div>
            <div className="text-xs mono" style={{ color: 'var(--text-tertiary)' }}>耗时 14:32 · 完成时间 2026-05-10 14:30</div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {EXPERIMENT_ROWS.map((row) => (
              <div key={row.algorithm} className="px-4 py-3 rounded-lg" style={{ background: `${ALGO_COLORS[row.algorithm]}16`, border: `1px solid ${ALGO_COLORS[row.algorithm]}` }}>
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="font-semibold mono" style={{ color: ALGO_COLORS[row.algorithm] }}>{row.algorithm}</span>
                  <span className="mono">{repetitions} / {repetitions} ✓</span>
                </div>
                <div className="progress-bar"><div className="progress-fill" style={{ width: '100%', background: ALGO_COLORS[row.algorithm] }} /></div>
              </div>
            ))}
          </div>
        </section>

        <section className="grid grid-cols-3 gap-4">
          {EXPERIMENT_ROWS.map((row, index) => (
            <div key={row.algorithm} className="panel p-4 relative" style={{ borderColor: index === 0 ? ALGO_COLORS[row.algorithm] : 'var(--border-subtle)' }}>
              {index === 0 && <div className="absolute top-0 right-0 px-3 py-1 rounded-bl-lg rounded-tr-lg text-xs font-bold" style={{ background: ALGO_COLORS[row.algorithm], color: 'white' }}>最优</div>}
              <div className="text-xs mb-1 mono" style={{ color: 'var(--text-tertiary)' }}>{row.algorithm}</div>
              <div className="text-2xl font-bold mono mb-3" style={{ color: ALGO_COLORS[row.algorithm] }}>{row.completionRate}%</div>
              <MetricLine label="响应时间" value={`${row.responseSec}s`} />
              <MetricLine label="路径总长" value={`${row.pathKm}km`} />
              <MetricLine label="负载标准差" value={row.loadStd.toFixed(2)} />
              <MetricLine label="决策耗时" value={`${row.decisionMs}ms`} />
            </div>
          ))}
        </section>

        <section className="grid grid-cols-2 gap-4">
          <ChartPanel title="图 6-1 任务完成率(%)" metric="completionRate" suffix="%" note="Hungarian 显著优于其他算法，适合作为论文核心对比图。" />
          <ChartPanel title="图 6-2 平均响应时间(秒)" metric="responseSec" suffix="s" note="Greedy 响应略快，但整体完成质量低于 Hungarian。" />
          <ChartPanel title="图 6-3 总路径长度(km)" metric="pathKm" suffix="km" note="Greedy 路径更短，体现局部贪心特征。" />
          <ChartPanel title="图 6-4 负载均衡度(标准差，越低越好)" metric="loadStd" suffix="" note="Hungarian 负载均衡优势明显，是答辩展示重点。" highlight />
          <ChartPanel title="图 6-5 算法决策耗时(ms)" metric="decisionMs" suffix="ms" note="Hungarian 用更高计算成本换取更好的全局分配质量。" wide />
        </section>
      </div>
    </main>
  );
}

function ChartPanel({ title, metric, suffix, note, highlight = false, wide = false }: { title: string; metric: keyof typeof EXPERIMENT_ROWS[number]; suffix: string; note: string; highlight?: boolean; wide?: boolean }) {
  const numeric = EXPERIMENT_ROWS.map((r) => Number(r[metric]));
  const max = Math.max(...numeric);
  return (
    <div className={`panel p-4 ${wide ? 'col-span-2' : ''}`} style={{ border: highlight ? '2px solid var(--success)' : undefined }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-semibold">{title}</div>
        <button className="btn-ghost"><Download className="w-3.5 h-3.5" /></button>
      </div>
      <div className="space-y-3">
        {EXPERIMENT_ROWS.map((row) => {
          const value = Number(row[metric]);
          const width = Math.max(8, (value / max) * 100);
          return (
            <div key={row.algorithm} className="grid items-center gap-3" style={{ gridTemplateColumns: '170px 1fr 72px' }}>
              <span className="text-xs mono" style={{ color: ALGO_COLORS[row.algorithm] }}>{row.algorithm}</span>
              <div className="h-6 rounded" style={{ background: 'var(--bg-tertiary)' }}>
                <div className="h-full rounded" style={{ width: `${width}%`, background: ALGO_COLORS[row.algorithm] }} />
              </div>
              <span className="text-xs mono text-right">{value}{suffix}</span>
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
