"""scripts/seed.py — P1.5 种子数据脚本

对照：
- BUILD_ORDER §P1.5（3 角色 + 2 用户 + 25 机器人 + 3 编队 + 1 场景）
- DATA_CONTRACTS §4.1（roles.permissions）
- DATA_CONTRACTS §4.2（robots.capability）
- DATA_CONTRACTS §4.14 / §4.15（scenarios.map_bounds / initial_state）
- BUILD_ORDER §P6.7（额外预创建 system 用户作为自动任务的 created_by）

幂等：所有插入使用 ON CONFLICT DO NOTHING（robot_groups 无 UNIQUE 约束，使用
select-then-insert 兜底）。重复执行不会报错也不会重复写入。

执行：
    backend\\.venv\\Scripts\\python.exe scripts\\seed.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# 让 scripts/seed.py 既能定位到 backend/app.*，又能让 pydantic-settings 读到 backend/.env
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

# Windows 上 asyncpg 需要 SelectorEventLoopPolicy（与 migrations/env.py 同源约束）
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Robot,
    RobotGroup,
    Role,
    Scenario,
    User,
    UserRole,
)

# ============================================================
# 静态数据
# ============================================================

ROLES_DEF = [
    {
        "name": "commander",
        "description": "指挥员：创建/取消任务，改派/召回机器人，切换调度算法",
        "permissions": [
            "task:create",
            "task:cancel",
            "task:update",
            "robot:reassign",
            "robot:recall",
            "robot:manage",
            "algorithm:switch",
        ],
    },
    {
        "name": "admin",
        "description": "管理员：用户与系统管理",
        "permissions": ["user:manage", "system:admin"],
    },
    {
        "name": "observer",
        "description": "观察员：只读",
        "permissions": [],
    },
]

USERS_DEF = [
    {
        "username": "commander001",
        "display_name": "指挥员 001",
        "password": "password123",
        "role": "commander",
    },
    {
        "username": "admin001",
        "display_name": "管理员 001",
        "password": "password123",
        "role": "admin",
    },
    {
        # P6.7 自动派任务的 created_by；统一用 password123 便于演练登录
        "username": "system",
        "display_name": "系统（自动派单）",
        "password": "password123",
        "role": "commander",
    },
]

GROUPS_DEF = [
    {"name": "空中编队 Alpha", "description": "10 台 UAV 组成的高空侦察编队"},
    {"name": "地面编队 Bravo", "description": "10 台 UGV 组成的地面救援编队"},
    {"name": "水面编队 Charlie", "description": "5 台 USV 组成的水面巡查编队"},
]

# 演练区中心：与 DATA_CONTRACTS §4.5 示例对齐
CENTER_LAT = 30.225
CENTER_LNG = 120.525

UAV_CAPABILITY = {
    "sensors": ["camera_4k", "thermal"],
    "payloads": [],
    "max_speed_mps": 23.0,
    "max_battery_min": 55,
    "max_range_km": 8.0,
    "has_yolo": True,
    "weight_kg": 6.3,
}

UGV_CAPABILITY = {
    "sensors": ["camera", "lidar"],
    "payloads": ["winch", "rescue_kit"],
    "max_speed_mps": 2.5,
    "max_battery_min": 180,
    "max_range_km": 4.0,
    "has_yolo": False,
    "weight_kg": 90.0,
}

USV_CAPABILITY = {
    "sensors": ["sonar", "camera"],
    "payloads": [],
    "max_speed_mps": 8.0,
    "max_battery_min": 240,
    "max_range_km": 30.0,
    "has_yolo": False,
    "weight_kg": 320.0,
}

SCENARIO_DEF = {
    "name": "6 级地震演练",
    "disaster_type": "earthquake",
    "description": "杭州西湖区 6 级地震救援演练，25 台异构机器人初始部署",
    "map_bounds": {
        "sw": {"lat": 30.20, "lng": 120.50},
        "ne": {"lat": 30.25, "lng": 120.55},
        "center": {"lat": CENTER_LAT, "lng": CENTER_LNG},
        "zoom_default": 14,
    },
}


def build_robots_def() -> list[dict]:
    """生成 25 台机器人定义：10 UAV + 10 UGV + 5 USV，初始位置围绕中心散布。"""
    rows: list[dict] = []
    for i in range(1, 11):
        rows.append({
            "code": f"UAV-{i:03d}",
            "name": f"鹰眼-{i}",
            "type": "uav",
            "model": "DJI M300 RTK",
            "capability": UAV_CAPABILITY,
            "group_name": "空中编队 Alpha",
            "init_lat": round(CENTER_LAT + 0.001 * i, 6),
            "init_lng": round(CENTER_LNG + 0.001 * i, 6),
        })
    for i in range(1, 11):
        rows.append({
            "code": f"UGV-{i:03d}",
            "name": f"履带-{i}",
            "type": "ugv",
            "model": "Husky A200",
            "capability": UGV_CAPABILITY,
            "group_name": "地面编队 Bravo",
            "init_lat": round(CENTER_LAT - 0.001 * i, 6),
            "init_lng": round(CENTER_LNG + 0.001 * i, 6),
        })
    for i in range(1, 6):
        rows.append({
            "code": f"USV-{i:03d}",
            "name": f"海豚-{i}",
            "type": "usv",
            "model": "WAM-V 16",
            "capability": USV_CAPABILITY,
            "group_name": "水面编队 Charlie",
            "init_lat": round(CENTER_LAT - 0.002 * i, 6),
            "init_lng": round(CENTER_LNG - 0.002 * i, 6),
        })
    return rows


# ============================================================
# 幂等插入 helpers
# ============================================================

async def upsert_role(session: AsyncSession, defn: dict) -> str:
    stmt = (
        pg_insert(Role.__table__)
        .values(
            name=defn["name"],
            description=defn["description"],
            permissions=defn["permissions"],
        )
        .on_conflict_do_nothing(index_elements=["name"])
    )
    await session.execute(stmt)
    res = await session.execute(select(Role.id).where(Role.name == defn["name"]))
    return str(res.scalar_one())


async def upsert_user(session: AsyncSession, defn: dict) -> str:
    stmt = (
        pg_insert(User.__table__)
        .values(
            username=defn["username"],
            password_hash=hash_password(defn["password"]),
            display_name=defn["display_name"],
            email=None,
            is_active=True,
        )
        .on_conflict_do_nothing(index_elements=["username"])
    )
    await session.execute(stmt)
    res = await session.execute(select(User.id).where(User.username == defn["username"]))
    return str(res.scalar_one())


async def grant_role(session: AsyncSession, user_id: str, role_id: str) -> None:
    stmt = (
        pg_insert(UserRole.__table__)
        .values(user_id=user_id, role_id=role_id)
        .on_conflict_do_nothing(index_elements=["user_id", "role_id"])
    )
    await session.execute(stmt)


async def upsert_group(session: AsyncSession, defn: dict) -> str:
    """robot_groups 无 UNIQUE 约束，使用 select-then-insert 实现幂等。"""
    res = await session.execute(
        select(RobotGroup.id).where(RobotGroup.name == defn["name"])
    )
    existing = res.scalar_one_or_none()
    if existing is not None:
        return str(existing)
    obj = RobotGroup(name=defn["name"], description=defn["description"])
    session.add(obj)
    await session.flush()
    res = await session.execute(
        select(RobotGroup.id).where(RobotGroup.name == defn["name"])
    )
    return str(res.scalar_one())


async def upsert_robot(session: AsyncSession, defn: dict, group_id: str) -> None:
    stmt = (
        pg_insert(Robot.__table__)
        .values(
            code=defn["code"],
            name=defn["name"],
            type=defn["type"],
            model=defn["model"],
            capability=defn["capability"],
            group_id=group_id,
            is_active=True,
        )
        .on_conflict_do_nothing(index_elements=["code"])
    )
    await session.execute(stmt)


async def upsert_scenario(
    session: AsyncSession, defn: dict, robots: list[dict]
) -> None:
    initial_state = {
        "robots": [
            {
                "code": r["code"],
                "initial_position": {"lat": r["init_lat"], "lng": r["init_lng"]},
                "initial_battery": 100.0,
            }
            for r in robots
        ]
    }
    stmt = (
        pg_insert(Scenario.__table__)
        .values(
            name=defn["name"],
            disaster_type=defn["disaster_type"],
            map_bounds=defn["map_bounds"],
            initial_state=initial_state,
            description=defn["description"],
            is_active=True,
        )
        .on_conflict_do_nothing(index_elements=["name"])
    )
    await session.execute(stmt)


# ============================================================
# 主流程
# ============================================================

async def main() -> None:
    print(
        f"[seed] target DB: {settings.db_user}@{settings.db_host}:"
        f"{settings.db_port}/{settings.db_name}"
    )
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    robots_def = build_robots_def()

    async with Session() as session:
        role_ids: dict[str, str] = {}
        for r in ROLES_DEF:
            role_ids[r["name"]] = await upsert_role(session, r)
        print(f"[seed] roles  : {list(role_ids.keys())}")

        user_ids: dict[str, str] = {}
        for u in USERS_DEF:
            uid = await upsert_user(session, u)
            user_ids[u["username"]] = uid
            await grant_role(session, uid, role_ids[u["role"]])
        print(f"[seed] users  : {list(user_ids.keys())}")

        group_ids: dict[str, str] = {}
        for g in GROUPS_DEF:
            group_ids[g["name"]] = await upsert_group(session, g)
        print(f"[seed] groups : {list(group_ids.keys())}")

        for rb in robots_def:
            await upsert_robot(session, rb, group_ids[rb["group_name"]])
        print(f"[seed] robots : {len(robots_def)} 台 (10 UAV + 10 UGV + 5 USV)")

        await upsert_scenario(session, SCENARIO_DEF, robots_def)
        print(f"[seed] scene  : {SCENARIO_DEF['name']}")

        await session.commit()

    await engine.dispose()
    print("[seed] done.")


if __name__ == "__main__":
    asyncio.run(main())
