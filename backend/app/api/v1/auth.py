"""认证相关 REST 路由。

对照 API_SPEC §1。

公开:
- POST /auth/login    （P2.3）
- POST /auth/refresh  （P2.5）

需认证（依赖 P2.4 的 get_current_user）:
- GET  /auth/me       （P2.5）
- POST /auth/logout   （P2.5，简化版：不做后端黑名单，由前端清 token）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    return await AuthService(db).login(payload.username, payload.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    return await AuthService(db).refresh(payload.refresh_token)


@router.get("/me", response_model=CurrentUser)
async def me(
    current: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    return current


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def logout(
    _current: CurrentUser = Depends(get_current_user),
) -> Response:
    """简化版：不维护后端黑名单（BUILD_ORDER P2.5 说明），仅校验 access
    token 有效后返回 204 No Content；客户端负责清除本地 token。"""
    return Response(status_code=status.HTTP_204_NO_CONTENT)
