"""认证服务。

对照：
- API_SPEC §1（POST /auth/login）
- BUSINESS_RULES §6.1（401_AUTH_INVALID_CREDENTIAL_001 / 423_AUTH_ACCOUNT_LOCKED_001）
- CONVENTIONS §10.1 / §11（锁定阈值，安全约定）

设计要点：
- 失败计数器：模块级内存 dict + asyncio.Lock 守护，进程重启清零；毕设场景
  足够，若需持久化（生产）可换 Redis（无需改 service 接口）。
- 安全策略：
  * 用户不存在 / 密码错 / is_active=False → 一律返回同一错误码
    （401_AUTH_INVALID_CREDENTIAL_001），避免用户名枚举攻击
  * 锁定期内任意请求（含正确密码）一律 423_AUTH_ACCOUNT_LOCKED_001
- 成功登录顺手更新 users.last_login_at = NOW()
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from uuid import UUID

from jose import ExpiredSignatureError, JWTError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.constants import (
    LOGIN_FAIL_LOCKOUT_THRESHOLD,
    LOGIN_LOCKOUT_DURATION_MIN,
)
from app.core.exceptions import BusinessError
from app.core.security import (
    TOKEN_TYPE_REFRESH,
    access_token_expires_in,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse


@dataclass
class _FailState:
    count: int = 0
    locked_until: float | None = None  # epoch seconds, None 表示未锁定


# 模块级状态（进程内单例）
_lock = asyncio.Lock()
_fail_state: dict[str, _FailState] = {}


async def _check_locked(username: str) -> None:
    """若该用户处于锁定期内，抛 423；过期则自动清掉锁定标记。"""
    async with _lock:
        st = _fail_state.get(username)
        if st is None or st.locked_until is None:
            return
        if st.locked_until > time.time():
            raise BusinessError(
                code="423_AUTH_ACCOUNT_LOCKED_001",
                message=f"账号已锁定，请 {LOGIN_LOCKOUT_DURATION_MIN} 分钟后重试",
                http_status=423,
            )
        # 过期：清掉锁定，但保留 0 计数（让用户重新计数）
        st.locked_until = None
        st.count = 0


async def _record_failure(username: str) -> None:
    """累加失败计数，达阈值时设置锁定窗口。"""
    async with _lock:
        st = _fail_state.setdefault(username, _FailState())
        st.count += 1
        if st.count >= LOGIN_FAIL_LOCKOUT_THRESHOLD:
            st.locked_until = time.time() + LOGIN_LOCKOUT_DURATION_MIN * 60


async def _reset_state(username: str) -> None:
    """登录成功后清掉计数。"""
    async with _lock:
        _fail_state.pop(username, None)


def _reset_all_state_for_tests() -> None:
    """仅供测试使用，无锁清空全部状态。"""
    _fail_state.clear()


_INVALID = BusinessError(
    code="401_AUTH_INVALID_CREDENTIAL_001",
    message="用户名或密码错误",
    http_status=401,
)


def _refresh_invalid() -> BusinessError:
    return BusinessError(
        code="401_AUTH_TOKEN_INVALID_001",
        message="Refresh Token 失效",
        http_status=401,
    )


def _refresh_expired() -> BusinessError:
    return BusinessError(
        code="401_AUTH_TOKEN_EXPIRED_001",
        message="Refresh Token 已过期",
        http_status=401,
    )


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def login(self, username: str, password: str) -> TokenResponse:
        # 1) 锁定守卫（即使密码正确也拒绝）
        await _check_locked(username)

        # 2) 查用户 + 三种失败统一返回 _INVALID（防用户名枚举）
        user: User | None = await self.users.get_by_username(username)
        if user is None or not user.is_active or not verify_password(
            password, user.password_hash
        ):
            await _record_failure(username)
            raise _INVALID

        # 3) 成功：清状态 + 更新 last_login_at + 颁发双 token
        await _reset_state(username)
        await self.session.execute(
            update(User).where(User.id == user.id).values(last_login_at=func.now())
        )

        roles, _perms = await self.users.get_roles_and_permissions(user.id)
        access = create_access_token(user_id=user.id, roles=roles)
        refresh = create_refresh_token(user_id=user.id)

        await self.session.commit()
        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=access_token_expires_in(),
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """用 Refresh Token 换新的 access + refresh。

        对照 API_SPEC §1（POST /auth/refresh，401 Refresh Token 失效）
        + BUSINESS_RULES §6.1。

        失败路径统一返回 401_AUTH_TOKEN_INVALID_001（type 不匹配 / sub 异常 /
        用户停用 / 签名错），过期单独抛 401_AUTH_TOKEN_EXPIRED_001。
        """
        try:
            payload = decode_token(refresh_token)
        except ExpiredSignatureError as exc:
            raise _refresh_expired() from exc
        except JWTError as exc:
            raise _refresh_invalid() from exc

        if payload.get("type") != TOKEN_TYPE_REFRESH:
            raise _refresh_invalid()

        sub = payload.get("sub")
        if not sub:
            raise _refresh_invalid()
        try:
            user_id = UUID(str(sub))
        except (ValueError, TypeError) as exc:
            raise _refresh_invalid() from exc

        user = await self.users.find_by_id(user_id)
        if user is None or not user.is_active:
            raise _refresh_invalid()

        roles, _ = await self.users.get_roles_and_permissions(user.id)
        new_access = create_access_token(user_id=user.id, roles=roles)
        new_refresh = create_refresh_token(user_id=user.id)
        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=access_token_expires_in(),
        )
