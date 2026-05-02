"""聚合 v1 各模块 router 到一个 APIRouter，前缀 /api/v1。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth as v1_auth
from app.api.v1 import robots as v1_robots

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(v1_auth.router)
api_router.include_router(v1_robots.router)
