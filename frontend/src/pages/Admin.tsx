import {
  Anchor,
  Bot,
  CheckCircle2,
  Database,
  Download,
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
  ShieldCheck,
  Trash2,
  Upload,
  Users,
} from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { listAlerts, type AlertRead } from '@/api/alerts';
import { listReplaySessions, type ReplaySessionRead } from '@/api/replay';
import {
  createRobot,
  deleteRobot,
  listRobots,
  updateRobot,
  type RobotCapability,
  type RobotCreatePayload,
  type RobotRead,
  type RobotType,
} from '@/api/robots';
import { listTasks, type TaskRead } from '@/api/tasks';
import { AppShell } from '@/components/common/AppShell';

const TYPE_LABEL: Record<RobotType, string> = { uav: 'AERIAL', ugv: 'GROUND', usv: 'MARINE' };
const TYPE_COLOR: Record<RobotType, string> = { uav: 'var(--robot-aerial)', ugv: 'var(--robot-ground)', usv: 'var(--robot-marine)' };
const TYPE_BG: Record<RobotType, string> = { uav: 'rgba(96,165,250,0.15)', ugv: 'rgba(167,139,250,0.15)', usv: 'rgba(34,211,238,0.15)' };

type MenuKey = 'robots' | 'users' | 'roles' | 'audit' | 'scenarios' | 'config';

const MENU_ITEMS: Array<{ k: MenuKey; label: string; icon: ReactNode; tag?: string; tone?: string }> = [
  { k: 'robots', label: '机器人注册', icon: <Bot className="w-4 h-4" /> },
  { k: 'users', label: '用户管理', icon: <Users className="w-4 h-4" />, tag: '3' },
  { k: 'roles', label: '角色权限', icon: <KeyRound className="w-4 h-4" />, tag: '3' },
  { k: 'audit', label: '审计日志', icon: <FileText className="w-4 h-4" />, tone: 'var(--warning)' },
  { k: 'scenarios', label: '场景剧本', icon: <Map className="w-4 h-4" /> },
  { k: 'config', label: '系统配置', icon: <Settings2 className="w-4 h-4" /> },
];

const USERS = [
  { username: 'commander001', name: '现场指挥员', role: 'commander', status: '启用', lastLogin: '2026-05-10 09:32' },
  { username: 'admin001', name: '系统管理员', role: 'admin', status: '启用', lastLogin: '2026-05-10 08:41' },
  { username: 'system', name: '系统自动化账户', role: 'admin', status: '锁定', lastLogin: '后台任务' },
];

const ROLES = [
  { name: 'commander', desc: '指挥员，可创建任务、改派、召回、处理告警', perms: ['task:create', 'robot:reassign', 'robot:recall', 'alert:handle', 'replay:read'] },
  { name: 'admin', desc: '管理员，可维护系统配置、用户、机器人和审计数据', perms: ['system:admin', 'user:manage', 'robot:manage', 'alert:handle', 'replay:read'] },
  { name: 'observer', desc: '观察员，只读查看态势、黑板、告警和复盘', perms: ['task:read', 'robot:read', 'blackboard:read', 'alert:read', 'replay:read'] },
];

const SCENARIOS = [
  { name: '6级地震废墟搜救', type: 'earthquake', robots: 25, tasks: 30, status: '当前默认' },
  { name: '森林火灾监测', type: 'fire', robots: 18, tasks: 20, status: '备用' },
];

