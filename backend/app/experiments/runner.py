"""实验运行器（P8.2）。

对照 BUILD_ORDER §P8.2：
- ExperimentRunner.run_batch(scenario_id, algorithms, repetitions)：循环 N 次，
  每次创建测试任务 → 触发拍卖（测量 decision_latency）→ 收集指标 → 写 experiment_runs。
- 通过删除测试任务恢复干净状态（CASCADE 自动清除 auctions / bids / assignments）。
- _BATCHES 内存字典跟踪批次状态；GET /experiments/{batch_id} 读取此字典 + DB 获取结果。

设计取舍：
- 每次拍卖用独立 session（与 dispatch_trigger 同款理由：start_auction 内部 commit）。
- 任务直接插 DB 而不走 TaskService.create（跳过 advisory lock、WS 推送、网格分解）。
  仅实验用途，task code 使用 X-前缀规避与正常 T-YYYY-NNN 冲突。
- 拍卖结束后 DELETE tasks CASCADE 清除该轮产生的所有 auctions/bids/assignments。
- load_std_dev 按 25 台活跃机器人填充零，未分配机器人算 0 任务。
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
import statistics
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import get_event_bus
from app.core.exceptions import BusinessError
from app.db.session import async_session_maker
from app.models.dispatch import Bid
from app.models.replay import ExperimentRun
from app.models.task import Task
from app.repositories.experiment import ExperimentRunRepository
from app.repositories.user import UserRepository
from app.services.dispatch_service import DispatchService

logger = logging.getLogger(__name__)

# 内存状态：{str(batch_id): {"status": ..., "total": N, "completed": M}}
_BATCHES: dict[str, dict] = {}

# 每次运行创建的测试任务数
NUM_TASKS_PER_RUN = 10

# 算法缩写（用于 task code 生成，每个算法唯一单字母）
_ALGO_ABBR = {
    "AUCTION_HUNGARIAN": "H",
    "GREEDY": "G",
    "RANDOM": "R",
}

# 所有活跃机器人数量（种子固定 25 台）
_ACTIVE_ROBOT_COUNT = 25


def get_batch_status(batch_id: UUID) -> dict | None:
    """返回内存中的批次状态，未找到时返回 None。"""
    return _BATCHES.get(str(batch_id))


def _random_pos(sw: dict, ne: dict) -> dict:
    lat = sw["lat"] + random.random() * (ne["lat"] - sw["lat"])
    lng = sw["lng"] + random.random() * (ne["lng"] - sw["lng"])
    return {"lat": round(lat, 6), "lng": round(lng, 6)}


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class ExperimentRunner:
    """单例可复用的实验运行器。"""

    async def run_batch(
        self,
        *,
        batch_id: UUID,
        scenario_id: UUID,
        algorithms: list[str],
        repetitions: int,
    ) -> None:
        """后台运行整批实验，进度写入 _BATCHES 内存字典 + DB。"""
        total = len(algorithms) * repetitions
        _BATCHES[str(batch_id)] = {"status": "running", "total": total, "completed": 0}

        try:
            # 获取场景地图范围 + 系统用户 ID
            async with async_session_maker() as s:
                row = (
                    await s.execute(
                        text("SELECT map_bounds FROM scenarios WHERE id = :id"),
                        {"id": str(scenario_id)},
                    )
                ).one_or_none()
                if row is None:
                    raise ValueError(f"Scenario {scenario_id} not found")
                map_bounds: dict = row[0]

                sys_user = await UserRepository(s).get_by_username("system")
                if sys_user is None:
                    # fallback: 取第一个有效用户
                    any_user = (await s.execute(text("SELECT id FROM users LIMIT 1"))).one_or_none()
                    if any_user is None:
                        raise ValueError("No users found in DB")
                    system_user_id = any_user[0]
                else:
                    system_user_id = sys_user.id

                # 查活跃机器人数（用于 load_std_dev 分母）
                active_count: int = (
                    await s.execute(text("SELECT COUNT(*) FROM robots WHERE is_active = TRUE"))
                ).scalar_one()

            sw = map_bounds["sw"]
            ne = map_bounds["ne"]
            center_lat = (sw["lat"] + ne["lat"]) / 2
            center_lng = (sw["lng"] + ne["lng"]) / 2

            for algorithm in algorithms:
                for run_index in range(1, repetitions + 1):
                    await self._run_single(
                        batch_id=batch_id,
                        scenario_id=scenario_id,
                        algorithm=algorithm,
                        run_index=run_index,
                        sw=sw,
                        ne=ne,
                        center_lat=center_lat,
                        center_lng=center_lng,
                        system_user_id=system_user_id,
                        active_robot_count=active_count or _ACTIVE_ROBOT_COUNT,
                    )
                    _BATCHES[str(batch_id)]["completed"] += 1
                    await self._publish_progress(
                        batch_id=batch_id,
                        completed_runs=_BATCHES[str(batch_id)]["completed"],
                        total_runs=total,
                        current_algorithm=algorithm,
                    )
                    # 每次 run 后稍作 yield 避免阻塞事件循环
                    await asyncio.sleep(0)

            _BATCHES[str(batch_id)]["status"] = "completed"
            await self._publish_completed(batch_id=batch_id, total_runs=total)
            logger.info("experiment_batch_completed", extra={"batch_id": str(batch_id), "total": total})

        except Exception as exc:
            logger.exception("experiment_batch_failed", extra={"batch_id": str(batch_id)})
            _BATCHES[str(batch_id)]["status"] = "failed"
            _BATCHES[str(batch_id)]["error"] = str(exc)
            raise

    async def _run_single(
        self,
        *,
        batch_id: UUID,
        scenario_id: UUID,
        algorithm: str,
        run_index: int,
        sw: dict,
        ne: dict,
        center_lat: float,
        center_lng: float,
        system_user_id: UUID,
        active_robot_count: int,
    ) -> None:
        started_at = datetime.now(timezone.utc)
        b_hex = str(batch_id).replace("-", "")[:8]
        a_abbr = _ALGO_ABBR.get(algorithm, algorithm[:1].upper())

        # ── 1) 创建测试任务 ──────────────────────────────────────────────────
        task_ids: list[UUID] = []
        task_positions: list[dict] = []

        task_types = ["search_rescue", "recon", "transport", "patrol"]

        async with async_session_maker() as s:
            for i in range(NUM_TASKS_PER_RUN):
                pos = _random_pos(sw, ne)
                code = f"X-{b_hex}-{a_abbr}{run_index:02d}{i + 1:02d}"
                target_area = {
                    "type": "circle",
                    "center": pos,
                    "radius_m": 200.0,
                    "area_km2": 0.13,
                    "center_point": pos,
                }
                required_capabilities = {
                    "sensors": [],
                    "payloads": [],
                    "min_battery_pct": 20.0,
                    "robot_type": None,
                }
                task = Task(
                    id=uuid4(),
                    code=code,
                    name=f"实验 {run_index}-{i + 1}",
                    type=random.choice(task_types),
                    priority=random.choice([1, 2, 3]),
                    status="PENDING",
                    target_area=target_area,
                    required_capabilities=required_capabilities,
                    created_by=system_user_id,
                )
                s.add(task)
                task_ids.append(task.id)
                task_positions.append(pos)
            await s.commit()

        # ── 2) 逐任务触发拍卖 ────────────────────────────────────────────────
        auction_results: list[dict] = []
        winner_robot_counts: dict[UUID, int] = {}

        for task_id in task_ids:
            try:
                async with async_session_maker() as s:
                    svc = DispatchService(s)
                    auction = await svc.start_auction(task_id, algorithm=algorithm)
                    # start_auction 内部已 commit
                    auction_results.append(
                        {
                            "status": auction.status,
                            "latency_ms": auction.decision_latency_ms,
                            "winner": auction.winner_robot_id,
                            "vision_assisted_count": await self._count_vision_assisted_bids(
                                s, auction_id=auction.id
                            ),
                        }
                    )
                    if auction.winner_robot_id:
                        rid = auction.winner_robot_id
                        winner_robot_counts[rid] = winner_robot_counts.get(rid, 0) + 1
            except BusinessError as exc:
                logger.info(
                    "experiment_auction_skipped",
                    extra={"task_id": str(task_id), "reason": str(exc)},
                )
                auction_results.append(
                    {
                        "status": "ERROR",
                        "latency_ms": None,
                        "winner": None,
                        "vision_assisted_count": 0,
                    }
                )
            except Exception:
                logger.exception("experiment_auction_error", extra={"task_id": str(task_id)})
                auction_results.append(
                    {
                        "status": "ERROR",
                        "latency_ms": None,
                        "winner": None,
                        "vision_assisted_count": 0,
                    }
                )

        # ── 3) 计算指标 ──────────────────────────────────────────────────────
        closed = [a for a in auction_results if a["status"] == "CLOSED"]
        completion_rate = Decimal(str(round(len(closed) / len(auction_results) * 100, 2)))

        latencies = [a["latency_ms"] for a in auction_results if a["latency_ms"] is not None]
        avg_latency_ms = int(sum(latencies) / len(latencies)) if latencies else None
        avg_response_sec = (
            Decimal(str(round(avg_latency_ms / 1000.0, 2))) if avg_latency_ms is not None else None
        )

        # 负载均衡：25 台机器人中每台分配的任务数的标准差（未分配机器人补 0）
        task_counts = list(winner_robot_counts.values())
        zeros = [0] * (active_robot_count - len(task_counts))
        task_counts.extend(zeros)
        load_std_dev = (
            Decimal(str(round(statistics.stdev(task_counts), 3)))
            if len(task_counts) >= 2
            else Decimal("0.000")
        )

        # 总路径：中心点→各任务中心的 haversine 之和（只统计已分配任务）
        total_path_km = Decimal("0.000")
        for result, pos in zip(auction_results, task_positions):
            if result["winner"]:
                dist = _haversine_km(center_lat, center_lng, pos["lat"], pos["lng"])
                total_path_km += Decimal(str(round(dist, 3)))

        per_task_response = [
            {"task_id": str(tid), "response_sec": round(a["latency_ms"] / 1000.0, 3)}
            for tid, a in zip(task_ids, auction_results)
            if a["latency_ms"] is not None
        ]
        raw_metrics = {
            "per_robot_load": [
                {"robot_id": str(rid), "task_count": cnt}
                for rid, cnt in winner_robot_counts.items()
            ],
            "per_task_response_sec": per_task_response,
            "total_decisions": len(auction_results),
            "hitl_interventions": 0,
            "vision_assisted_count": sum(
                int(a.get("vision_assisted_count") or 0) for a in auction_results
            ),
        }

        finished_at = datetime.now(timezone.utc)

        # ── 4) 写 ExperimentRun + 清除测试任务（CASCADE 删 auctions/bids/assignments）
        async with async_session_maker() as s:
            run = ExperimentRun(
                id=uuid4(),
                batch_id=batch_id,
                scenario_id=scenario_id,
                algorithm=algorithm,
                run_index=run_index,
                completion_rate=completion_rate,
                avg_response_sec=avg_response_sec,
                total_path_km=total_path_km,
                load_std_dev=load_std_dev,
                decision_latency_ms=avg_latency_ms,
                raw_metrics=raw_metrics,
                started_at=started_at,
                finished_at=finished_at,
            )
            await ExperimentRunRepository(s).save(run)
            # 删除测试任务（CASCADE 自动删 auctions / bids / task_assignments）
            await s.execute(delete(Task).where(Task.id.in_(task_ids)))
            await s.commit()

        logger.info(
            "experiment_run_done",
            extra={
                "batch_id": str(batch_id),
                "algorithm": algorithm,
                "run_index": run_index,
                "completion_rate": str(completion_rate),
                "decision_latency_ms": avg_latency_ms,
            },
        )

    async def _count_vision_assisted_bids(
        self, session: AsyncSession, *, auction_id: UUID
    ) -> int:
        """统计本次拍卖中真实触发视觉加成的出价数量。"""
        rows = (
            await session.execute(select(Bid).where(Bid.auction_id == auction_id))
        ).scalars().all()
        return sum(
            1
            for bid in rows
            if float(bid.vision_boost or 1.0) > 1.0
            or bool((bid.breakdown or {}).get("vision_boosted"))
        )

    async def _publish_progress(
        self,
        *,
        batch_id: UUID,
        completed_runs: int,
        total_runs: int,
        current_algorithm: str,
    ) -> None:
        remaining = max(total_runs - completed_runs, 0)
        await get_event_bus().publish(
            "experiment.progress",
            {
                "batch_id": str(batch_id),
                "completed_runs": completed_runs,
                "total_runs": total_runs,
                "current_algorithm": current_algorithm,
                "estimated_remaining_sec": remaining * 5,
            },
        )

    async def _publish_completed(self, *, batch_id: UUID, total_runs: int) -> None:
        async with async_session_maker() as session:
            runs = await ExperimentRunRepository(session).find_by_batch(batch_id)

        by_algorithm: dict[str, list[float]] = {}
        for run in runs:
            if run.completion_rate is None:
                continue
            by_algorithm.setdefault(run.algorithm, []).append(float(run.completion_rate))

        stats = {}
        for algorithm, values in by_algorithm.items():
            stats[algorithm] = {
                "completion_rate_mean": sum(values) / len(values) if values else 0.0,
                "completion_rate_std": statistics.stdev(values)
                if len(values) >= 2
                else 0.0,
            }

        started_values = [run.started_at for run in runs if run.started_at is not None]
        finished_values = [run.finished_at for run in runs if run.finished_at is not None]
        duration_sec = 0
        if started_values and finished_values:
            duration_sec = max(
                0,
                int((max(finished_values) - min(started_values)).total_seconds()),
            )

        await get_event_bus().publish(
            "experiment.completed",
            {
                "batch_id": str(batch_id),
                "total_runs": total_runs,
                "duration_sec": duration_sec,
                "stats": stats,
            },
        )


_runner = ExperimentRunner()


def get_experiment_runner() -> ExperimentRunner:
    return _runner
