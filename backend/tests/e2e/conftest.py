"""E2E 测试夹具：DB 清场 + 复用 commander001 用户 + 共享 helper。

设计取舍：
- 不重置 DB schema（migrations 已就位）；测试数据用 `T-8888-...` / `UAV-E2E-...`
  前缀隔离，session-scoped autouse fixture 在 setup / teardown 各跑一次清场。
- E2E 测试启动 EventBus + 注册 auto_trigger handler（与 main.py lifespan 同款），
  跑完后 stop bus。不启动 PendingAuctionScanner（避免与测试节奏抢任务）。
- 用 httpx ASGITransport 直接打 FastAPI app；不起 uvicorn，避免端口占用与
  socketio 服务的额外协程。
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import select, text

# 让导入解析得到 backend/app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.event_bus import EventBus, get_event_bus  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.db.session import async_session_maker, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.dispatch_service import DispatchSettings  # noqa: E402
from app.services.dispatch_trigger import (  # noqa: E402
    register_auto_trigger,
    reset_scanner_for_tests,
)

E2E_TASK_PREFIX = "T-8888"
E2E_ROBOT_PREFIX = "UAV-E2E"


# ---------- DB 清场 ----------


async def _cleanup_e2e_data() -> None:
    """删除上次/本次 E2E 测试残留（按前缀；不影响 seed 用户/机器人）。"""
    async with async_session_maker() as session:
        prefixes = (f"{E2E_TASK_PREFIX}-%",)
        for p in prefixes:
            await session.execute(
                text(
                    f"DELETE FROM human_interventions WHERE target_task_id IN (SELECT id FROM tasks WHERE code LIKE '{p}')"
                )
            )
            await session.execute(
                text(
                    f"DELETE FROM bids WHERE auction_id IN (SELECT id FROM auctions WHERE task_id IN (SELECT id FROM tasks WHERE code LIKE '{p}'))"
                )
            )
            await session.execute(
                text(
                    f"DELETE FROM auctions WHERE task_id IN (SELECT id FROM tasks WHERE code LIKE '{p}')"
                )
            )
            await session.execute(
                text(
                    f"DELETE FROM task_assignments WHERE task_id IN (SELECT id FROM tasks WHERE code LIKE '{p}')"
                )
            )
            await session.execute(
                text(f"DELETE FROM tasks WHERE code LIKE '{p}'")
            )
        rcond = f"code LIKE '{E2E_ROBOT_PREFIX}-%'"
        await session.execute(
            text(f"DELETE FROM robot_states WHERE robot_id IN (SELECT id FROM robots WHERE {rcond})")
        )
        await session.execute(
            text(f"DELETE FROM task_assignments WHERE robot_id IN (SELECT id FROM robots WHERE {rcond})")
        )
        await session.execute(
            text(f"DELETE FROM auctions WHERE winner_robot_id IN (SELECT id FROM robots WHERE {rcond})")
        )
        await session.execute(
            text(f"DELETE FROM bids WHERE robot_id IN (SELECT id FROM robots WHERE {rcond})")
        )
        await session.execute(text(f"DELETE FROM robots WHERE {rcond}"))
        await session.commit()


# ---------- session-scoped event bus + auto trigger ----------


@pytest_asyncio.fixture(autouse=True)
async def _e2e_per_test_setup() -> AsyncIterator[None]:
    """每个 E2E 用例：清场 → 起 EventBus + auto_trigger → 跑 → 停 + 清场。

    function 作用域的原因：pytest-asyncio 0.23 默认每测试一个 event loop；
    session-scoped 异步 fixture 与之 scope 不匹配（fixture 在不同 loop 上构建
    asyncio.Queue 会导致 dispatcher 跨 loop 出 RuntimeError: Event loop is closed）。
    """
    # 上一测试用例若把 engine 池里的连接绑到了已关闭 loop，必须 dispose 重建。
    await engine.dispose()

    DispatchSettings.reset_for_tests()
    EventBus.reset_for_tests()
    reset_scanner_for_tests()

    bus = get_event_bus()
    register_auto_trigger(bus)
    await bus.start()
    await _cleanup_e2e_data()
    try:
        yield
    finally:
        await _cleanup_e2e_data()
        await bus.stop()
        await engine.dispose()


# ---------- per-test client + commander token ----------


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def commander_headers() -> dict[str, str]:
    """复用 seed.py 的 commander001 用户构造 access token；roles 任填。"""
    async with async_session_maker() as session:
        u = (
            await session.execute(select(User).where(User.username == "commander001"))
        ).scalar_one_or_none()
    if u is None:
        pytest.skip("commander001 not seeded; run scripts/seed.py first")
    token = create_access_token(u.id, roles=["commander"])
    return {"Authorization": f"Bearer {token}"}


# ---------- helpers exported to tests ----------


def small_circle_target_area(*, lat: float = 30.225, lng: float = 120.525) -> dict[str, Any]:
    """area_km2=0.5 < 1 km²，避开网格分解（让 task.created 走 child_count=0 路径）。"""
    return {
        "type": "circle",
        "center": {"lat": lat, "lng": lng},
        "radius_m": 200.0,
        "area_km2": 0.5,
        "center_point": {"lat": lat, "lng": lng},
    }


async def seed_e2e_robot(*, code_suffix: str, battery: float = 100.0) -> uuid.UUID:
    """直接 INSERT 一台 IDLE / 满电 / 在 (30.225, 120.525) 的 UAV，返回 robot_id。"""
    from decimal import Decimal

    from app.models.robot import Robot, RobotState

    async with async_session_maker() as session:
        r = Robot(
            code=f"{E2E_ROBOT_PREFIX}-{code_suffix}",
            name=f"E2E {code_suffix}",
            type="uav",
            capability={
                "sensors": ["camera_4k", "thermal"],
                "payloads": [],
                "max_speed_mps": 23.0,
                "max_battery_min": 60,
                "max_range_km": 50.0,
                "has_yolo": True,
                "weight_kg": 5.0,
            },
            is_active=True,
        )
        session.add(r)
        await session.flush()
        s = RobotState(
            robot_id=r.id,
            fsm_state="IDLE",
            position={"lat": 30.225, "lng": 120.525},
            battery=Decimal(str(battery)),
            sensor_data={},
        )
        session.add(s)
        await session.commit()
        return r.id


async def wait_until(predicate, *, timeout: float = 10.0, interval: float = 0.1) -> bool:
    """轮询直到 predicate() 返回真或超时。"""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if await predicate():
            return True
        await asyncio.sleep(interval)
    return False
