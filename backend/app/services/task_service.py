"""任务业务编排层（P4.3 创建路径 + P4.4 列表 / 详情 / 更新 / 取消 / 分配查询）。

对照：
- API_SPEC §3（/tasks 全部接口）
- BUSINESS_RULES §6.3（任务类错误码：422_TASK_INVALID_AREA_001 / 409_TASK_STATUS_CONFLICT_001
  / 409_TASK_ALREADY_CANCELLED_001 / 404_TASK_NOT_FOUND_001）+ §6.5（reason 校验）
  + §2.1（状态机）+ §4.1 / §4.2（HITL cancel_task 流程）+ §7（网格分解阈值 1 km²
  + 切分粒度 500m × 500m）
- DATA_CONTRACTS §1.8（tasks）+ §1.9（task_assignments）+ §1.12 / §4.8
  （human_interventions before/after_state）+ §4.5 / §4.6（target_area /
  required_capabilities）
- WS_EVENTS §4 task.created / task.cancelled（commander 房间）

设计取舍：
- area_km2 / radius_m 的 > 0 业务校验放在 service 层，抛特化错误码
  422_TASK_INVALID_AREA_001；与 recall_service.reason min_len 抛
  422_INTERVENTION_REASON_INVALID_001 同模式（特化错误码优先于 Pydantic 通用
  422_VALIDATION_FAILED_001）。
- 任务 code 生成：`pg_advisory_xact_lock(year)` 串行化同年并发创建，再 `MAX(...)
  + 1`，UNIQUE 兜底 + 最多 3 次重试，避免长事务持锁风险。子任务 code 形式
  `T-YYYY-NNN-CC`（CC 从 01 起，宽度 2）。
- 网格分解：rectangle / polygon / circle 一律先求经纬度 bounding box，再按
  500m × 500m 平铺；polygon / circle 的「真实形状裁剪」留给 P5+ 调度算法。
  decomposition 仅当 area_km2 > 1.0 触发；切到 1×1 的退化情形（单 tile）也认为
  无需分解。
- 事件总线（P4.5）：task.created / task.cancelled 经 `app/core/event_bus.py`
  publish → `app/ws/event_bridge.py` 转推 → `push_event` → `sio.emit`。
  service 层不再直接依赖 WS 协议层；后续接审计 sink / Kafka 中继只需在
  bus.subscribe 注册新 handler。commit 之后才 publish，避免在事务回滚时已
  发布事件造成幻觉。
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    METERS_PER_DEGREE,
    RECALL_REASON_MIN_LEN,
    TASK_CHILD_CODE_SEQ_WIDTH,
    TASK_CODE_SEQ_WIDTH,
    TASK_GRID_DECOMPOSE_THRESHOLD_KM2,
    TASK_GRID_TILE_METERS,
)
from app.core.event_bus import get_event_bus
from app.core.exceptions import BusinessError
from app.models.intervention import HumanIntervention
from app.models.task import Task, TaskAssignment
from app.repositories.intervention import InterventionRepository
from app.repositories.task import TaskRepository
from app.repositories.task_assignment import TaskAssignmentRepository
from app.schemas.task import TargetArea, TaskCreate, TaskUpdate
from app.services.task_status_machine import (
    TERMINAL_TASK_STATUSES,
    transit as transit_task,
)

logger = logging.getLogger(__name__)


_INVALID_AREA = "422_TASK_INVALID_AREA_001"
_CODE_GEN_RETRY = 3


def _invalid_area(message: str, field: str = "target_area") -> BusinessError:
    return BusinessError(
        code=_INVALID_AREA,
        message=message,
        http_status=422,
        details=[{"field": field, "code": "invalid_area", "message": message}],
    )


def _not_found(task_id: UUID) -> BusinessError:
    return BusinessError(
        code="404_TASK_NOT_FOUND_001",
        message="任务不存在",
        http_status=404,
        details=[{"field": "task_id", "code": "not_found", "message": str(task_id)}],
    )


def _validate_reason(reason: str) -> None:
    """BUSINESS_RULES §4.3.1 + §6.5：reason ≥ 5 字符且非纯空白。

    特化错误码 422_INTERVENTION_REASON_INVALID_001（与 RecallService 完全一致）。
    """
    if not isinstance(reason, str) or len(reason.strip()) < RECALL_REASON_MIN_LEN:
        raise BusinessError(
            code="422_INTERVENTION_REASON_INVALID_001",
            message=f"reason 至少 {RECALL_REASON_MIN_LEN} 个非空白字符",
            http_status=422,
            details=[
                {
                    "field": "reason",
                    "code": "too_short_or_blank",
                    "message": f"strip 后长度 {len(reason.strip()) if isinstance(reason, str) else 0}",
                }
            ],
        )


def _validate_area(area: TargetArea) -> None:
    """业务层 area 校验（在 schema 校验之后、写库之前）。

    抛 422_TASK_INVALID_AREA_001：
    - area_km2 ≤ 0
    - rectangle 缺 bounds / bounds 不含 sw+ne / sw 在 ne 东北方向
    - polygon 顶点数 < 3
    - circle 缺 center 或 radius_m ≤ 0
    """
    if area.area_km2 <= 0:
        raise _invalid_area("area_km2 必须 > 0", field="target_area.area_km2")

    if area.type == "rectangle":
        b = area.bounds or {}
        sw = b.get("sw")
        ne = b.get("ne")
        if not isinstance(sw, dict) or not isinstance(ne, dict):
            raise _invalid_area(
                "rectangle 必须包含 bounds.sw 与 bounds.ne", field="target_area.bounds"
            )
        try:
            if float(sw["lat"]) >= float(ne["lat"]) or float(sw["lng"]) >= float(ne["lng"]):
                raise _invalid_area(
                    "bounds.sw 必须严格在 bounds.ne 的西南方向",
                    field="target_area.bounds",
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise _invalid_area(
                "bounds 经纬度字段缺失或类型错误", field="target_area.bounds"
            ) from exc
    elif area.type == "polygon":
        if not area.vertices or len(area.vertices) < 3:
            raise _invalid_area(
                "polygon 必须至少包含 3 个顶点", field="target_area.vertices"
            )
    elif area.type == "circle":
        if area.center is None:
            raise _invalid_area("circle 必须包含 center", field="target_area.center")
        if area.radius_m is None or area.radius_m <= 0:
            raise _invalid_area(
                "circle.radius_m 必须 > 0", field="target_area.radius_m"
            )


# ---------- 网格分解 ----------


def _bounding_box(area: TargetArea) -> tuple[float, float, float, float]:
    """返回 (sw_lat, sw_lng, ne_lat, ne_lng)。三种几何形状统一走 bbox。"""
    if area.type == "rectangle":
        b = area.bounds or {}
        sw, ne = b["sw"], b["ne"]
        return float(sw["lat"]), float(sw["lng"]), float(ne["lat"]), float(ne["lng"])
    if area.type == "polygon":
        assert area.vertices is not None
        lats = [v.lat for v in area.vertices]
        lngs = [v.lng for v in area.vertices]
        return min(lats), min(lngs), max(lats), max(lngs)
    # circle：center ± radius_m / METERS_PER_DEGREE，lng 按 cos(lat) 修正
    assert area.center is not None and area.radius_m is not None
    dlat = area.radius_m / METERS_PER_DEGREE
    cos_lat = max(math.cos(math.radians(area.center.lat)), 1e-6)
    dlng = area.radius_m / (METERS_PER_DEGREE * cos_lat)
    return (
        area.center.lat - dlat,
        area.center.lng - dlng,
        area.center.lat + dlat,
        area.center.lng + dlng,
    )


def _decompose_to_tiles(area: TargetArea) -> list[dict[str, Any]]:
    """把 target_area 切成若干 500m × 500m 的 rectangle 子区域 (JSONB 结构)。

    返回的每个 dict 与 DATA_CONTRACTS §4.5 一致：含 type/bounds/area_km2/center_point。
    若 bbox 在某轴上 < 一个 tile，则该轴退化为 1 行/列；最终 ≥ 2 个 tile 才视为有效
    分解，否则调用方应跳过分解只写父任务。
    """
    sw_lat, sw_lng, ne_lat, ne_lng = _bounding_box(area)
    lat_step = TASK_GRID_TILE_METERS / METERS_PER_DEGREE
    cos_lat = max(math.cos(math.radians((sw_lat + ne_lat) / 2)), 1e-6)
    lng_step = TASK_GRID_TILE_METERS / (METERS_PER_DEGREE * cos_lat)

    rows = max(1, math.ceil((ne_lat - sw_lat) / lat_step))
    cols = max(1, math.ceil((ne_lng - sw_lng) / lng_step))

    tiles: list[dict[str, Any]] = []
    for r in range(rows):
        tile_sw_lat = sw_lat + r * lat_step
        tile_ne_lat = min(sw_lat + (r + 1) * lat_step, ne_lat)
        for c in range(cols):
            tile_sw_lng = sw_lng + c * lng_step
            tile_ne_lng = min(sw_lng + (c + 1) * lng_step, ne_lng)
            # tile 实际尺寸（米）；最后一行/列可能 < 500m
            h_m = (tile_ne_lat - tile_sw_lat) * METERS_PER_DEGREE
            w_m = (tile_ne_lng - tile_sw_lng) * METERS_PER_DEGREE * cos_lat
            tile_area_km2 = max((h_m * w_m) / 1_000_000.0, 0.0)
            tiles.append(
                {
                    "type": "rectangle",
                    "bounds": {
                        "sw": {"lat": tile_sw_lat, "lng": tile_sw_lng},
                        "ne": {"lat": tile_ne_lat, "lng": tile_ne_lng},
                    },
                    "area_km2": round(tile_area_km2, 6),
                    "center_point": {
                        "lat": (tile_sw_lat + tile_ne_lat) / 2,
                        "lng": (tile_sw_lng + tile_ne_lng) / 2,
                    },
                }
            )
    return tiles


# ---------- 任务 code 生成 ----------


_CODE_LOCK_NAMESPACE = 0x7A5C_0001  # 任意常量，用作 advisory lock 命名空间


async def _allocate_root_code(session: AsyncSession, year: int) -> tuple[str, int]:
    """分配同年下一个 root 任务码（T-YYYY-NNN）。

    使用 `pg_advisory_xact_lock(ns, year)` 串行化同年并发分配；锁随事务释放。
    返回 (code, seq)；caller 负责把 seq 透传给子任务后缀生成。
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :y)"),
        {"ns": _CODE_LOCK_NAMESPACE, "y": year},
    )
    pattern = f"T-{year}-%"
    # 仅匹配根任务（T-YYYY-NNN），不含子任务（T-YYYY-NNN-CC，含两个连字符）
    regex = rf"^T-{year}-\d+$"
    row = await session.execute(
        text(
            "SELECT COALESCE(MAX(CAST(SUBSTRING(code FROM :re) AS INTEGER)), 0) "
            "FROM tasks WHERE code LIKE :p AND code ~ :full"
        ),
        {"re": rf"T-{year}-(\d+)$", "p": pattern, "full": regex},
    )
    max_seq = int(row.scalar_one() or 0)
    seq = max_seq + 1
    code = f"T-{year}-{str(seq).zfill(TASK_CODE_SEQ_WIDTH)}"
    return code, seq


