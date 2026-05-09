/**
 * HITL 改派弹窗（P7.4，对照 docs/prototypes/prototype_02_reassign_dialog.html）。
 *
 * 后端：
 * - GET /tasks/{id}/assignments → 当前活跃 robot
 * - GET /robots/{id} → 详情含 latest_state（fsm/battery/position）
 * - GET /robots → 列出全部，过滤 fsm IN (IDLE, RETURNING) 作候选
 * - POST /dispatch/reassign {task_id, new_robot_id, reason}
 *
 * 候选评分：用 battery × 0.6 + (1 - distanceKm / 10) × 0.4 的简单启发式（前端展示用），
 * 真实评分由后端 RuleEngine + BidCalculator 在 reassign 时校验（>= 5 字符 reason、
 * R1-R8 硬约束、bid 重排）。前端展示只为帮助指挥员快速选择，不替代后端决策。
 */
import { ArrowRight, Check, Cpu, Hand, Pencil, Plane, Bot, Anchor, Replace, ShieldCheck, X, Battery } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { reassignTask } from '@/api/dispatch';
import { getRobot, listRobots, type FsmState, type RobotRead, type RobotStateRead } from '@/api/robots';
import { listTaskAssignments, type TaskRead } from '@/api/tasks';

interface Props {
  open: boolean;
  task: TaskRead | null;
  onClose: () => void;
  onSuccess?: (taskId: string) => void;
}

interface Candidate {
  robot: RobotRead;
  state?: RobotStateRead;
  /** 启发式评分 [0,1] */
  score: number;
  /** 距任务中心 km */
  distanceKm: number;
}

