"""P8.1 复盘后端自检脚本（一次性，验收后删除）。

覆盖：
- A. timeline_player 纯函数（filter_snapshots / filter_key_events）
- B. SnapshotRecorder 内核：lifecycle / open_session / build_snapshot /
  terminal diff / finalize 落库 / max_frames 触发 finalize
- C. EventBus handlers append key_events 到 active session
- D. REST 401 / 403 / 200：list / detail / snapshots / key-events
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


from sqlalchemy import delete, select  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.session import async_session_maker  # noqa: E402
from app.models.replay import ReplaySession  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.models.user import User  # noqa: E402
from app.replay import snapshot_recorder as sr  # noqa: E402
from app.replay.timeline_player import filter_key_events, filter_snapshots  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASS.append(label)
        print(f"  PASS  {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  FAIL  {label}  {detail}")


# ============== A. timeline_player ==============


def section_a() -> None:
    print("\n[A] timeline_player ----------")
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    snaps = [{"ts": (base + timedelta(seconds=i)).isoformat()} for i in range(10)]

    out = filter_snapshots(snaps)
    check("A1 默认无抽样保留全部", len(out) == 10)

    out = filter_snapshots(snaps, interval_sec=2.0)
    check("A2 interval=2 抽样减半（含首帧）", len(out) == 5)

    out = filter_snapshots(
        snaps,
        start_time=base + timedelta(seconds=2),
        end_time=base + timedelta(seconds=5),
    )
    check("A3 时间窗 [2,5] 闭区间", len(out) == 4)

    out = filter_snapshots([])
    check("A4 空入参返回空", out == [])

    out = filter_snapshots([{"ts": "not-a-date"}, {"ts": base.isoformat()}])
    check("A5 ts 解析失败的帧自动跳过", len(out) == 1)

    evs = [
        {"ts": (base + timedelta(seconds=i)).isoformat(), "type": "alert"}
        for i in range(5)
    ]
    out = filter_key_events(
        evs,
        start_time=base + timedelta(seconds=1),
        end_time=base + timedelta(seconds=3),
    )
    check("A6 key_events 时间窗", len(out) == 3)


# ============== B + C. SnapshotRecorder 内核 ==============


class _StubTask:
    def __init__(self, *, code: str, status: str, progress: float = 0.0):
        self.id = uuid4()
        self.code = code
        self.status = status
        self.progress = progress


async def _purge_test_sessions() -> None:
    """清理本脚本残留 test session（按 name 前缀 'SELFCHECK-P81-'）。"""
    async with async_session_maker() as s:
        await s.execute(
            delete(ReplaySession).where(ReplaySession.name.like("SELFCHECK-P81-%"))
        )
        await s.commit()


async def section_b_c() -> None:
    print("\n[B+C] SnapshotRecorder ----------")
    sr.reset_for_tests()
    rec = sr.get_snapshot_recorder(interval_sec=0, max_frames=3)
    check("B1 interval=0 → 禁用 loop（start no-op）", True)
    await rec.start()
    check("B1.1 start 后 _started=False（因 interval=0）", not rec.started)

    # 构造：mock _fetch_relevant_tasks 的入口（通过 monkeypatch 类方法）
    fake_tasks: list[_StubTask] = []

    async def _fake_fetch(_session, _tracked):
        return list(fake_tasks)

    sr.SnapshotRecorder._fetch_relevant_tasks = staticmethod(_fake_fetch)  # type: ignore

    # 边界 1：无活跃任务 → 不开 session
    fake_tasks = []
    res = await rec.tick_once()
    check("B2 无活跃任务 → tick 返回 False", res is False)
    check("B2.1 active_session 仍为 None", rec.active_session is None)

    # 边界 2：出现 ASSIGNED 任务 → 开 session 并录第一帧
    t1 = _StubTask(code="T-SC-001", status="ASSIGNED")
    fake_tasks = [t1]
    res = await rec.tick_once()
    check("B3 出现 ASSIGNED → 开 session 并录帧", res is True)
    check("B3.1 active_session 非空", rec.active_session is not None)
    sess = rec.active_session
    assert sess is not None
    check("B3.2 第一帧入 buffer", len(sess.snapshots) == 1)
    check("B3.3 task_states 跟踪 t1=ASSIGNED", sess.task_states.get(t1.id) == "ASSIGNED")
    check(
        "B3.4 snapshot.tasks 含 1 个 task",
        len(sess.snapshots[0]["tasks"]) == 1
        and sess.snapshots[0]["tasks"][0]["code"] == "T-SC-001",
    )

    # 转 EXECUTING：不应触发 key_event
    t1.status = "EXECUTING"
    await rec.tick_once()
    check("B4 ASSIGNED→EXECUTING 不写 key_event",
          all(ev["type"] != "task_completed" for ev in sess.key_events))

    # 转 COMPLETED：写 task_completed key_event；session.all_tracked_terminal=True
    t1.status = "COMPLETED"
    await rec.tick_once()
    # tick 内 _detect_terminal_transitions 会 append；finalize 在 tick 末触发
    # 因为 finalize 后 _active=None，这里捕获已 finalized 的 session 信息要查 DB
    check("B5 终态后 _active 已 finalize 置空", rec.active_session is None)

    # 校验 DB 落库
    async with async_session_maker() as s:
        stmt = select(ReplaySession).where(
            ReplaySession.algorithm.is_not(None),
        ).order_by(ReplaySession.created_at.desc()).limit(1)
        latest = (await s.execute(stmt)).scalar_one_or_none()
    check("B5.1 replay_sessions 表新增一条", latest is not None)
    if latest is not None:
        summary = dict(latest.summary or {})
        check("B5.2 summary.snapshots 非空",
              len(summary.get("snapshots", [])) >= 2,
              detail=f"snapshots={len(summary.get('snapshots', []))}")
        evs = summary.get("key_events", [])
        check("B5.3 key_events 含 task_completed",
              any(ev.get("type") == "task_completed" for ev in evs))
        check("B5.4 summary.completed_tasks=1",
              summary.get("completed_tasks") == 1)
        check("B5.5 ended_at / duration_sec 已写",
              latest.ended_at is not None and latest.duration_sec is not None)
        # 标记本次 session 名称便于清理
        await _rename_for_cleanup(latest.id)

    # === C. EventBus handlers ===
    # 重新开一个 session
    t2 = _StubTask(code="T-SC-002", status="EXECUTING")
    fake_tasks = [t2]
    await rec.tick_once()
    sess2 = rec.active_session
    assert sess2 is not None

    await rec._on_alert_raised({"alert_id": str(uuid4()), "message": "测试告警"})
    await rec._on_auction_completed(
        {"auction_id": str(uuid4()), "algorithm": "HUNGARIAN", "task_code": "T-SC-002"}
    )
    await rec._on_intervention_recorded(
        {"intervention_id": str(uuid4()), "intervention_type": "reassign"}
    )
    await rec._on_task_reassigned(
        {"task_id": str(uuid4()), "from_robot_code": "UAV-001", "to_robot_code": "UAV-002"}
    )
    await rec._on_perception_high_confidence({"class_name": "survivor"})
    await rec._on_perception_high_confidence({"class_name": "fire"})
    await rec._on_perception_high_confidence({"class_name": "fire"})

    types = [ev["type"] for ev in sess2.key_events]
    check("C1 alert handler 写 key_event", "alert" in types)
    check("C2 auction handler 写 key_event", "auction_completed" in types)
    check("C3 intervention handler 写 key_event", "intervention" in types)
    check("C4 reassign handler 写 key_event", "task_reassigned" in types)
    check("C5 yolo survivor count=1", sess2.yolo_counts["survivor"] == 1)
    check("C6 yolo fire count=2", sess2.yolo_counts["fire"] == 2)
    check("C7 yolo smoke 未变", sess2.yolo_counts["smoke"] == 0)

    # 强制 finalize（停服路径）
    finalized_id = await rec._finalize_if_active(reason="selfcheck")
    check("C8 主动 finalize 返回 session_id", finalized_id is not None)
    if finalized_id is not None:
        await _rename_for_cleanup(finalized_id)

    # === B 续：max_frames 触发 finalize ===
    t3 = _StubTask(code="T-SC-003", status="EXECUTING")
    fake_tasks = [t3]
    await rec.tick_once()  # 第 1 帧 + 开 session
    await rec.tick_once()  # 第 2 帧
    # rec.max_frames=3 → 第 3 帧 + finalize
    await rec.tick_once()
    check("B6 帧数到上限自动 finalize", rec.active_session is None)
    async with async_session_maker() as s:
        stmt = select(ReplaySession).order_by(
            ReplaySession.created_at.desc()
        ).limit(1)
        recent = (await s.execute(stmt)).scalar_one()
        await _rename_for_cleanup(recent.id)


async def _rename_for_cleanup(session_id) -> None:
    """把刚创建的 session name 改成 SELFCHECK 前缀，便于清理。"""
    async with async_session_maker() as s:
        obj = await s.get(ReplaySession, session_id)
        if obj is not None and not obj.name.startswith("SELFCHECK-P81-"):
            obj.name = f"SELFCHECK-P81-{obj.name}"
            await s.commit()


# ============== D. REST 401 / 403 / 200 ==============


async def section_d() -> None:
    print("\n[D] REST endpoints ----------")
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1) 401 (no token)
        r = await client.get("/api/v1/replay/sessions")
        check("D1 GET /sessions 无 token → 401", r.status_code == 401)

        # 2) 403 (no replay:read)
        # 用一个临时 user：插一个无任何角色的 user，签发 token
        async with async_session_maker() as s:
            from app.core.security import hash_password

            # 幂等：先清理上一次失败遗留
            await s.execute(
                delete(User).where(User.username == "selfcheck_noperm_p81")
            )
            await s.commit()
            tmp_user = User(
                username="selfcheck_noperm_p81",
                password_hash=hash_password("xx"),
                display_name="P81 无权限测试",
                is_active=True,
            )
            s.add(tmp_user)
            await s.commit()
            await s.refresh(tmp_user)
            no_perm_id = tmp_user.id
        no_perm_token = create_access_token(no_perm_id, [])
        r = await client.get(
            "/api/v1/replay/sessions",
            headers={"Authorization": f"Bearer {no_perm_token}"},
        )
        check("D2 无 replay:read → 403", r.status_code == 403,
              detail=f"got {r.status_code}")

        # 3) commander 有 replay:read（seed 已 grant）
        async with async_session_maker() as s:
            cmd_user = (await s.execute(
                select(User).where(User.username == "commander001")
            )).scalar_one()
            cmd_id = cmd_user.id
        cmd_token = create_access_token(cmd_id, ["commander"])
        headers = {"Authorization": f"Bearer {cmd_token}"}

        # 创建一个测试 session 直接落库（避免依赖真实任务流）
        async with async_session_maker() as s:
            base = datetime.now(timezone.utc)
            test_session = ReplaySession(
                name="SELFCHECK-P81-rest",
                scenario_id=None,
                algorithm="HUNGARIAN",
                started_at=base,
                ended_at=base + timedelta(seconds=10),
                duration_sec=10,
                completion_rate=100.0,
                summary={
                    "total_tasks": 1,
                    "completed_tasks": 1,
                    "failed_tasks": 0,
                    "total_robots_used": 1,
                    "total_interventions": 0,
                    "total_alerts": 0,
                    "yolo_detections_summary": {
                        "survivor": 0, "fire": 0, "smoke": 0, "collapsed_building": 0
                    },
                    "snapshots": [
                        {"ts": (base + timedelta(seconds=i)).isoformat(),
                         "robots": [], "tasks": [],
                         "blackboard": {"total_entries": 0, "by_type": {}}}
                        for i in range(5)
                    ],
                    "key_events": [
                        {"ts": (base + timedelta(seconds=2)).isoformat(),
                         "type": "task_completed",
                         "description": "fake",
                         "related_id": str(uuid4())},
                    ],
                },
                created_by=cmd_id,
            )
            s.add(test_session)
            await s.commit()
            await s.refresh(test_session)
            sid = test_session.id

        r = await client.get("/api/v1/replay/sessions", headers=headers)
        check("D3 GET /sessions 200", r.status_code == 200,
              detail=f"got {r.status_code} body={r.text[:200]}")
        body = r.json()
        check("D3.1 响应 items 列表非空", len(body.get("items", [])) >= 1)

        r = await client.get(f"/api/v1/replay/sessions/{sid}", headers=headers)
        check("D4 GET /sessions/{id} 200", r.status_code == 200)
        if r.status_code == 200:
            detail_body = r.json()
            check("D4.1 详情含 summary.snapshots",
                  len(detail_body["summary"]["snapshots"]) == 5)

        r = await client.get(
            f"/api/v1/replay/sessions/{sid}/snapshots?interval_sec=2",
            headers=headers,
        )
        check("D5 snapshots interval=2 抽样", r.status_code == 200)
        if r.status_code == 200:
            arr = r.json()
            check("D5.1 抽样后帧数缩减", len(arr) <= 3,
                  detail=f"got {len(arr)}")

        r = await client.get(
            f"/api/v1/replay/sessions/{sid}/key-events", headers=headers
        )
        check("D6 key-events 200", r.status_code == 200)
        if r.status_code == 200:
            evs = r.json()
            check("D6.1 含 1 条 task_completed",
                  len(evs) == 1 and evs[0]["type"] == "task_completed")

        r = await client.get(
            f"/api/v1/replay/sessions/{uuid4()}", headers=headers
        )
        check("D7 不存在的 session → 404", r.status_code == 404)

        # 清理临时 user + session
        async with async_session_maker() as s:
            await s.execute(delete(User).where(User.id == no_perm_id))
            await s.execute(
                delete(ReplaySession).where(ReplaySession.id == sid)
            )
            await s.commit()


# ============== main ==============


async def main() -> None:
    await _purge_test_sessions()
    section_a()
    await section_b_c()
    await section_d()
    await _purge_test_sessions()
    sr.reset_for_tests()

    print(f"\n=== Result: {len(PASS)} pass / {len(FAIL)} fail ===")
    if FAIL:
        for f in FAIL:
            print("  FAIL:", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
