/**
 * 指挥工作台（对照 docs/prototypes/prototype_01_cockpit.html）。
 *
 * 三栏布局：
 * - 左 w=72：机器人编队卡片（类型 Tab + 搜索 + 卡片列表）
 * - 中 flex-1：态势地图（SVG 网格 + 危险区 + 幸存者信号 + 任务网格 + 机器人）
 * - 右 w=80：任务 / 告警 / 日志 Tab + 创建按钮 + 任务卡片列表 + 底部告警
 *
 * 后端对接：
 * - GET /situation/kpi + WS commander 'kpi.snapshot' 实时刷新
 * - GET /robots + GET /robots/{id} 拉真实 fsm/battery（限制并发）
 * - GET /tasks 拉真实任务（mock 仅在 0 条时占位）
 * - GET /alerts 拉最近 5 条 + WS 'alert.raised' 实时插入
 * - GET /dispatch/algorithm + WS 'dispatch.algorithm_changed' 显示当前调度算法
 * - 改派 → ReassignDialog；召回 → /robots/{id}/recall；切换算法 → AlgorithmSwitchDialog
 */
import {
  AlertTriangle,
  Anchor,
  BatteryFull,
  BatteryLow,
  BatteryMedium,
  Bot,
  Camera,
  CheckCircle2,
  ClipboardList,
  Cpu,
  Hand,
  LocateFixed,
  MapPin,
  Maximize2,
  Minus,
  Pause,
  Plane,
  Play,
  Plus,
  Replace,
  RotateCcw,
  Ruler,
  Search,
  Square,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { useNavigate } from 'react-router-dom';

import { listAlerts, type AlertRead } from '@/api/alerts';
import {
  getAlgorithm,
  switchAlgorithm,
  type AlgorithmInfo,
  type DispatchAlgorithm,
} from '@/api/dispatch';
import { getRobot, listRobots, recallRobot, type FsmState } from '@/api/robots';
import { listTasks, type TaskRead } from '@/api/tasks';
import { fetchKpi, type KPISnapshot } from '@/api/situation';
import { AppShell } from '@/components/common/AppShell';
import { ReassignDialog } from '@/components/common/ReassignDialog';
import { useWSStore } from '@/store/ws';

interface RobotRow {
  id: string;
  code: string;
  type: 'aerial' | 'ground' | 'marine';
  fsm: FsmState;
  battery: number;
  detail: string;
}

const TYPE_LABEL_RT: Record<'uav' | 'ugv' | 'usv', string> = {
  uav: '无人机',
  ugv: '地面',
  usv: '水面',
};

const TYPE_FRONT: Record<'uav' | 'ugv' | 'usv', 'aerial' | 'ground' | 'marine'> = {
  uav: 'aerial',
  ugv: 'ground',
  usv: 'marine',
};

function robotColor(t: RobotRow['type']) {
  return t === 'aerial' ? 'var(--robot-aerial)' : t === 'ground' ? 'var(--robot-ground)' : 'var(--robot-marine)';
}

function batteryColor(pct: number) {
  if (pct >= 50) return 'var(--success)';
  if (pct >= 25) return 'var(--warning)';
  return 'var(--danger)';
}

function fsmBadge(fsm: FsmState) {
  if (fsm === 'EXECUTING') return 'badge-info';
  if (fsm === 'BIDDING') return 'badge-warning';
  if (fsm === 'FAULT') return 'badge-danger';
  if (fsm === 'RETURNING') return 'badge-warning';
  return 'badge-success';
}

function RobotIcon({ type }: { type: RobotRow['type'] }) {
  const c = robotColor(type);
  if (type === 'aerial') return <Plane className="w-4 h-4" style={{ color: c }} />;
  if (type === 'marine') return <Anchor className="w-4 h-4" style={{ color: c }} />;
  return <Bot className="w-4 h-4" style={{ color: c }} />;
}

export function Cockpit() {
  const navigate = useNavigate();
  const [kpi, setKpi] = useState<KPISnapshot | null>(null);
  const [robotTab, setRobotTab] = useState<'all' | 'aerial' | 'ground' | 'marine'>('all');
  const [robotSearch, setRobotSearch] = useState('');
  const [rightTab, setRightTab] = useState<'tasks' | 'alerts' | 'logs'>('tasks');
  const [robots, setRobots] = useState<RobotRow[]>([]);
  const [tasks, setTasks] = useState<TaskRead[]>([]);
  const [alerts, setAlerts] = useState<AlertRead[]>([]);
  const [reassignTarget, setReassignTarget] = useState<TaskRead | null>(null);
  const [algoInfo, setAlgoInfo] = useState<AlgorithmInfo | null>(null);
  const [showAlgoSwitch, setShowAlgoSwitch] = useState(false);
  const [logEntries, setLogEntries] = useState<Array<{ ts: string; line: string }>>([]);
  const [paused, setPaused] = useState(false);
  const mapRef = useRef<HTMLDivElement | null>(null);

  const wsConnect = useWSStore((s) => s.connect);
  const wsSubscribe = useWSStore((s) => s.subscribe);
  const wsAddListener = useWSStore((s) => s.addListener);

  const pushLog = (line: string) => {
    setLogEntries((prev) => [{ ts: new Date().toLocaleTimeString('zh-CN', { hour12: false }), line }, ...prev].slice(0, 50));
  };

  const loadRobotsWithState = async () => {
    try {
      const page = await listRobots({ page_size: 25 });
      const rows: RobotRow[] = await Promise.all(
        page.items.map(async (r): Promise<RobotRow> => {
          const front = TYPE_FRONT[r.type];
          const detail = await getRobot(r.id).catch(() => null);
          const st = detail?.latest_state;
          return {
            id: r.id,
            code: r.code,
            type: front,
            fsm: st?.fsm_state ?? 'IDLE',
            battery: st?.battery ?? 0,
            detail: st
              ? `${st.fsm_state} · (${st.position.lat.toFixed(3)}, ${st.position.lng.toFixed(3)})`
              : `${TYPE_LABEL_RT[r.type]} · ${r.model ?? ''}`,
          };
        }),
      );
      setRobots(rows);
    } catch {
      setRobots([]);
    }
  };

  const loadAlerts = () => {
    listAlerts({ page_size: 5, status: 'unack' })
      .then((p) => setAlerts(p.items))
      .catch(() => undefined);
  };

  useEffect(() => {
    fetchKpi().then(setKpi).catch(() => undefined);
    loadRobotsWithState();
    listTasks({ page_size: 10 }).then((p) => setTasks(p.items)).catch(() => undefined);
    loadAlerts();
    getAlgorithm().then(setAlgoInfo).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (paused) return;
    wsConnect();
    wsSubscribe('commander');
    const offs = [
      wsAddListener<KPISnapshot>('kpi.snapshot', (snap) => {
        setKpi(snap);
      }),
      wsAddListener<TaskRead>('task.created', (t) => {
        pushLog(`task.created · ${t?.code ?? ''}`);
        listTasks({ page_size: 10 }).then((p) => setTasks(p.items)).catch(() => undefined);
      }),
      wsAddListener<TaskRead>('task.cancelled', (t) => {
        pushLog(`task.cancelled · ${t?.code ?? ''}`);
        listTasks({ page_size: 10 }).then((p) => setTasks(p.items)).catch(() => undefined);
      }),
      wsAddListener('task.reassigned', () => {
        pushLog('task.reassigned');
        listTasks({ page_size: 10 }).then((p) => setTasks(p.items)).catch(() => undefined);
      }),
      wsAddListener<AlertRead>('alert.raised', (a) => {
        pushLog(`alert.raised · ${a?.severity ?? ''} ${a?.message ?? ''}`);
        loadAlerts();
      }),
      wsAddListener('alert.acknowledged', () => loadAlerts()),
      wsAddListener('alert.ignored', () => loadAlerts()),
      wsAddListener<{ current: DispatchAlgorithm; previous: DispatchAlgorithm }>(
        'dispatch.algorithm_changed',
        (p) => {
          pushLog(`algorithm: ${p.previous} → ${p.current}`);
          setAlgoInfo((prev) => (prev ? { ...prev, current: p.current } : prev));
        },
      ),
      wsAddListener<{ robot_id: string }>('robot.state_changed', () => {
        loadRobotsWithState();
      }),
      wsAddListener<{ robot_id: string }>('robot.recall_completed', () => {
        loadRobotsWithState();
      }),
    ];
    return () => offs.forEach((f) => f());
  }, [wsConnect, wsSubscribe, wsAddListener, paused]);

  const filtered = useMemo(
    () =>
      robots.filter(
        (r) =>
          (robotTab === 'all' || r.type === robotTab) &&
          (robotSearch.trim() === '' || r.code.toLowerCase().includes(robotSearch.toLowerCase())),
      ),
    [robots, robotTab, robotSearch],
  );
  const counts = useMemo(
    () => ({
      all: robots.length,
      aerial: robots.filter((r) => r.type === 'aerial').length,
      ground: robots.filter((r) => r.type === 'ground').length,
      marine: robots.filter((r) => r.type === 'marine').length,
    }),
    [robots],
  );

  const handleRecall = async (id: string, code: string) => {
    const reason = window.prompt(`召回原因（必填，至少 5 字）\n机器人: ${code}`);
    if (!reason || reason.trim().length < 5) return;
    try {
      await recallRobot(id, reason.trim());
      pushLog(`recall · ${code}`);
      loadRobotsWithState();
    } catch (e: unknown) {
      const m = (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? String(e);
      alert(`召回失败：${m}`);
    }
  };

  const handleFullscreen = () => {
    const el = mapRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => undefined);
    } else {
      el.requestFullscreen().catch(() => undefined);
    }
  };

  const algoLabel = algoInfo?.current === 'AUCTION_HUNGARIAN'
    ? 'Hungarian'
    : algoInfo?.current ?? '—';

  return (
    <AppShell fullHeight sessionInfo={
      <>
        <span>当前会话: <span className="text-white">6级地震-演练#003</span></span>
        <span className="mono" style={{ color: 'var(--text-tertiary)' }}>
          {' '}| {new Date().toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5)} | 算法: {algoInfo?.current ?? '...'}
        </span>
      </>
    }>
      {/* KPI 顶条 */}
      <div
        className="h-20 flex items-center px-6 gap-4 border-b shrink-0"
        style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border-subtle)' }}
      >
        <KpiCard
          icon={<Bot className="w-8 h-8" style={{ color: 'var(--accent-primary)' }} />}
          label="在线机器人"
          value={`${kpi?.online_robots ?? '--'}`}
          sub={`/ ${kpi?.total_robots ?? '--'}`}
        />
        <KpiCard
          icon={<ClipboardList className="w-8 h-8" style={{ color: 'var(--info)' }} />}
          label="任务总数"
          value={`${kpi?.active_tasks ?? '--'}`}
          subText={`活跃 ${kpi?.active_tasks ?? '--'}`}
        />
        <KpiCard
          icon={<CheckCircle2 className="w-8 h-8" style={{ color: 'var(--success)' }} />}
          label="任务完成率"
          value={`${kpi ? Math.round(kpi.completion_rate) : '--'}`}
          unit="%"
          valueColor="var(--success)"
        />
        <div
          className="flex-1 flex items-center gap-3 px-4 py-2 rounded-lg cursor-pointer hover:opacity-90"
          style={{
            background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.3)',
          }}
          onClick={() => navigate('/alerts')}
        >
          <AlertTriangle className="w-8 h-8" style={{ color: 'var(--danger)' }} />
          <div>
            <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>告警</div>
            <div>
              <span className="kpi-num mono" style={{ color: 'var(--danger)' }}>
                {kpi?.active_alerts ?? '--'}
              </span>
              <span className="text-xs ml-2" style={{ color: 'var(--text-tertiary)' }}>待处理</span>
            </div>
          </div>
        </div>
        <div
          className="flex-1 flex items-center gap-3 px-4 py-2 rounded-lg"
          style={{ background: 'var(--bg-tertiary)' }}
        >
          <Cpu className="w-8 h-8" style={{ color: 'var(--warning)' }} />
          <div>
            <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>调度算法</div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold mono">{algoLabel}</span>
              <button
                className="btn-ghost"
                style={{ padding: '2px 8px', fontSize: 11 }}
                onClick={() => setShowAlgoSwitch(true)}
              >
                切换
              </button>
            </div>
          </div>
        </div>
        <div
          className="flex-1 flex items-center gap-3 px-4 py-2 rounded-lg"
          style={{ background: 'var(--bg-tertiary)' }}
        >
          <MapPin className="w-8 h-8" style={{ color: 'var(--robot-aerial)' }} />
          <div>
            <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>场景</div>
            <div className="text-sm font-semibold">6级地震-演练</div>
          </div>
        </div>
      </div>

      {/* 三栏主体 */}
      <main className="flex-1 flex gap-3 p-3 overflow-hidden">
        {/* 左栏 */}
        <aside className="panel w-72 flex flex-col">
          <div
            className="px-4 py-3 border-b flex items-center justify-between"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4" />
              <span className="text-sm font-semibold">机器人编队</span>
            </div>
            <span className="badge badge-success">{kpi?.online_robots ?? '--'} 在线</span>
          </div>
          <div className="px-3 py-2 flex gap-1 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
            {[
              { k: 'all' as const, label: `全部 ${counts.all}` },
              { k: 'aerial' as const, label: `空 ${counts.aerial}` },
              { k: 'ground' as const, label: `陆 ${counts.ground}` },
              { k: 'marine' as const, label: `水 ${counts.marine}` },
            ].map((t) => (
              <button
                key={t.k}
                onClick={() => setRobotTab(t.k)}
                className="flex-1 py-1.5 text-xs rounded font-semibold"
                style={{
                  background: robotTab === t.k ? 'var(--accent-primary)' : 'transparent',
                  color: robotTab === t.k ? 'white' : 'var(--text-secondary)',
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="px-3 py-2 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="relative">
              <Search
                className="w-4 h-4 absolute left-2.5 top-2"
                style={{ color: 'var(--text-tertiary)' }}
              />
              <input
                type="text"
                placeholder="搜索机器人编号..."
                value={robotSearch}
                onChange={(e) => setRobotSearch(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded"
                style={{
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-default)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto scroll-thin px-3 py-2 space-y-2">
            {filtered.length === 0 && (
              <div className="text-center text-xs py-6" style={{ color: 'var(--text-tertiary)' }}>
                暂无机器人
              </div>
            )}
            {filtered.map((r) => (
              <div
                key={r.id}
                className="rounded-lg p-3 cursor-pointer hover:opacity-90"
                onClick={() => navigate(`/robots`)}
                style={{
                  background: r.fsm === 'FAULT' ? 'rgba(239,68,68,0.1)' : 'var(--bg-tertiary)',
                  border: r.fsm === 'FAULT' ? '1px solid var(--danger)' : undefined,
                  borderLeft: r.fsm === 'FAULT' ? '1px solid var(--danger)' : `3px solid ${robotColor(r.type)}`,
                }}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5">
                    <RobotIcon type={r.type} />
                    <span className="text-sm font-semibold mono">{r.code}</span>
                    {r.fsm === 'FAULT' && (
                      <AlertTriangle className="w-3.5 h-3.5" style={{ color: 'var(--danger)' }} />
                    )}
                  </div>
                  <span className={`badge ${fsmBadge(r.fsm)}`}>{r.fsm}</span>
                </div>
                <div className="flex items-center gap-2 mb-1">
                  {r.battery >= 80 ? (
                    <BatteryFull className="w-3.5 h-3.5" style={{ color: 'var(--success)' }} />
                  ) : r.battery >= 30 ? (
                    <BatteryMedium className="w-3.5 h-3.5" style={{ color: batteryColor(r.battery) }} />
                  ) : (
                    <BatteryLow className="w-3.5 h-3.5" style={{ color: 'var(--danger)' }} />
                  )}
                  <div className="flex-1 progress-bar" style={{ height: 4 }}>
                    <div
                      className="progress-fill"
                      style={{
                        width: `${r.battery}%`,
                        background: r.battery < 25 ? 'var(--danger)' : undefined,
                      }}
                    />
                  </div>
                  <span className="text-xs mono" style={{ color: batteryColor(r.battery) }}>
                    {r.battery.toFixed(0)}%
                  </span>
                </div>
                {r.fsm === 'FAULT' || (r.fsm !== 'IDLE' && r.battery < 25) ? (
                  <button
                    className="w-full py-1 text-xs rounded font-semibold mt-2"
                    style={{ background: 'var(--danger)', color: 'white', border: 'none' }}
                    onClick={(ev) => { ev.stopPropagation(); handleRecall(r.id, r.code); }}
                  >
                    紧急召回
                  </button>
                ) : (
                  <div className="text-xs mono" style={{ color: 'var(--text-tertiary)' }}>
                    {r.detail}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div
            className="px-3 py-2 border-t flex gap-2"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <button
              className="flex-1 btn-ghost flex items-center justify-center gap-1"
              onClick={() => navigate('/robots')}
            >
              <Plus className="w-3.5 h-3.5" /> 全部
            </button>
            <button
              className="flex-1 btn-ghost flex items-center justify-center gap-1"
              style={{ color: 'var(--danger)', borderColor: 'var(--danger)' }}
              onClick={() => navigate('/robots')}
            >
              <RotateCcw className="w-3.5 h-3.5" /> 召回中心
            </button>
          </div>
        </aside>

        {/* 中央地图 */}
        <section className="panel flex-1 flex flex-col overflow-hidden" ref={mapRef}>
          <div
            className="px-4 py-2 border-b flex items-center justify-between"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4" />
              <span className="text-sm font-semibold">态势地图</span>
              <span className="text-xs mono" style={{ color: 'var(--text-tertiary)' }}>
                | 演示视图 · 真实地图待 P8 接入
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button className="btn-ghost" disabled title="平移（待 P8）"><Hand className="w-3.5 h-3.5" /></button>
              <button className="btn-ghost" disabled title="选区（待 P8）"><Square className="w-3.5 h-3.5" /></button>
              <button className="btn-ghost" disabled title="测距（待 P8）"><Ruler className="w-3.5 h-3.5" /></button>
              <div className="w-px h-5 mx-1" style={{ background: 'var(--border-default)' }} />
              <button className="btn-ghost" disabled><Minus className="w-3.5 h-3.5" /></button>
              <span className="text-xs mono px-2" style={{ color: 'var(--text-secondary)' }}>100%</span>
              <button className="btn-ghost" disabled><Plus className="w-3.5 h-3.5" /></button>
              <button className="btn-ghost" disabled title="复位（待 P8）"><LocateFixed className="w-3.5 h-3.5" /></button>
            </div>
          </div>

          <div
            className="flex-1 relative overflow-hidden"
            style={{ background: 'radial-gradient(circle at 50% 50%, #1a2030 0%, #0F1419 100%)' }}
          >
            <CockpitMapSvg />
            <div
              className="absolute top-3 left-3 panel p-3 text-xs space-y-1.5"
              style={{ background: 'rgba(26,31,46,0.9)', backdropFilter: 'blur(8px)' }}
            >
              <div className="font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>图例</div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full" style={{ background: 'var(--robot-aerial)' }} />
                无人机
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-sm" style={{ background: 'var(--robot-ground)' }} />
                地面
              </div>
              <div className="flex items-center gap-2">
                <span
                  style={{
                    width: 0,
                    height: 0,
                    borderLeft: '6px solid transparent',
                    borderRight: '6px solid transparent',
                    borderBottom: '10px solid var(--robot-marine)',
                  }}
                />
                水面
              </div>
              <div className="flex items-center gap-2">
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ background: 'var(--success)', opacity: 0.6 }}
                />
                幸存者
              </div>
              <div className="flex items-center gap-2">
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ background: 'var(--danger)', opacity: 0.6 }}
                />
                危险区
              </div>
            </div>
          </div>

          <div
            className="h-10 px-4 flex items-center justify-between border-t"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="flex items-center gap-3">
              <span className="text-xs flex items-center gap-1.5">
                <span className="pulse-dot" style={{ background: paused ? 'var(--warning)' : undefined }}></span>
                {paused ? '已暂停推送' : '实时模式'}
              </span>
              <button
                className="btn-ghost"
                title={paused ? '恢复实时推送' : '暂停 WS 监听'}
                onClick={() => setPaused((v) => !v)}
              >
                {paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
              </button>
              <button className="btn-ghost" title="截图（待 P8）" disabled><Camera className="w-3.5 h-3.5" /></button>
            </div>
            <button className="btn-ghost flex items-center gap-1" onClick={handleFullscreen} title="全屏地图">
              <Maximize2 className="w-3.5 h-3.5" /> 全屏
            </button>
          </div>
        </section>

        {/* 右栏 */}
        <aside className="panel w-80 flex flex-col">
          <div className="flex border-b" style={{ borderColor: 'var(--border-subtle)' }}>
            {[
              { k: 'tasks' as const, label: `任务 ${tasks.length || kpi?.active_tasks || 0}` },
              { k: 'alerts' as const, label: '告警', badge: kpi?.active_alerts },
              { k: 'logs' as const, label: '日志' },
            ].map((t) => (
              <button
                key={t.k}
                className="flex-1 py-3 text-sm flex items-center justify-center gap-1"
                style={{
                  borderBottom: rightTab === t.k ? '2px solid var(--accent-primary)' : undefined,
                  color: rightTab === t.k ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  fontWeight: rightTab === t.k ? 600 : 400,
                }}
                onClick={() => setRightTab(t.k)}
              >
                {t.label}
                {t.badge != null && t.badge > 0 && (
                  <span className="badge badge-danger ml-1">{t.badge}</span>
                )}
              </button>
            ))}
          </div>

          <div className="px-3 py-2.5 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
            <button
              className="btn-primary w-full flex items-center justify-center gap-1.5"
              onClick={() => navigate('/tasks')}
            >
              <Plus className="w-4 h-4" /> 创建救援任务
            </button>
          </div>

          {rightTab === 'tasks' && (
            <div className="flex-1 overflow-y-auto scroll-thin px-3 py-2 space-y-2.5">
              {tasks.length === 0 ? (
                <div className="text-center text-xs py-4" style={{ color: 'var(--text-tertiary)' }}>
                  暂无任务 · 点击「创建救援任务」前往任务管理
                </div>
              ) : (
                tasks.map((t) => <TaskCardReal key={t.id} task={t} onReassign={() => setReassignTarget(t)} />)
              )}
            </div>
          )}
          {rightTab === 'alerts' && (
            <div className="flex-1 overflow-y-auto scroll-thin px-3 py-2 space-y-2">
              {alerts.length === 0 ? (
                <div className="text-center text-xs py-4" style={{ color: 'var(--text-tertiary)' }}>
                  暂无未处理告警
                </div>
              ) : (
                alerts.map((a) => (
                  <div
                    key={a.id}
                    className="rounded-lg p-2.5 text-xs cursor-pointer hover:opacity-90"
                    style={{
                      background: 'var(--bg-tertiary)',
                      borderLeft: `3px solid ${a.severity === 'critical' ? 'var(--danger)' : a.severity === 'warn' ? 'var(--warning)' : 'var(--info)'}`,
                    }}
                    onClick={() => navigate('/alerts')}
                  >
                    <div className="flex justify-between items-center mb-1">
                      <span className="mono" style={{ color: 'var(--warning)' }}>{a.source}</span>
                      <span className="mono" style={{ color: 'var(--text-tertiary)' }}>
                        {new Date(a.raised_at).toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5)}
                      </span>
                    </div>
                    <div style={{ color: 'var(--text-secondary)' }}>{a.message}</div>
                  </div>
                ))
              )}
              <button
                className="w-full btn-ghost text-xs mt-2"
                onClick={() => navigate('/alerts')}
              >
                查看全部告警 →
              </button>
            </div>
          )}
          {rightTab === 'logs' && (
            <div className="flex-1 overflow-y-auto scroll-thin px-3 py-2 text-xs space-y-1"
              style={{ color: 'var(--text-secondary)' }}>
              {logEntries.length === 0 ? (
                <div className="text-center text-xs py-4" style={{ color: 'var(--text-tertiary)' }}>
                  等待 WebSocket 事件…
                </div>
              ) : (
                logEntries.map((e, i) => (
                  <div key={i} className="flex gap-2 mono">
                    <span style={{ color: 'var(--accent-primary)' }}>{e.ts}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{e.line}</span>
                  </div>
                ))
              )}
            </div>
          )}

          <div
            className="border-t px-3 py-2.5"
            style={{ borderColor: 'var(--border-subtle)', background: 'rgba(239,68,68,0.05)' }}
          >
            <div className="flex items-center gap-1.5 mb-1.5">
              <AlertTriangle className="w-3.5 h-3.5" style={{ color: 'var(--danger)' }} />
              <span className="text-xs font-semibold" style={{ color: 'var(--danger)' }}>
                最近告警
              </span>
            </div>
            <div className="text-xs space-y-1" style={{ color: 'var(--text-secondary)' }}>
              {alerts.length === 0 && (
                <div style={{ color: 'var(--text-tertiary)' }}>暂无</div>
              )}
              {alerts.slice(0, 3).map((a) => (
                <div key={a.id}>· {a.source} · {a.message.slice(0, 28)}{a.message.length > 28 ? '…' : ''}</div>
              ))}
            </div>
          </div>
        </aside>
      </main>

      <ReassignDialog
        open={reassignTarget !== null}
        task={reassignTarget}
        onClose={() => setReassignTarget(null)}
        onSuccess={() => {
          listTasks({ page_size: 10 }).then((p) => setTasks(p.items)).catch(() => undefined);
        }}
      />

      {showAlgoSwitch && algoInfo && (
        <AlgorithmSwitchDialog
          info={algoInfo}
          onClose={() => setShowAlgoSwitch(false)}
          onChanged={(newAlgo) => {
            setAlgoInfo({ ...algoInfo, current: newAlgo });
            setShowAlgoSwitch(false);
          }}
        />
      )}
    </AppShell>
  );
}

interface KpiCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  subText?: string;
  unit?: string;
  valueColor?: string;
}

function KpiCard({ icon, label, value, sub, subText, unit, valueColor }: KpiCardProps) {
  return (
    <div
      className="flex-1 flex items-center gap-3 px-4 py-2 rounded-lg"
      style={{ background: 'var(--bg-tertiary)' }}
    >
      {icon}
      <div>
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</div>
        <div>
          <span className="kpi-num mono" style={{ color: valueColor }}>{value}</span>
          {unit && (
            <span className="text-base mono ml-0.5" style={{ color: valueColor }}>{unit}</span>
          )}
          {sub && (
            <span className="text-sm mono ml-1" style={{ color: 'var(--text-tertiary)' }}>{sub}</span>
          )}
          {subText && (
            <span className="text-xs mono ml-2" style={{ color: 'var(--text-tertiary)' }}>{subText}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function TaskCardReal({ task, onReassign }: { task: TaskRead; onReassign: () => void }) {
  const navigate = useNavigate();
  const sideColor = task.priority === 1 ? 'var(--danger)' : task.priority === 2 ? 'var(--warning)' : 'var(--success)';
  const priorityLabel = task.priority === 1 ? 'HIGH' : task.priority === 2 ? 'MED' : 'LOW';
  const priorityBadge = task.priority === 1 ? 'badge-danger' : task.priority === 2 ? 'badge-warning' : 'badge-success';
  const statusBadge =
    task.status === 'EXECUTING' || task.status === 'ASSIGNED' ? 'badge-info'
    : task.status === 'COMPLETED' ? 'badge-success'
    : task.status === 'PENDING' ? 'badge-warning'
    : 'badge-danger';
  return (
    <div className="rounded-lg p-3" style={{ background: 'var(--bg-tertiary)', borderLeft: `3px solid ${sideColor}` }}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold mono">{task.code}</span>
          <span className={`badge ${priorityBadge}`}>{priorityLabel}</span>
        </div>
        <span className={`badge ${statusBadge}`}>{task.status}</span>
      </div>
      <div className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>{task.name}</div>
      <div className="flex items-center gap-2 mb-2">
        <div className="flex-1 progress-bar"><div className="progress-fill" style={{ width: `${task.progress}%` }} /></div>
        <span className="text-xs mono font-semibold">{Number(task.progress).toFixed(0)}%</span>
      </div>
      <div className="flex justify-end gap-3">
        {(task.status === 'EXECUTING' || task.status === 'ASSIGNED') && (
          <button
            className="text-xs hover:underline flex items-center gap-1"
            style={{ color: 'var(--warning)' }}
            onClick={onReassign}
          >
            <Replace className="w-3 h-3" /> 改派
          </button>
        )}
        <button
          className="text-xs hover:underline"
          style={{ color: 'var(--accent-primary)' }}
          onClick={() => navigate('/tasks')}
        >
          详情
        </button>
      </div>
    </div>
  );
}

function AlgorithmSwitchDialog({
  info,
  onClose,
  onChanged,
}: {
  info: AlgorithmInfo;
  onClose: () => void;
  onChanged: (a: DispatchAlgorithm) => void;
}) {
  const [algo, setAlgo] = useState<DispatchAlgorithm>(info.current);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (algo === info.current) {
      setError('请选择不同算法');
      return;
    }
    if (reason.trim().length < 5) {
      setError('原因至少 5 字符');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await switchAlgorithm(algo, reason.trim());
      onChanged(res.current);
    } catch (e: unknown) {
      const m = (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? String(e);
      setError(m);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(6px)' }}
      onClick={onClose}
    >
      <div
        className="rounded-xl p-6"
        style={{
          width: 480,
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-default)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Cpu className="w-5 h-5" style={{ color: 'var(--warning)' }} />
            <span className="text-base font-bold">切换调度算法</span>
            <span className="text-xs px-2 py-0.5 rounded font-semibold" style={{ background: 'var(--warning)', color: 'white' }}>
              HITL
            </span>
          </div>
          <button onClick={onClose} className="btn-icon"><X className="w-4 h-4" /></button>
        </div>

        <div className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>当前算法</div>
        <div className="mono text-sm mb-4 p-2 rounded" style={{ background: 'var(--bg-tertiary)' }}>
          {info.current}
        </div>

        <div className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>切换至</div>
        <div className="grid grid-cols-1 gap-2 mb-4">
          {info.available.map((a) => (
            <div
              key={a}
              onClick={() => setAlgo(a)}
              className="px-3 py-2 rounded cursor-pointer mono text-sm flex items-center gap-2"
              style={{
                background: algo === a ? 'rgba(245,158,11,0.1)' : 'var(--bg-tertiary)',
                border: `1px solid ${algo === a ? 'var(--warning)' : 'var(--border-default)'}`,
                color: algo === a ? 'var(--warning)' : 'var(--text-primary)',
              }}
            >
              {algo === a ? '●' : '○'} {a} {a === info.current && <span className="text-xs ml-auto">（当前）</span>}
            </div>
          ))}
        </div>

        <div className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>
          切换原因 <span style={{ color: 'var(--danger)' }}>* 必填（≥ 5 字符，记入审计）</span>
        </div>
        <textarea
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="例：拍卖耗时过长，临时切换至 GREEDY 提升响应速度"
          style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-default)',
            color: 'var(--text-primary)',
            borderRadius: 6,
            padding: 10,
            fontSize: 13,
            width: '100%',
            resize: 'vertical',
            fontFamily: 'inherit',
          }}
        />

        {error && (
          <div className="mt-3 px-3 py-2 rounded text-xs" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: 'var(--danger)' }}>
            {error}
          </div>
        )}

        <div className="flex gap-2 mt-5">
          <button className="btn-ghost flex-1" onClick={onClose}>取消</button>
          <button
            className="btn-primary flex-1"
            style={{ background: 'var(--warning)', opacity: submitting ? 0.6 : 1 }}
            disabled={submitting}
            onClick={submit}
          >
            {submitting ? '切换中…' : '确认切换'}
          </button>
        </div>
      </div>
    </div>
  );
}

/** 1:1 复刻 prototype_01 中央地图 SVG。 */
function CockpitMapSvg() {
  return (
    <svg viewBox="0 0 800 600" xmlns="http://www.w3.org/2000/svg" style={{ width: '100%', height: '100%' }}>
      <defs>
        <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#2A3142" strokeWidth="0.5" />
        </pattern>
        <radialGradient id="signal" cx="50%" cy="50%">
          <stop offset="0%" stopColor="#10B981" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#10B981" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="hazard" cx="50%" cy="50%">
          <stop offset="0%" stopColor="#EF4444" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#EF4444" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="800" height="600" fill="url(#grid)" />

      <circle cx="600" cy="180" r="80" fill="url(#hazard)" />
      <text x="600" y="180" textAnchor="middle" fontSize="11" fill="#EF4444" fontWeight="600">危险区</text>

      <circle cx="200" cy="350" r="60" fill="url(#signal)" />
      <circle cx="200" cy="350" r="4" fill="#10B981" />
      <text x="200" y="375" textAnchor="middle" fontSize="10" fill="#10B981">幸存者信号</text>

      <circle cx="450" cy="420" r="50" fill="url(#signal)" />
      <circle cx="450" cy="420" r="4" fill="#10B981" />

      <rect x="160" y="280" width="120" height="120" fill="none" stroke="#3B82F6" strokeWidth="1.5" strokeDasharray="4,4" />
      <text x="220" y="275" textAnchor="middle" fontSize="10" fill="#3B82F6" fontWeight="600">T-018 · 60%</text>

      <rect x="380" y="380" width="80" height="80" fill="none" stroke="#F59E0B" strokeWidth="1.5" strokeDasharray="4,4" />
      <text x="420" y="375" textAnchor="middle" fontSize="10" fill="#F59E0B" fontWeight="600">T-021 · 35%</text>

      <g transform="translate(220, 320)">
        <circle r="14" fill="#1A1F2E" stroke="#60A5FA" strokeWidth="2" />
        <path d="M -6 -2 L 6 -2 L 4 4 L -4 4 Z" fill="#60A5FA" />
        <text y="28" textAnchor="middle" fontSize="9" fill="#60A5FA" fontWeight="600" fontFamily="monospace">UAV-003</text>
      </g>

      <g transform="translate(420, 410)">
        <rect x="-12" y="-12" width="24" height="24" rx="3" fill="#1A1F2E" stroke="#A78BFA" strokeWidth="2" />
        <rect x="-6" y="-6" width="12" height="12" rx="1" fill="#A78BFA" />
        <text y="28" textAnchor="middle" fontSize="9" fill="#A78BFA" fontWeight="600" fontFamily="monospace">GND-001</text>
      </g>

      <g transform="translate(580, 200)">
        <circle r="14" fill="#1A1F2E" stroke="#EF4444" strokeWidth="2" />
        <circle r="20" fill="none" stroke="#EF4444" strokeWidth="1" strokeDasharray="3,3" opacity="0.8" />
        <path d="M -6 -2 L 6 -2 L 4 4 L -4 4 Z" fill="#EF4444" />
        <text y="28" textAnchor="middle" fontSize="9" fill="#EF4444" fontWeight="600" fontFamily="monospace">UAV-007 !</text>
      </g>

      <g transform="translate(80, 80)">
        <rect x="-30" y="-15" width="60" height="30" rx="4" fill="#252B3D" stroke="#3A4258" strokeWidth="1" />
        <text y="4" textAnchor="middle" fontSize="10" fill="#9BA3B8" fontWeight="600">基地 (5)</text>
      </g>

      <g transform="translate(520, 480)">
        <polygon points="0,-12 10,8 -10,8" fill="#1A1F2E" stroke="#22D3EE" strokeWidth="2" />
        <text y="22" textAnchor="middle" fontSize="9" fill="#22D3EE" fontWeight="600" fontFamily="monospace">MAR-002</text>
      </g>

      <path d="M 80 80 Q 150 200 220 320" fill="none" stroke="#60A5FA" strokeWidth="1" strokeDasharray="2,3" opacity="0.5" />
      <path d="M 80 80 Q 250 200 420 410" fill="none" stroke="#A78BFA" strokeWidth="1" strokeDasharray="2,3" opacity="0.5" />

      <g transform="translate(40, 560)">
        <line x1="0" y1="0" x2="80" y2="0" stroke="#5C6580" strokeWidth="2" />
        <line x1="0" y1="-3" x2="0" y2="3" stroke="#5C6580" strokeWidth="2" />
        <line x1="80" y1="-3" x2="80" y2="3" stroke="#5C6580" strokeWidth="2" />
        <text x="40" y="15" textAnchor="middle" fontSize="9" fill="#5C6580">100m</text>
      </g>
    </svg>
  );
}