function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const toRad = (x: number) => (x * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function TypeIcon({ type, color }: { type: 'uav' | 'ugv' | 'usv'; color?: string }) {
  if (type === 'uav') return <Plane className="w-5 h-5" style={{ color: color ?? 'var(--robot-aerial)' }} />;
  if (type === 'usv') return <Anchor className="w-5 h-5" style={{ color: color ?? 'var(--robot-marine)' }} />;
  return <Bot className="w-5 h-5" style={{ color: color ?? 'var(--robot-ground)' }} />;
}

function batteryColor(pct: number) {
  if (pct >= 60) return 'var(--success)';
  if (pct >= 30) return 'var(--warning)';
  return 'var(--danger)';
}

const FSM_BADGE: Partial<Record<FsmState, { bg: string; fg: string; label: string }>> = {
  IDLE:      { bg: 'rgba(16,185,129,0.15)', fg: 'var(--success)',         label: 'IDLE' },
  EXECUTING: { bg: 'rgba(6,182,212,0.15)',  fg: 'var(--info)',            label: 'EXECUTING' },
  BIDDING:   { bg: 'rgba(245,158,11,0.15)', fg: 'var(--warning)',         label: 'BIDDING' },
  RETURNING: { bg: 'rgba(96,165,250,0.15)', fg: 'var(--robot-aerial)',    label: 'RETURNING' },
  FAULT:     { bg: 'rgba(239,68,68,0.15)',  fg: 'var(--danger)',          label: 'FAULT' },
};

export function ReassignDialog({ open, task, onClose, onSuccess }: Props) {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentRobot, setCurrentRobot] = useState<RobotRead | null>(null);
  const [currentState, setCurrentState] = useState<RobotStateRead | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // open 切换时重置状态
  useEffect(() => {
    if (!open) return;
    setReason('');
    setError(null);
    setSelectedId(null);
    setCurrentRobot(null);
    setCurrentState(null);
    setCandidates([]);
  }, [open, task?.id]);

  // 加载当前 robot + 候选列表
  useEffect(() => {
    if (!open || !task) return;
    setLoading(true);
    (async () => {
      try {
        // 1) 当前 active assignment
        const assignments = await listTaskAssignments(task.id);
        const active = assignments.find((a) => a.is_active);
        if (active) {
          const cur = await getRobot(active.robot_id);
          setCurrentRobot(cur);
          setCurrentState(cur.latest_state);
        }
        // 2) 候选：全部 active=true robots，过滤掉当前 robot
        const page = await listRobots({ page_size: 50 });
        const cp = task.target_area.center_point;
        const cands: Candidate[] = await Promise.all(
          page.items
            .filter((r) => r.is_active)
            .map(async (r): Promise<Candidate | null> => {
              if (active && r.id === active.robot_id) return null;
              const detail = await getRobot(r.id).catch(() => null);
              const st = detail?.latest_state;
              if (!st) return null;
              // 仅 IDLE / RETURNING 视作可改派
              if (st.fsm_state !== 'IDLE' && st.fsm_state !== 'RETURNING') return null;
              const distKm = haversineKm(cp.lat, cp.lng, st.position.lat, st.position.lng);
              const batteryNorm = Math.min(1, st.battery / 100);
              const distNorm = Math.max(0, 1 - distKm / 10);
              const score = batteryNorm * 0.6 + distNorm * 0.4;
              return { robot: r, state: st, score, distanceKm: distKm };
            }),
        ).then((arr) => arr.filter((x): x is Candidate => x !== null));
        cands.sort((a, b) => b.score - a.score);
        setCandidates(cands);
        if (cands.length > 0) setSelectedId(cands[0].robot.id);
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error('[reassign] load failed', e);
      } finally {
        setLoading(false);
      }
    })();
  }, [open, task]);

  const selected = useMemo(() => candidates.find((c) => c.robot.id === selectedId) ?? null, [candidates, selectedId]);

  if (!open || !task) return null;

  const handleSubmit = async () => {
    if (!selectedId) {
      setError('请先选择新机器人');
      return;
    }
    if (reason.trim().length < 5) {
      setError('改派原因至少 5 个字符');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await reassignTask({ task_id: task.id, new_robot_id: selectedId, reason: reason.trim() });
      onSuccess?.(task.id);
      onClose();
    } catch (e: unknown) {
      const m = (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? String(e);
      setError(m);
    } finally {
      setSubmitting(false);
    }
  };

  const cp = task.target_area.center_point;
  const priorityLabel = task.priority === 1 ? 'HIGH' : task.priority === 2 ? 'MED' : 'LOW';
  const priorityClass = task.priority === 1 ? 'badge-danger' : task.priority === 2 ? 'badge-warning' : 'badge-success';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(6px)' }}
      onClick={onClose}
    >
      <div
        className="relative rounded-xl overflow-hidden"
        style={{
          width: 880,
          maxWidth: '95vw',
          maxHeight: '95vh',
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-default)',
          boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="px-6 py-4 flex items-center justify-between border-b shrink-0"
          style={{
            background: 'linear-gradient(90deg, rgba(245,158,11,0.15), transparent)',
            borderColor: 'var(--border-subtle)',
          }}
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'rgba(245,158,11,0.2)' }}>
              <Replace className="w-5 h-5" style={{ color: 'var(--warning)' }} />
            </div>
            <div>
              <div className="text-base font-bold flex items-center gap-2">
                人工改派机器人
                <span className="text-xs px-2 py-0.5 rounded font-semibold" style={{ background: 'var(--warning)', color: 'white' }}>
                  HITL
                </span>
              </div>
              <div className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                Human-in-the-Loop Intervention · 操作将记入审计
              </div>
            </div>
          </div>
          <button
            className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-white/5"
            style={{ color: 'var(--text-secondary)' }}
            onClick={onClose}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 overflow-y-auto scroll-thin" style={{ flex: 1 }}>
          {/* 任务信息卡 */}
          <div
            className="rounded-lg p-4 mb-5 flex items-center gap-6"
            style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}
          >
            <div className="w-12 h-12 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'rgba(239,68,68,0.15)' }}>
              <Replace className="w-6 h-6" style={{ color: 'var(--danger)' }} />
            </div>
            <div className="flex-1 grid grid-cols-4 gap-4">
              <Field label="任务编号" value={task.code} mono />
              <Field
                label="类型"
                value={
                  <span className="text-sm">
                    {task.type} <span className={`badge ${priorityClass} ml-1`}>{priorityLabel}</span>
                  </span>
                }
              />
              <Field label="进度" value={<span className="mono"><b>{Number(task.progress).toFixed(0)}%</b> · {task.status}</span>} />
              <Field
                label="目标区域"
                value={<span className="mono text-sm">({cp.lat.toFixed(3)}, {cp.lng.toFixed(3)})</span>}
              />
            </div>
          </div>

          {/* 对比区 */}
          <div className="mb-5" style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 16 }}>
            {/* 当前机器人 */}
            <div className="rounded-lg p-4" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-default)' }}>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(59,130,246,0.15)' }}>
                  <Cpu className="w-4 h-4" style={{ color: 'var(--accent-primary)' }} />
                </div>
                <div>
                  <div className="text-sm font-semibold">当前分配</div>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>算法推荐</div>
                </div>
              </div>

              {currentRobot ? (
                <div className="rounded p-3" style={{ background: 'var(--bg-tertiary)' }}>
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <TypeIcon type={currentRobot.type} />
                      <span className="text-base font-semibold mono">{currentRobot.code}</span>
                    </div>
                    {currentState && (() => {
                      const badge = FSM_BADGE[currentState.fsm_state] ?? FSM_BADGE.IDLE!;
                      return (
                        <span className="badge" style={{ background: badge.bg, color: badge.fg }}>
                          {badge.label}
                        </span>
                      );
                    })()}
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="flex items-center gap-1.5">
                      <Battery className="w-3.5 h-3.5" style={{ color: batteryColor(currentState?.battery ?? 0) }} />
                      <span className="mono">{(currentState?.battery ?? 0).toFixed(0)}%</span>
                    </div>
                    <div className="flex items-center gap-1.5" style={{ color: 'var(--text-secondary)' }}>
                      <span>能力</span>
                      <span className="mono" style={{ color: 'var(--success)' }}>
                        {currentRobot.capability.sensors.length} 项
                      </span>
                    </div>
                    <div className="col-span-2 mt-2" style={{ color: 'var(--text-secondary)' }}>
                      {currentState ? (
                        <span className="mono text-xs">
                          位置 ({currentState.position.lat.toFixed(3)}, {currentState.position.lng.toFixed(3)})
                        </span>
                      ) : '无最新状态'}
                    </div>
                  </div>
                </div>
              ) : loading ? (
                <div className="text-xs text-center py-4" style={{ color: 'var(--text-tertiary)' }}>加载中…</div>
              ) : (
                <div className="text-xs text-center py-4" style={{ color: 'var(--text-tertiary)' }}>
                  当前任务未绑定机器人（PENDING 状态）
                </div>
              )}
            </div>

            {/* 中间箭头 */}
            <div className="flex items-center justify-center">
              <div className="flex flex-col items-center gap-2 reassign-arrow">
                <div className="text-xs font-semibold" style={{ color: 'var(--warning)' }}>改派</div>
                <ArrowRight className="w-8 h-8" style={{ color: 'var(--warning)' }} />
              </div>
            </div>

            {/* 候选机器人 */}
            <div className="rounded-lg p-4" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--warning)' }}>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(245,158,11,0.2)' }}>
                  <Hand className="w-4 h-4" style={{ color: 'var(--warning)' }} />
                </div>
                <div>
                  <div className="text-sm font-semibold">选择新机器人</div>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>人工决策</div>
                </div>
              </div>

              <div className="space-y-2 overflow-y-auto scroll-thin" style={{ maxHeight: 300 }}>
                {loading && (
                  <div className="text-xs text-center py-4" style={{ color: 'var(--text-tertiary)' }}>加载中…</div>
                )}
                {!loading && candidates.length === 0 && (
                  <div className="text-xs text-center py-4" style={{ color: 'var(--text-tertiary)' }}>
                    无可用 IDLE/RETURNING 机器人
                  </div>
                )}
                {candidates.map((c) => {
                  const sel = c.robot.id === selectedId;
                  const lowBattery = (c.state?.battery ?? 0) < 30;
                  return (
                    <div
                      key={c.robot.id}
                      onClick={() => setSelectedId(c.robot.id)}
                      className="rounded p-3 flex items-center gap-3 cursor-pointer transition"
                      style={{
                        background: sel ? 'rgba(245,158,11,0.1)' : 'var(--bg-tertiary)',
                        border: `1px solid ${sel ? 'var(--warning)' : 'var(--border-default)'}`,
                        boxShadow: sel ? '0 0 0 1px var(--warning), 0 0 16px rgba(245,158,11,0.2)' : undefined,
                        opacity: lowBattery ? 0.7 : 1,
                      }}
                    >
                      <div
                        className="w-4 h-4 rounded-full flex items-center justify-center shrink-0"
                        style={{
                          background: sel ? 'var(--warning)' : 'transparent',
                          border: sel ? 'none' : '2px solid var(--border-strong)',
                        }}
                      >
                        {sel && <div className="w-2 h-2 rounded-full bg-white" />}
                      </div>
                      <TypeIcon type={c.robot.type} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold mono truncate">{c.robot.code}</span>
                          <span
                            className="text-sm font-bold mono ml-2"
                            style={{ color: sel ? 'var(--warning)' : 'var(--text-secondary)' }}
                          >
                            {c.score.toFixed(2)}
                          </span>
                        </div>
                        <div className="text-xs mt-0.5 mono" style={{ color: 'var(--text-tertiary)' }}>
                          {c.state?.battery.toFixed(0)}% · {c.distanceKm.toFixed(2)}km · {c.state?.fsm_state}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="mt-3 text-xs flex items-center gap-1.5" style={{ color: 'var(--text-tertiary)' }}>
                <span>评分 = 电量 × 0.6 + 距离权重 × 0.4（启发式预览）</span>
              </div>
            </div>
          </div>

          {/* 干预原因 */}
          <div className="mb-2">
            <div className="flex items-center gap-1.5 mb-2">
              <Pencil className="w-4 h-4" style={{ color: 'var(--warning)' }} />
              <label className="text-sm font-semibold">干预原因</label>
              <span className="text-xs" style={{ color: 'var(--danger)' }}>* 必填（≥ 5 字符）</span>
              <span className="text-xs ml-auto" style={{ color: 'var(--text-tertiary)' }}>将记入审计日志</span>
            </div>
            <textarea
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="例：UAV-003 即将进入禁飞区，UAV-007 视野更优"
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
          </div>

          {error && (
            <div
              className="mt-3 px-3 py-2 rounded text-xs"
              style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: 'var(--danger)' }}
            >
              {error}
            </div>
          )}

          {selected && (
            <div
              className="mt-3 px-3 py-2 rounded text-xs flex items-center gap-2"
              style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.3)', color: 'var(--warning)' }}
            >
              <Replace className="w-3.5 h-3.5" />
              将把任务 <b className="mono">{task.code}</b> 改派到 <b className="mono">{selected.robot.code}</b>
              （后端会按 R1-R8 硬约束重新校验，不通过返回 409_ROBOT_INELIGIBLE_001）
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          className="px-6 py-4 flex items-center justify-between border-t shrink-0"
          style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border-subtle)' }}
        >
          <div className="text-xs flex items-center gap-2" style={{ color: 'var(--text-tertiary)' }}>
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>本次操作将记入 human_interventions 表 (intervention_type=reassign)</span>
          </div>
          <div className="flex gap-3">
            <button
              className="px-6 py-2 rounded-lg text-sm cursor-pointer transition"
              style={{ background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border-default)' }}
              onClick={onClose}
              disabled={submitting}
            >
              取消
            </button>
            <button
              className="px-6 py-2 rounded-lg text-sm font-semibold cursor-pointer flex items-center gap-2 transition"
              style={{
                background: 'var(--warning)',
                color: 'white',
                border: 'none',
                boxShadow: '0 0 16px rgba(245,158,11,0.4)',
                opacity: submitting || !selectedId ? 0.5 : 1,
              }}
              disabled={submitting || !selectedId}
              onClick={handleSubmit}
            >
              <Check className="w-4 h-4" />
              {submitting ? '改派中…' : '确认改派'}
            </button>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes reassign-arrow-pulse {
          0%, 100% { transform: translateX(0); opacity: 0.7; }
          50% { transform: translateX(4px); opacity: 1; }
        }
        .reassign-arrow {
          animation: reassign-arrow-pulse 2s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-xs mb-0.5" style={{ color: 'var(--text-tertiary)' }}>{label}</div>
      <div className={`text-sm ${mono ? 'mono font-semibold' : ''}`}>{value}</div>
    </div>
  );
}
