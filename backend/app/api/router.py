"""聚合 v1 各模块 router 到一个 APIRouter，前缀 /api/v1。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth as v1_auth
from app.api.v1 import blackboard as v1_blackboard
from app.api.v1 import dispatch as v1_dispatch
from app.api.v1 import perception as v1_perception
from app.api.v1 import robots as v1_robots
from app.api.v1 import tasks as v1_tasks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(v1_auth.router)
api_router.include_router(v1_robots.router)
api_router.include_router(v1_tasks.router)
api_router.include_router(v1_dispatch.router)
api_router.include_router(v1_blackboard.router)
api_router.include_router(v1_perception.router)