export function Admin() {
  const [menu, setMenu] = useState<MenuKey>('robots');
  const [robotTotal, setRobotTotal] = useState(0);
  const [alertTotal, setAlertTotal] = useState(0);

  useEffect(() => {
    listRobots({ page: 1, page_size: 1, only_active: false }).then((p) => setRobotTotal(p.total)).catch(() => setRobotTotal(25));
    listAlerts({ page: 1, page_size: 1 }).then((p) => setAlertTotal(p.total)).catch(() => setAlertTotal(0));
  }, []);

  return (
    <AppShell>
      <div className="flex" style={{ minHeight: 'calc(100vh - 56px)' }}>
        <aside className="panel my-3 ml-3 flex flex-col p-3 rounded-lg shrink-0" style={{ width: 240 }}>
          <div className="text-xs font-semibold mb-3 px-2" style={{ color: 'var(--text-tertiary)' }}>系统配置</div>
          <nav className="space-y-1">
            {MENU_ITEMS.map((it) => {
              const active = it.k === menu;
              const tag = it.k === 'robots' ? String(robotTotal || 25) : it.k === 'audit' ? String(alertTotal) : it.tag;
              return (
                <button
                  key={it.k}
                  onClick={() => setMenu(it.k)}
                  className="w-full px-4 py-2.5 rounded-md cursor-pointer flex items-center gap-2.5 text-sm transition"
                  style={{
                    background: active ? 'var(--accent-primary)' : 'transparent',
                    color: active ? 'white' : (it.tone ?? 'var(--text-primary)'),
                  }}
                >
                  {it.icon}
                  <span className="flex-1 text-left">{it.label}</span>
                  {tag && <span className="text-xs mono" style={{ color: active ? 'rgba(255,255,255,0.85)' : 'var(--text-tertiary)' }}>{tag}</span>}
                </button>
              );
            })}
          </nav>

          <div className="mt-auto pt-4 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="px-3 py-3 rounded-lg text-xs" style={{ background: 'var(--bg-tertiary)' }}>
              <div className="font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>系统信息</div>
              <InfoLine label="版本" value="v1.0.0" />
              <InfoLine label="API 状态" value="在线" valueColor="var(--success)" />
              <InfoLine label="DB 端口" value="5433" />
            </div>
          </div>
        </aside>

        <main className="flex-1 p-3 flex flex-col gap-3 overflow-hidden">
          {menu === 'robots' && <RobotsPanel />}
          {menu === 'users' && <UsersPanel />}
          {menu === 'roles' && <RolesPanel />}
          {menu === 'audit' && <AuditPanel />}
          {menu === 'scenarios' && <ScenariosPanel />}
          {menu === 'config' && <ConfigPanel />}
        </main>
      </div>
    </AppShell>
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
  const [editing, setEditing] = useState<RobotRead | null>(null);
  const [creating, setCreating] = useState(false);

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

  const handleToggleActive = async (r: RobotRead) => {
    try {
      await updateRobot(r.id, { is_active: !r.is_active });
      refresh();
    } catch (e: unknown) {
      const m = (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? String(e);
      alert(`操作失败：${m}`);
    }
  };

  const handleDelete = async (r: RobotRead) => {
    if (!window.confirm(`确认软删除 ${r.code} (${r.name})？\n（is_active=FALSE，如有活跃任务将返回 409）`)) return;
    try {
      await deleteRobot(r.id);
      refresh();
    } catch (e: unknown) {
      const m = (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? String(e);
      alert(`删除失败：${m}`);
    }
  };

  const handleBatchToggle = async (toActive: boolean) => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    if (!window.confirm(`确认对 ${ids.length} 台机器人执行${toActive ? '启用' : '停用'}？`)) return;
    let failed = 0;
    for (const id of ids) {
      try {
        await updateRobot(id, { is_active: toActive });
      } catch {
        failed += 1;
      }
    }
    if (failed > 0) alert(`完成，${failed}/${ids.length} 失败`);
    setSelected(new Set());
    refresh();
  };

  const handleBatchDelete = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    if (!window.confirm(`确认软删除 ${ids.length} 台机器人？`)) return;
    let failed = 0;
    for (const id of ids) {
      try {
        await deleteRobot(id);
      } catch {
        failed += 1;
      }
    }
    if (failed > 0) alert(`完成，${failed}/${ids.length} 失败`);
    setSelected(new Set());
    refresh();
  };

  const stats = useMemo(() => {
    const uav = items.filter((r) => r.type === 'uav').length;
    const ugv = items.filter((r) => r.type === 'ugv').length;
    const usv = items.filter((r) => r.type === 'usv').length;
    return { uav, ugv, usv };
  }, [items]);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <>
      <PageTitle title="机器人注册" trail="管理后台 / 机器人注册">
        <button
          className="btn-ghost flex items-center gap-1.5"
          title="批量导入需要 CSV 解析（P8 实装）"
          disabled
        >
          <Upload className="w-3.5 h-3.5" /> 批量导入
        </button>
        <button
          className="btn-primary flex items-center gap-1.5"
          style={{ padding: '8px 16px', fontSize: 13, fontWeight: 600 }}
          onClick={() => setCreating(true)}
        >
          <Plus className="w-4 h-4" /> 注册新机器人
        </button>
      </PageTitle>

      <div className="grid grid-cols-4 gap-3">
        <StatCard icon={<Bot />} label="总数" value={total} color="var(--accent-primary)" bg="rgba(59,130,246,0.15)" />
        <StatCard icon={<Plane />} label="无人机" value={stats.uav} color={TYPE_COLOR.uav} bg={TYPE_BG.uav} />
        <StatCard icon={<Bot />} label="地面机器人" value={stats.ugv} color={TYPE_COLOR.ugv} bg={TYPE_BG.ugv} />
        <StatCard icon={<Anchor />} label="水面机器人" value={stats.usv} color={TYPE_COLOR.usv} bg={TYPE_BG.usv} />
      </div>

      <div className="panel flex-1 flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b flex items-center gap-3" style={{ borderColor: 'var(--border-subtle)' }}>
          <SearchBox value={search} onChange={(v) => { setPage(1); setSearch(v); }} placeholder="搜索编号 / 名称 / 型号..." />
          <select className="px-3 py-2 text-sm rounded" style={controlStyle} value={type} onChange={(e) => { setPage(1); setType(e.target.value as RobotType | ''); }}>
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

        <div className="flex-1 overflow-auto scroll-thin">
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
              {loading && <tr><td colSpan={10} className="text-center text-xs py-6" style={{ color: 'var(--text-tertiary)' }}>加载中...</td></tr>}
              {!loading && items.length === 0 && <tr><td colSpan={10} className="text-center text-xs py-6" style={{ color: 'var(--text-tertiary)' }}>暂无机器人</td></tr>}
              {items.map((r) => (
                <tr key={r.id} className={!r.is_active ? 'opacity-60' : ''}>
                  <td><input type="checkbox" checked={selected.has(r.id)} onChange={() => setSelected(toggleSet(selected, r.id))} /></td>
                  <td className="mono font-semibold">{r.code}</td>
                  <td>{r.name}</td>
                  <td><span className="badge" style={{ background: TYPE_BG[r.type], color: TYPE_COLOR[r.type] }}>{TYPE_LABEL[r.type]}</span></td>
                  <td className="mono text-xs" style={{ color: 'var(--text-secondary)' }}>{r.model ?? '-'}</td>
                  <td><code className="px-2 py-0.5 rounded text-xs" style={{ background: 'var(--bg-tertiary)' }}>{capabilityPreview(r)}</code></td>
                  <td className="text-xs" style={{ color: 'var(--text-secondary)' }}>{r.group_id?.slice(0, 8) ?? '-'}</td>
                  <td>{r.is_active ? <span className="badge badge-success">● 启用</span> : <span className="badge badge-danger">● 停用</span>}</td>
                  <td className="mono text-xs" style={{ color: 'var(--text-tertiary)' }}>{r.created_at.slice(0, 10)}</td>
                  <td style={{ textAlign: 'right' }}>
                    <button className="btn-icon" title="编辑" onClick={() => setEditing(r)}>
                      <Edit2 className="w-4 h-4" style={{ color: 'var(--accent-primary)' }} />
                    </button>
                    <button
                      className="btn-icon"
                      title={r.is_active ? '停用' : '启用'}
                      onClick={() => handleToggleActive(r)}
                    >
                      <Power className="w-4 h-4" style={{ color: r.is_active ? 'var(--text-secondary)' : 'var(--success)' }} />
                    </button>
                    <button className="btn-icon" title="软删除" onClick={() => handleDelete(r)}>
                      <Trash2 className="w-4 h-4" style={{ color: 'var(--danger)' }} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <TableFooter
          selected={selected.size}
          total={total}
          page={page}
          totalPages={totalPages}
          onPrev={() => setPage((p) => Math.max(1, p - 1))}
          onNext={() => setPage((p) => Math.min(totalPages, p + 1))}
          onBatchEnable={() => handleBatchToggle(true)}
          onBatchDisable={() => handleBatchToggle(false)}
          onBatchDelete={handleBatchDelete}
        />
      </div>

      {(creating || editing) && (
        <RobotEditDialog
          robot={editing}
          onClose={() => { setCreating(false); setEditing(null); }}
          onSaved={() => { setCreating(false); setEditing(null); refresh(); }}
        />
      )}
    </>
  );
}

function RobotEditDialog({
  robot,
  onClose,
  onSaved,
}: {
  robot: RobotRead | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = robot !== null;
  const [code, setCode] = useState(robot?.code ?? '');
  const [name, setName] = useState(robot?.name ?? '');
  const [type, setType] = useState<RobotType>(robot?.type ?? 'uav');
  const [model, setModel] = useState(robot?.model ?? '');
  const [sensors, setSensors] = useState((robot?.capability.sensors ?? ['camera_4k']).join(','));
  const [payloads, setPayloads] = useState((robot?.capability.payloads ?? []).join(','));
  const [maxSpeed, setMaxSpeed] = useState(robot?.capability.max_speed_mps ?? 12);
  const [maxBattery, setMaxBattery] = useState(robot?.capability.max_battery_min ?? 30);
  const [maxRange, setMaxRange] = useState(robot?.capability.max_range_km ?? 8);
  const [hasYolo, setHasYolo] = useState(robot?.capability.has_yolo ?? true);
  const [weight, setWeight] = useState(robot?.capability.weight_kg ?? 5);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    if (!isEdit && code.trim().length < 2) {
      setError('编号至少 2 字符');
      return;
    }
    if (name.trim().length < 1) {
      setError('名称必填');
      return;
    }
    const cap: RobotCapability = {
      sensors: sensors.split(',').map((s) => s.trim()).filter(Boolean),
      payloads: payloads.split(',').map((s) => s.trim()).filter(Boolean),
      max_speed_mps: maxSpeed,
      max_battery_min: maxBattery,
      max_range_km: maxRange,
      has_yolo: hasYolo,
      weight_kg: weight,
    };
    setSubmitting(true);
    try {
      if (isEdit && robot) {
        await updateRobot(robot.id, { name: name.trim(), model: model.trim() || null, capability: cap });
      } else {
        const payload: RobotCreatePayload = {
          code: code.trim(),
          name: name.trim(),
          type,
          model: model.trim() || null,
          capability: cap,
        };
        await createRobot(payload);
      }
      onSaved();
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
        className="rounded-xl p-6 overflow-y-auto scroll-thin"
        style={{ width: 560, maxHeight: '90vh', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-base font-bold mb-4">{isEdit ? `编辑 ${robot?.code}` : '注册新机器人'}</div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="编号 *" disabled={isEdit}>
            <input className="input-field" value={code} disabled={isEdit} onChange={(e) => setCode(e.target.value)} placeholder="例 UAV-008" />
          </Field>
          <Field label="名称 *">
            <input className="input-field" value={name} onChange={(e) => setName(e.target.value)} placeholder="例 巡查 8 号" />
          </Field>
          <Field label="类型 *" disabled={isEdit}>
            <select className="input-field" value={type} disabled={isEdit} onChange={(e) => setType(e.target.value as RobotType)}>
              <option value="uav">无人机</option>
              <option value="ugv">地面</option>
              <option value="usv">水面</option>
            </select>
          </Field>
          <Field label="型号">
            <input className="input-field" value={model} onChange={(e) => setModel(e.target.value)} placeholder="例 DJI-Matrice-300" />
          </Field>
        </div>

        <div className="text-xs uppercase tracking-wider mt-4 mb-2" style={{ color: 'var(--text-tertiary)' }}>能力</div>
        <Field label="传感器（逗号分隔）">
          <input className="input-field" value={sensors} onChange={(e) => setSensors(e.target.value)} placeholder="camera_4k,thermal" />
        </Field>
        <Field label="负载（逗号分隔）">
          <input className="input-field" value={payloads} onChange={(e) => setPayloads(e.target.value)} placeholder="rescue_kit" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="最大速度 (m/s)">
            <input className="input-field" type="number" value={maxSpeed} onChange={(e) => setMaxSpeed(parseFloat(e.target.value) || 0)} />
          </Field>
          <Field label="最大续航 (分钟)">
            <input className="input-field" type="number" value={maxBattery} onChange={(e) => setMaxBattery(parseFloat(e.target.value) || 0)} />
          </Field>
          <Field label="最大航程 (km)">
            <input className="input-field" type="number" value={maxRange} onChange={(e) => setMaxRange(parseFloat(e.target.value) || 0)} />
          </Field>
          <Field label="重量 (kg)">
            <input className="input-field" type="number" value={weight} onChange={(e) => setWeight(parseFloat(e.target.value) || 0)} />
          </Field>
        </div>
        <label className="flex items-center gap-2 mt-3 text-sm cursor-pointer">
          <input type="checkbox" checked={hasYolo} onChange={(e) => setHasYolo(e.target.checked)} />
          支持 YOLO 视觉感知
        </label>

        {error && (
          <div className="mt-3 px-3 py-2 rounded text-xs" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: 'var(--danger)' }}>
            {error}
          </div>
        )}

        <div className="flex gap-2 mt-5">
          <button className="btn-ghost flex-1" onClick={onClose}>取消</button>
          <button className="btn-primary flex-1" disabled={submitting} onClick={handleSubmit}>
            {submitting ? '保存中…' : isEdit ? '保存修改' : '创建'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children, disabled }: { label: string; children: React.ReactNode; disabled?: boolean }) {
  return (
    <div className="mb-3" style={{ opacity: disabled ? 0.6 : 1 }}>
      <label className="text-xs font-semibold mb-1.5 block" style={{ color: 'var(--text-secondary)' }}>
        {label}
      </label>
      {children}
    </div>
  );
}

function UsersPanel() {
  return (
    <>
      <PageTitle title="用户管理" trail="管理后台 / 用户管理">
        <button className="btn-primary flex items-center gap-1.5" disabled title="后端尚未开放 /users CRUD（P8 实装）">
          <Plus className="w-4 h-4" /> 新建用户
        </button>
      </PageTitle>
      <ReadOnlyNotice text="该面板展示静态种子用户（commander001 / admin001 / system）。后端 /users CRUD 端点未实现，新建/编辑/删除按钮在 P8 接入。" />
      <div className="grid grid-cols-4 gap-3">
        <StatCard icon={<Users />} label="用户总数" value={USERS.length} color="var(--accent-primary)" bg="rgba(59,130,246,0.15)" />
        <StatCard icon={<ShieldCheck />} label="管理员" value={1} color="var(--warning)" bg="rgba(245,158,11,0.15)" />
        <StatCard icon={<CheckCircle2 />} label="启用账号" value={2} color="var(--success)" bg="rgba(16,185,129,0.15)" />
        <StatCard icon={<Database />} label="系统账号" value={1} color="var(--info)" bg="rgba(6,182,212,0.15)" />
      </div>
      <SimpleTable headers={['用户名', '显示名', '角色', '状态', '最后登录', '操作']}>
        {USERS.map((u) => (
          <tr key={u.username}>
            <td className="mono font-semibold">{u.username}</td>
            <td>{u.name}</td>
            <td><span className="badge badge-info">{u.role}</span></td>
            <td><span className={u.status === '启用' ? 'badge badge-success' : 'badge badge-warning'}>● {u.status}</span></td>
            <td className="mono text-xs" style={{ color: 'var(--text-secondary)' }}>{u.lastLogin}</td>
            <td><button className="btn-ghost" disabled title="P8 实装">编辑权限</button></td>
          </tr>
        ))}
      </SimpleTable>
    </>
  );
}

function RolesPanel() {
  return (
    <>
      <PageTitle title="角色权限" trail="管理后台 / 角色权限">
        <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>只读 · 角色定义在 BUSINESS_RULES §5</span>
      </PageTitle>
      <ReadOnlyNotice text="角色权限按 BUSINESS_RULES §5 静态定义，已硬编码在后端 RBAC（require_permission 装饰器），不支持运行时修改。" />
      <div className="grid grid-cols-3 gap-3">
        {ROLES.map((r) => (
          <div className="panel p-4" key={r.name}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-base font-semibold mono">{r.name}</span>
              <span className="badge badge-info">{r.perms.length} 权限</span>
            </div>
            <p className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>{r.desc}</p>
            <div className="flex flex-wrap gap-2">
              {r.perms.map((p) => <code key={p} className="px-2 py-1 rounded text-xs" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>{p}</code>)}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function AuditPanel() {
  const [alerts, setAlerts] = useState<AlertRead[]>([]);
  const [tasks, setTasks] = useState<TaskRead[]>([]);
  const [sessions, setSessions] = useState<ReplaySessionRead[]>([]);

  useEffect(() => {
    listAlerts({ page: 1, page_size: 8 }).then((p) => setAlerts(p.items)).catch(() => setAlerts([]));
    listTasks({ page: 1, page_size: 5 }).then((p) => setTasks(p.items)).catch(() => setTasks([]));
    listReplaySessions({ page: 1, page_size: 5 }).then((p) => setSessions(p.items)).catch(() => setSessions([]));
  }, []);

  const auditRows = [
    ...alerts.map((a) => ({ time: a.raised_at, type: '告警', actor: a.source, detail: `${a.code} ${a.message}`, tone: a.severity === 'critical' ? 'badge-danger' : 'badge-warning' })),
    ...tasks.map((t) => ({ time: t.created_at, type: '任务', actor: 'commander', detail: `${t.code} ${t.name} / ${t.status}`, tone: 'badge-info' })),
    ...sessions.map((s) => ({ time: s.created_at, type: '复盘', actor: 'system', detail: `${s.name} ${s.algorithm}`, tone: 'badge-success' })),
  ].sort((a, b) => Date.parse(b.time) - Date.parse(a.time)).slice(0, 12);

  return (
    <>
      <PageTitle title="审计日志" trail="管理后台 / 审计日志">
        <button
          className="btn-ghost flex items-center gap-1.5"
          onClick={() => exportAuditCsv(auditRows)}
          disabled={auditRows.length === 0}
        >
          <Download className="w-3.5 h-3.5" /> 导出 CSV
        </button>
      </PageTitle>
      <ReadOnlyNotice text="审计聚合页面 ── 数据由 /alerts / /tasks / /replay/sessions 三个端点合并；human_interventions 详细日志在 P8 提供专用查询接口。" />
      <SimpleTable headers={['时间', '类型', '操作者', '审计详情', '结果']}>
        {auditRows.map((r, i) => (
          <tr key={`${r.time}-${i}`}>
            <td className="mono text-xs" style={{ color: 'var(--text-tertiary)' }}>{new Date(r.time).toLocaleString('zh-CN', { hour12: false })}</td>
            <td><span className={`badge ${r.tone}`}>{r.type}</span></td>
            <td className="mono">{r.actor}</td>
            <td>{r.detail}</td>
            <td><span className="badge badge-success">已记录</span></td>
          </tr>
        ))}
        {auditRows.length === 0 && <tr><td colSpan={5} className="text-center text-xs py-8" style={{ color: 'var(--text-tertiary)' }}>暂无审计数据</td></tr>}
      </SimpleTable>
    </>
  );
}

function ScenariosPanel() {
  return (
    <>
      <PageTitle title="场景剧本" trail="管理后台 / 场景剧本">
        <button className="btn-primary flex items-center gap-1.5" disabled title="后端 scenarios 表未开放 CRUD（P8）">
          <Plus className="w-4 h-4" /> 新建剧本
        </button>
      </PageTitle>
      <ReadOnlyNotice text="场景由 backend/scripts seed 写入，运行时切换通过演练会话 (replay sessions) 体现。CRUD 接口在 P8 实装。" />
      <div className="grid grid-cols-2 gap-3">
        {SCENARIOS.map((s) => (
          <div className="panel p-4" key={s.name}>
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="text-lg font-semibold">{s.name}</div>
                <div className="text-xs mono mt-1" style={{ color: 'var(--text-tertiary)' }}>{s.type}</div>
              </div>
              <span className={s.status === '当前默认' ? 'badge badge-success' : 'badge'} style={s.status === '当前默认' ? undefined : { background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>{s.status}</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <MiniMetric label="机器人编队" value={`${s.robots} 台`} />
              <MiniMetric label="任务规模" value={`${s.tasks} 个`} />
            </div>
            <div className="mt-4 h-40 rounded relative overflow-hidden" style={{ background: 'radial-gradient(circle at 45% 50%, #252B3D 0%, #111827 70%)', border: '1px solid var(--border-subtle)' }}>
              <svg viewBox="0 0 420 160" className="w-full h-full">
                <path d="M30 120 C80 70 130 84 180 48 C230 18 292 42 374 96" fill="none" stroke="#3B82F6" strokeWidth="2" strokeDasharray="7 6" />
                <circle cx="270" cy="70" r="38" fill="rgba(239,68,68,0.14)" stroke="#EF4444" strokeDasharray="5 4" />
                <circle cx="130" cy="96" r="26" fill="rgba(245,158,11,0.16)" stroke="#F59E0B" strokeDasharray="5 4" />
              </svg>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function ConfigPanel() {
  const configs = [
    ['调度算法', 'AUCTION_HUNGARIAN', '通过指挥工作台「切换算法」按钮 HITL 修改（POST /dispatch/algorithm）'],
    ['状态推送频率', '1 Hz', '后端 .env STATE_PUSH_INTERVAL 静态配置'],
    ['告警扫描间隔', '60 sec', 'SLA 扫描定时任务，运行时不可改'],
    ['复盘采样频率', '1 Hz', 'Replay SnapshotRecorder 内置'],
    ['Mock 视觉流', '关闭', '由后端 .env MOCK_PERCEPTION_ENABLED 控制，运行时不可改'],
    ['JWT 有效期', '24 h', '后端 .env JWT_EXPIRES_IN 静态配置'],
  ];
  return (
    <>
      <PageTitle title="系统配置" trail="管理后台 / 系统配置">
        <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>只读 · 由后端 .env / settings 决定</span>
      </PageTitle>
      <ReadOnlyNotice text="此处展示运行时关键配置，仅有「调度算法」可通过工作台 HITL 修改；其他项需重启后端才能生效。" />
      <div className="grid grid-cols-2 gap-3">
        {configs.map(([k, v, desc]) => (
          <div key={k} className="panel p-4 flex items-center justify-between gap-4">
            <div>
              <div className="font-semibold">{k}</div>
              <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{desc}</div>
            </div>
            <input
              className="px-3 py-2 rounded text-sm mono text-right"
              style={{ ...controlStyle, width: 180, opacity: 0.6 }}
              value={v}
              readOnly
            />
          </div>
        ))}
      </div>
    </>
  );
}

function ReadOnlyNotice({ text }: { text: string }) {
  return (
    <div
      className="panel p-3 flex items-start gap-2 text-xs"
      style={{
        background: 'rgba(245,158,11,0.08)',
        borderColor: 'rgba(245,158,11,0.3)',
        color: 'var(--text-secondary)',
      }}
    >
      <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5" style={{ color: 'var(--warning)' }} />
      <span>{text}</span>
    </div>
  );
}

function PageTitle({ title, trail, children }: { title: string; trail: string; children?: ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{trail}</div>
        <h1 className="text-xl font-bold mt-1">{title}</h1>
      </div>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}

function StatCard({ icon, label, value, color, bg }: { icon: ReactNode; label: string; value: number; color: string; bg: string }) {
  return (
    <div className="panel p-4 flex items-center gap-3">
      <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: bg, color }}>{icon}</div>
      <div>
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</div>
        <div className="text-xl font-bold mono" style={{ color }}>{value}</div>
      </div>
    </div>
  );
}

function SimpleTable({ headers, children }: { headers: string[]; children: ReactNode }) {
  return (
    <div className="panel flex-1 overflow-auto scroll-thin">
      <table className="app-table">
        <thead><tr>{headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div className="relative" style={{ flex: 1, maxWidth: 320 }}>
      <Search className="w-4 h-4 absolute left-3 top-2.5" style={{ color: 'var(--text-tertiary)' }} />
      <input className="w-full pl-9 pr-3 py-2 text-sm rounded" style={controlStyle} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
    </div>
  );
}

function TableFooter({
  selected, total, page, totalPages, onPrev, onNext,
  onBatchEnable, onBatchDisable, onBatchDelete,
}: {
  selected: number; total: number; page: number; totalPages: number;
  onPrev: () => void; onNext: () => void;
  onBatchEnable?: () => void; onBatchDisable?: () => void; onBatchDelete?: () => void;
}) {
  return (
    <div className="px-4 py-3 border-t flex items-center justify-between" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="flex items-center gap-3">
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>已选 <span className="font-bold text-white">{selected}</span> 条 | 共 {total} 条</span>
        <button className="btn-ghost" style={{ padding: '4px 10px' }} disabled={selected === 0} onClick={onBatchEnable}>启用</button>
        <button className="btn-ghost" style={{ padding: '4px 10px' }} disabled={selected === 0} onClick={onBatchDisable}>禁用</button>
        <button className="btn-ghost" style={{ padding: '4px 10px', color: 'var(--danger)', borderColor: 'var(--danger)' }} disabled={selected === 0} onClick={onBatchDelete}>删除</button>
      </div>
      <div className="flex items-center gap-3 text-xs">
        <button className="btn-ghost" style={{ padding: '4px 10px' }} disabled={page <= 1} onClick={onPrev}>‹</button>
        <span>第 {page} / {totalPages} 页</span>
        <button className="btn-ghost" style={{ padding: '4px 10px' }} disabled={page >= totalPages} onClick={onNext}>›</button>
      </div>
    </div>
  );
}

function InfoLine({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div className="flex justify-between py-0.5" style={{ color: 'var(--text-tertiary)' }}>
      <span>{label}</span>
      <span className="mono" style={{ color: valueColor }}>{value}</span>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded p-3" style={{ background: 'var(--bg-tertiary)' }}>
      <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{label}</div>
      <div className="text-lg font-bold mono">{value}</div>
    </div>
  );
}

function toggleSet(source: Set<string>, id: string) {
  const next = new Set(source);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

function capabilityPreview(robot: RobotRead) {
  const sensors = robot.capability.sensors ?? [];
  return `{${sensors.slice(0, 2).join(', ')}${sensors.length > 2 ? ', ...' : ''}}`;
}

function exportAuditCsv(rows: Array<{ time: string; type: string; actor: string; detail: string }>) {
  if (rows.length === 0) return;
  const escape = (v: unknown) => {
    const s = v == null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [
    'time,type,actor,detail',
    ...rows.map((r) => [r.time, r.type, r.actor, r.detail].map(escape).join(',')),
  ];
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `audit-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

const controlStyle = {
  background: 'var(--bg-tertiary)',
  border: '1px solid var(--border-default)',
  color: 'var(--text-primary)',
};