def _child_code(parent_code: str, child_index: int) -> str:
    """T-YYYY-NNN-CC（CC 从 01 起，宽度 2，溢出按实际位数输出）。"""
    return f"{parent_code}-{str(child_index).zfill(TASK_CHILD_CODE_SEQ_WIDTH)}"


# ---------- TaskService ----------


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tasks = TaskRepository(session)
        self.assignments = TaskAssignmentRepository(session)
        self.interventions = InterventionRepository(session)

    # ---------- 读 ----------

    async def list_paginated(
        self,
        *,
        status_in: list[str] | None,
        priority: int | None,
        type_: str | None,
        created_by: UUID | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Task], int]:
        return await self.tasks.find_paginated(
            status_in=status_in,
            priority=priority,
            type_=type_,
            created_by=created_by,
            search=search,
            page=page,
            page_size=page_size,
        )

    async def get_with_assignments(
        self, task_id: UUID
    ) -> tuple[Task, list[TaskAssignment]]:
        task = await self.tasks.find_by_id(task_id)
        if task is None:
            raise _not_found(task_id)
        assignments = await self.assignments.find_by_task(task_id)
        return task, assignments

    async def list_assignments(self, task_id: UUID) -> list[TaskAssignment]:
        # 404 守卫：任务不存在直接抛
        if await self.tasks.find_by_id(task_id) is None:
            raise _not_found(task_id)
        return await self.assignments.find_by_task(task_id)

    # ---------- 写 ----------

    async def create(self, payload: TaskCreate, *, created_by: UUID) -> Task:
        """创建任务（含可选网格分解）。

        流程：
          1. service 层校验 area（特化错误码 422_TASK_INVALID_AREA_001）
          2. advisory lock + 分配 root code（按年序号）
          3. flush 父任务（拿到 id）
          4. 若 area_km2 > 1.0 且分解后 ≥ 2 tile：批量写子任务，parent_id=父
          5. commit
          6. push_event task.created（仅父，commander 房间）

        IntegrityError（极小概率 code 冲突）：rollback 后最多重试 3 次重新分配 code；
        全部失败抛 BusinessError(409_TASK_STATUS_CONFLICT_001) 留给上游 5xx 监控。
        """
        _validate_area(payload.target_area)

        last_exc: IntegrityError | None = None
        for _attempt in range(_CODE_GEN_RETRY):
            try:
                parent, child_count = await self._create_with_code(payload, created_by)
                await self.session.commit()
                await self.session.refresh(parent)
                await self._emit_created(parent, child_count)
                return parent
            except IntegrityError as exc:
                await self.session.rollback()
                last_exc = exc
                logger.warning(
                    "task_code_conflict_retry",
                    extra={"created_by": str(created_by), "attempt": _attempt + 1},
                )
                continue

        # 三次重试仍失败：极端罕见，按 5xx 暴露
        assert last_exc is not None
        raise BusinessError(
            code="500_INTERNAL_ERROR_001",
            message="任务编码分配失败（多次唯一冲突），请重试",
            http_status=500,
        ) from last_exc

    async def _create_with_code(
        self, payload: TaskCreate, created_by: UUID
    ) -> tuple[Task, int]:
        now_year = datetime.now(timezone.utc).year
        root_code, _seq = await _allocate_root_code(self.session, now_year)

        parent = Task(
            code=root_code,
            name=payload.name,
            type=payload.type,
            priority=payload.priority,
            status="PENDING",
            target_area=payload.target_area.model_dump(),
            required_capabilities=payload.required_capabilities.model_dump(),
            sla_deadline=payload.sla_deadline,
            created_by=created_by,
        )
        await self.tasks.save(parent)

        child_count = 0
        if payload.target_area.area_km2 > TASK_GRID_DECOMPOSE_THRESHOLD_KM2:
            tiles = _decompose_to_tiles(payload.target_area)
            if len(tiles) >= 2:
                cap_dump = payload.required_capabilities.model_dump()
                for idx, tile in enumerate(tiles, start=1):
                    child = Task(
                        code=_child_code(root_code, idx),
                        name=f"{payload.name} #子{idx:02d}",
                        type=payload.type,
                        priority=payload.priority,
                        status="PENDING",
                        target_area=tile,
                        required_capabilities=cap_dump,
                        sla_deadline=payload.sla_deadline,
                        parent_id=parent.id,
                        created_by=created_by,
                    )
                    await self.tasks.save(child)
                child_count = len(tiles)

        return parent, child_count

    async def update(self, task_id: UUID, payload: TaskUpdate) -> Task:
        """PUT /tasks/{id}：仅 name / priority / sla_deadline，且任务非终态。

        终态（COMPLETED / FAILED / CANCELLED）→ 409_TASK_STATUS_CONFLICT_001
        （API_SPEC §3 PUT 写「409 任务状态不允许修改」；BUSINESS_RULES §6.3 字面）。
        """
        task = await self.tasks.find_by_id(task_id)
        if task is None:
            raise _not_found(task_id)
        if task.status in TERMINAL_TASK_STATUSES:
            raise BusinessError(
                code="409_TASK_STATUS_CONFLICT_001",
                message=f"任务处于终态 {task.status}，不允许修改",
                http_status=409,
                details=[
                    {
                        "field": "task.status",
                        "code": "current_status",
                        "message": task.status,
                    }
                ],
            )

        patch = payload.model_dump(exclude_unset=True)
        if "name" in patch and patch["name"] is not None:
            task.name = patch["name"]
        if "priority" in patch and patch["priority"] is not None:
            task.priority = patch["priority"]
        if "sla_deadline" in patch:  # 允许显式清空
            task.sla_deadline = patch["sla_deadline"]

        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def cancel(
        self, task_id: UUID, *, user_id: UUID, reason: str
    ) -> Task:
        """POST /tasks/{id}/cancel：HITL 取消任务。

        流程（BUSINESS_RULES §4.2 + §2.1）：
          1. reason ≥5 字符且非纯空白 → 422_INTERVENTION_REASON_INVALID_001
          2. 任务存在 → 404_TASK_NOT_FOUND_001
          3. 已 CANCELLED → 409_TASK_ALREADY_CANCELLED_001（特化于通用 status_conflict）
          4. 其他终态（COMPLETED / FAILED）→ 409_TASK_STATUS_CONFLICT_001
          5. before_state 快照（assigned_robot_ids 来自 active assignments）
          6. status_machine.transit → CANCELLED（同时按规则置 completed_at）
          7. 释放所有 active assignments（is_active=FALSE，released_at=NOW）
          8. after_state（status=CANCELLED, assigned_robot_ids=[]）
          9. 写 human_interventions(intervention_type='cancel_task')，同事务
          10. commit
          11. push_event task.cancelled（commander 房间）
        """
        _validate_reason(reason)

        task = await self.tasks.find_by_id(task_id)
        if task is None:
            raise _not_found(task_id)

        if task.status == "CANCELLED":
            raise BusinessError(
                code="409_TASK_ALREADY_CANCELLED_001",
                message="任务已被取消",
                http_status=409,
                details=[
                    {
                        "field": "task.status",
                        "code": "current_status",
                        "message": task.status,
                    }
                ],
            )
        if task.status in TERMINAL_TASK_STATUSES:
            raise BusinessError(
                code="409_TASK_STATUS_CONFLICT_001",
                message=f"任务处于终态 {task.status}，不允许取消",
                http_status=409,
                details=[
                    {
                        "field": "task.status",
                        "code": "current_status",
                        "message": task.status,
                    }
                ],
            )

        active_before = await self.assignments.find_by_task(task_id, only_active=True)
        before_state = {
            "task_id": str(task.id),
            "task_code": task.code,
            "status": task.status,
            "assigned_robot_ids": [str(a.robot_id) for a in active_before],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # 6) 状态机转移（任意非终态 → CANCELLED 都被 TASK_TRANSITIONS 允许）
        transit_task(task, "CANCELLED", reason=reason)

        # 7) 释放 active assignments
        now = datetime.now(timezone.utc)
        await self.assignments.release_active_for_task(task_id, released_at=now)

        # 8) after_state
        after_state = {
            "task_id": str(task.id),
            "task_code": task.code,
            "status": "CANCELLED",
            "assigned_robot_ids": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # 9) 写 intervention（同事务）
        intervention = HumanIntervention(
            user_id=user_id,
            intervention_type="cancel_task",
            target_task_id=task.id,
            target_robot_id=None,
            before_state=before_state,
            after_state=after_state,
            reason=reason,
        )
        await self.interventions.save(intervention)

        await self.session.commit()
        await self.session.refresh(task)

        # 11) publish task.cancelled（commit 之后；失败仅日志，bus → bridge → push_event）
        try:
            await get_event_bus().publish(
                "task.cancelled",
                {
                    "task_id": str(task.id),
                    "task_code": task.code,
                    "cancelled_by_user_id": str(user_id),
                    "reason": reason,
                    "intervention_id": str(intervention.id),
                },
            )
        except Exception:
            logger.exception(
                "task_cancelled_publish_failed", extra={"task_id": str(task.id)}
            )

        return task

    async def _emit_created(self, parent: Task, child_count: int) -> None:
        try:
            await get_event_bus().publish(
                "task.created",
                {
                    "task_id": str(parent.id),
                    "task_code": parent.code,
                    "name": parent.name,
                    "type": parent.type,
                    "priority": int(parent.priority),
                    "target_area": parent.target_area,
                    "created_by": str(parent.created_by),
                    "child_count": child_count,
                },
            )
        except Exception:
            logger.exception(
                "task_created_publish_failed", extra={"task_id": str(parent.id)}
            )
