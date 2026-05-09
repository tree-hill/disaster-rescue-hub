/**
 * 指挥工作台（对照 docs/prototypes/prototype_01_cockpit.html）。
 *
 * 三栏布局：
 * - 左 w=72：机器人编队卡片（类型 Tab + 搜索 + 卡片列表）
 * - 中 flex-1：态势地图（SVG 网格 + 危险区 + 幸存者信号 + 任务网格 + 机器人）
 * - 右 w=80：任务 / 告警 / 日志 Tab + 创建按钮 + 任务卡片列表 + 底部告警
 *
 * 数据接入（已对齐 P7.1 后端）：
 * - KPI 顶条：GET /situation/kpi（命中后端 KPIAggregator 缓存）+ WS commander 房间订阅 'kpi.snapshot' 实时刷新
 *
 * 占位（后端缺 / 待 P7.4 实装）：
 * - 机器人列表 → 暂用 mock，与原型同；后续接 GET /robots（已有）
 * - 任务列表 → 暂用 mock，与原型同；后续接 GET /tasks（已有）
 * - 地图 SVG → 静态原型 SVG 直接复刻，后续 P7.3 后期接入 react-konva 真实地图
 * - 改派按钮 → onClick 暂时弹 alert（P7.4 ReassignDialog 实装）
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
  Gavel,
  Hand,
  LocateFixed,
  MapPin,
  Maximize2,
  Minus,
  Pause,
  Plane,
  Plus,
  Replace,
  RotateCcw,
  Ruler,
  Search,
  Square,
} from 'lucide-react';
import { useEffect, useState } from 'react';

import { fetchKpi, type KPISnapshot } from '@/api/situation';
import { AppShell } from '@/components/common/AppShell';
import { useWSStore } from '@/store/ws';

interface RobotMock {
  code: string;
  type: 'aerial' | 'ground' | 'marine';
  fsm: 'EXECUTING' | 'BIDDING' | 'IDLE' | 'FAULT';
  battery: number;
  detail: string;
  taskCode?: string;
}

const ROBOT_MOCKS: RobotMock[] = [
  { code: 'UAV-003', type: 'aerial', fsm: 'EXECUTING', battery: 80, detail: '→ T-018 · (123, 456)', taskCode: 'T-018' },
  { code: 'GND-001', type: 'ground', fsm: 'EXECUTING', battery: 60, detail: '→ T-021 · (89, 234)', taskCode: 'T-021' },
  { code: 'UAV-007', type: 'aerial', fsm: 'FAULT', battery: 18, detail: '低电量故障' },
  { code: 'GND-005', type: 'ground', fsm: 'IDLE', battery: 95, detail: '基地待命 · (50, 50)' },
  { code: 'MAR-002', type: 'marine', fsm: 'BIDDING', battery: 72, detail: '出价中 · (180, 320)' },
];

interface TaskMock {
  code: string;
  priority: 'HIGH' | 'MEDIUM' | 'LOW' | 'AUCTION';
  type: string;
  area: string;
  robotCode?: string;
  robotType?: 'aerial' | 'ground' | 'marine';
  progress: number;
  status: 'EXECUTING' | 'COMPLETED' | 'AUCTION';
  ageText: string;
  remainSec?: number;
}

const TASK_MOCKS: TaskMock[] = [
  { code: 'T-018', priority: 'HIGH', type: '搜救', area: '区域 (12,5)~(15,8)', robotCode: 'UAV-003', robotType: 'aerial', progress: 60, status: 'EXECUTING', ageText: '17m' },
  { code: 'T-021', priority: 'MEDIUM', type: '侦察', area: '区域 (8,3)~(10,5)', robotCode: 'GND-001', robotType: 'ground', progress: 35, status: 'EXECUTING', ageText: '42m' },
  { code: 'T-024', priority: 'AUCTION', type: '', area: '区域 (20,15)~(22,17)', progress: 0, status: 'AUCTION', ageText: '1.2s' },
];

const RECENT_ALERTS = [
  '· UAV-007 低电量 (15%)',
  '· T-018 SLA 即将超时',
  '· GND-002 通信中断 30s',
];

function robotColor(t: RobotMock['type']) {
  return t === 'aerial' ? 'var(--robot-aerial)' : t === 'ground' ? 'var(--robot-ground)' : 'var(--robot-marine)';
}

function batteryColor(pct: number) {
  if (pct >= 50) return 'var(--success)';
  if (pct >= 25) return 'var(--warning)';
  return 'var(--danger)';
}

function fsmBadge(fsm: RobotMock['fsm']) {
  if (fsm === 'EXECUTING') return 'badge-info';
  if (fsm === 'BIDDING') return 'badge-warning';
  if (fsm === 'FAULT') return 'badge-danger';
  return 'badge-success';
}

function RobotIcon({ type }: { type: RobotMock['type'] }) {
  const c = robotColor(type);
  if (type === 'aerial') return <Plane className="w-4 h-4" style={{ color: c }} />;
  if (type === 'marine') return <Anchor className="w-4 h-4" style={{ color: c }} />;
  return <Bot className="w-4 h-4" style={{ color: c }} />;
}

export function Cockpit() {
  const [kpi, setKpi] = useState<KPISnapshot | null>(null);
  const [robotTab, setRobotTab] = useState<'all' | 'aerial' | 'ground' | 'marine'>('all');
  const [rightTab, setRightTab] = useState<'tasks' | 'alerts' | 'logs'>('tasks');
  const wsConnect = useWSStore((s) => s.connect);
  const wsSubscribe = useWSStore((s) => s.subscribe);
  const wsAddListener = useWSStore((s) => s.addListener);

  // 初次拉取 KPI
  useEffect(() => {
    fetchKpi().then(setKpi).catch(() => undefined);
  }, []);

  // WS 订阅 commander → kpi.snapshot 实时刷新
  useEffect(() => {
    wsConnect();
    wsSubscribe('commander');
    const off = wsAddListener<KPISnapshot>('kpi.snapshot', (snap) => setKpi(snap));
    return off;
  }, [wsConnect, wsSubscribe, wsAddListener]);

  const filtered = ROBOT_MOCKS.filter((r) => robotTab === 'all' || r.type === robotTab);

  return (
    <AppShell fullHeight sessionInfo={
      <>
        <span>当前会话: <span className="text-white">6级地震-演练#003</span></span>
        <span className="mono" style={{ color: 'var(--text-tertiary)' }}>
          {' '}| {new Date().toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5)} | 算法: AUCTION_HUNGARIAN
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
          className="flex-1 flex items-center gap-3 px-4 py-2 rounded-lg"
          style={{
            background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.3)',
          }}
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
              <span className="text-sm font-semibold mono">Hungarian</span>
              <button className="btn-ghost" style={{ padding: '2px 8px', fontSize: 11 }}>
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
              { k: 'all' as const, label: `全部 ${ROBOT_MOCKS.length}` },
              { k: 'aerial' as const, label: '空 10' },
              { k: 'ground' as const, label: '陆 10' },
              { k: 'marine' as const, label: '水 5' },
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
            {filtered.map((r) => (
              <div
                key={r.code}
                className="rounded-lg p-3 cursor-pointer hover:opacity-90"
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
                    {r.battery}%
                  </span>
                </div>
                {r.fsm === 'FAULT' ? (
                  <button
                    className="w-full py-1 text-xs rounded font-semibold mt-2"
                    style={{ background: 'var(--danger)', color: 'white' }}
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
            <div
              className="text-center text-xs py-2"
              style={{ color: 'var(--text-tertiary)' }}
            >
              ··· 更多机器人 ···
            </div>
          </div>
          <div
            className="px-3 py-2 border-t flex gap-2"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <button className="flex-1 btn-ghost flex items-center justify-center gap-1">
              <Plus className="w-3.5 h-3.5" /> 编队
            </button>
            <button
              className="flex-1 btn-ghost flex items-center justify-center gap-1"
              style={{ color: 'var(--danger)', borderColor: 'var(--danger)' }}
            >
              <RotateCcw className="w-3.5 h-3.5" /> 全员召回
            </button>
          </div>
        </aside>

        {/* 中央地图 */}
        <section className="panel flex-1 flex flex-col overflow-hidden">
          <div
            className="px-4 py-2 border-b flex items-center justify-between"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4" />
              <span className="text-sm font-semibold">态势地图</span>
              <span className="text-xs mono" style={{ color: 'var(--text-tertiary)' }}>
                | 缩放 100% | 中心 (250, 250)
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button className="btn-ghost"><Hand className="w-3.5 h-3.5" /></button>
              <button className="btn-ghost"><Square className="w-3.5 h-3.5" /></button>
              <button className="btn-ghost"><Ruler className="w-3.5 h-3.5" /></button>
              <div className="w-px h-5 mx-1" style={{ background: 'var(--border-default)' }} />
              <button className="btn-ghost"><Minus className="w-3.5 h-3.5" /></button>
              <span className="text-xs mono px-2" style={{ color: 'var(--text-secondary)' }}>100%</span>
              <button className="btn-ghost"><Plus className="w-3.5 h-3.5" /></button>
              <button className="btn-ghost"><LocateFixed className="w-3.5 h-3.5" /></button>
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
                <span className="pulse-dot"></span>实时模式
              </span>
              <button className="btn-ghost"><Pause className="w-3.5 h-3.5" /></button>
              <button className="btn-ghost"><Camera className="w-3.5 h-3.5" /></button>
            </div>
            <button className="btn-ghost flex items-center gap-1">
              <Maximize2 className="w-3.5 h-3.5" /> 全屏
            </button>
          </div>
        </section>

        {/* 右栏 */}
        <aside className="panel w-80 flex flex-col">
          <div className="flex border-b" style={{ borderColor: 'var(--border-subtle)' }}>
            {[
              { k: 'tasks' as const, label: `任务 ${TASK_MOCKS.length}` },
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
            <button className="btn-primary w-full flex items-center justify-center gap-1.5">
              <Plus className="w-4 h-4" /> 创建救援任务
            </button>
          </div>

          {rightTab === 'tasks' && (
            <div className="flex-1 overflow-y-auto scroll-thin px-3 py-2 space-y-2.5">
              {TASK_MOCKS.map((t) => (
                <TaskCard key={t.code} task={t} />
              ))}
              <div className="text-center text-xs py-2" style={{ color: 'var(--text-tertiary)' }}>
                ··· 更多任务 ···
              </div>
            </div>
          )}
          {rightTab === 'alerts' && (
            <div className="flex-1 overflow-y-auto scroll-thin px-3 py-2">
              <div
                className="text-xs"
                style={{ color: 'var(--text-secondary)' }}
              >
                请前往 <a className="underline" href="/alerts" style={{ color: 'var(--accent-primary)' }}>告警中心</a> 查看完整列表
              </div>
            </div>
          )}
          {rightTab === 'logs' && (
            <div className="flex-1 overflow-y-auto scroll-thin px-3 py-2 text-xs"
              style={{ color: 'var(--text-tertiary)' }}>
              （日志面板占位 — 后续接入审计日志流）
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
              {RECENT_ALERTS.map((a) => (
                <div key={a}>{a}</div>
              ))}
            </div>
          </div>
        </aside>
      </main>
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

function TaskCard({ task }: { task: TaskMock }) {
  if (task.status === 'AUCTION') {
    return (
      <div
        className="rounded-lg p-3 border-2 border-dashed"
        style={{ background: 'rgba(59,130,246,0.05)', borderColor: 'var(--accent-primary)' }}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold mono">{task.code}</span>
            <span className="badge" style={{ background: 'rgba(59,130,246,0.2)', color: 'var(--accent-primary)' }}>
              拍卖中
            </span>
          </div>
          <span className="text-xs mono" style={{ color: 'var(--accent-primary)' }}>{task.ageText}</span>
        </div>
        <div className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>{task.area}</div>
        <div
          className="text-xs mb-2 flex items-center gap-1.5"
          style={{ color: 'var(--accent-primary)' }}
        >
          <Gavel className="w-3.5 h-3.5" />
          <span>5 个机器人正在出价</span>
        </div>
        <button className="w-full btn-ghost" style={{ padding: '4px 8px' }}>查看候选</button>
      </div>
    );
  }
  const sideColor = task.priority === 'HIGH' ? 'var(--danger)' : task.priority === 'MEDIUM' ? 'var(--warning)' : 'var(--success)';
  const badgeClass = task.priority === 'HIGH' ? 'badge-danger' : task.priority === 'MEDIUM' ? 'badge-warning' : 'badge-success';
  return (
    <div
      className="rounded-lg p-3"
      style={{
        background: 'var(--bg-tertiary)',
        borderLeft: `3px solid ${sideColor}`,
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold mono">{task.code}</span>
          <span className={`badge ${badgeClass}`}>{task.priority}</span>
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{task.type}</span>
        </div>
        <span className="text-xs mono" style={{ color: 'var(--text-tertiary)' }}>{task.ageText}</span>
      </div>
      <div className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>{task.area}</div>
      {task.robotCode && (
        <div className="flex items-center gap-2 text-xs mb-2">
          <RobotIcon type={task.robotType ?? 'aerial'} />
          <span className="mono">{task.robotCode}</span>
        </div>
      )}
      <div className="flex items-center gap-2 mb-2">
        <div className="flex-1 progress-bar">
          <div className="progress-fill" style={{ width: `${task.progress}%` }} />
        </div>
        <span className="text-xs mono font-semibold">{task.progress}%</span>
      </div>
      <div className="flex gap-1.5">
        <button
          className="flex-1 btn-warning flex items-center justify-center gap-1"
          style={{ padding: '4px 8px', fontSize: 12 }}
          onClick={() => alert('改派对话框 P7.4 实装')}
        >
          <Replace className="w-3 h-3 inline" /> 改派
        </button>
        <button className="btn-ghost" style={{ padding: '4px 8px' }}>取消</button>
        <button className="btn-ghost" style={{ padding: '4px 8px' }}>详情</button>
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
