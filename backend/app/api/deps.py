"""FastAPI 依赖：JWT 解析、当前用户、权限校验。

对照：
- API_SPEC §0.2（JWT Bearer / 公开接口清单）
- BUSINESS_RULES §6.1
  * 401_AUTH_TOKEN_EXPIRED_001
  * 401_AUTH_TOKEN_INVALID_001
  * 403_AUTH_PERMISSION_DENIED_001
- DATA_CONTRACTS §5（CurrentUser）

设计决策：
- oauth2_scheme.auto_error=False：缺/坏 token 由本模块统一翻译为
  BusinessError，避免 FastAPI 默认 401 响应不带项目错误码
- access token payload 不放 permissions，每次依赖调用从 DB 加载最新
  roles/permissions，保证权限调整立刻生效（成本：1 次 JOIN）
- 用户不存在 / is_active=False / sub 无法解析为 UUID / type≠access
  统一返回 401_AUTH_TOKEN_INVALID_001，不暴露具体原因（防探测）
- require_permission 用 FastAPI 依赖工厂模式（Depends 工厂），不写成
  decorator —— 路由参数依赖系统更天然，且与 OpenAPI schema 兼容
"""
from __future__ import annotations

from typing import Awaitable, Callable
from uuid import UUID

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.session import get_db
from app.repositories.user import UserRepository
from app.schemas.auth import CurrentUser

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)


def _token_invalid() -> BusinessError:
    return BusinessError(
        code="401_AUTH_TOKEN_INVALID_001",
        message="Token 格式错误或被吊销",
        http_status=401,
    )


def _token_expired() -> BusinessError:
    return BusinessError(
        code="401_AUTH_TOKEN_EXPIRED_001",
        message="Access Token 已过期",
        http_status=401,
    )


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """解析 Authorization: Bearer <token>，返回 CurrentUser。

    抛错路径：
    - 缺 token / 类型不是 access / sub 非 UUID / 用户不存在或停用
        → 401_AUTH_TOKEN_INVALID_001
    - JWT 已过期 → 401_AUTH_TOKEN_EXPIRED_001
    - JWT 签名/格式错 → 401_AUTH_TOKEN_INVALID_001
    """
    if not token:
        raise _token_invalid()

    try:
        payload = decode_token(token)
    except ExpiredSignatureError as exc:
        raise _token_expired() from exc
    except JWTError as exc:
        raise _token_invalid() from exc

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise _token_invalid()

    sub = payload.get("sub")
    if not sub:
        raise _token_invalid()
    try:
        user_id = UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise _token_invalid() from exc

    users = UserRepository(db)
    user = await users.find_by_id(user_id)
    if user is None or not user.is_active:
        raise _token_invalid()

    roles, perms = await users.get_roles_and_permissions(user.id)

    return CurrentUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        roles=roles,
        permissions=perms,
    )


def require_permission(
    perm: str,
) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    """依赖工厂：要求 current_user 拥有指定权限。

    用法：
        @router.post("/robots")
        async def create_robot(
            current: CurrentUser = Depends(require_permission("robot:manage")),
        ): ...

    不命中权限抛 403_AUTH_PERMISSION_DENIED_001（对照 BUSINESS_RULES §6.1）。
    """

    async def _checker(
        current: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if perm not in current.permissions:
            raise BusinessError(
                code="403_AUTH_PERMISSION_DENIED_001",
                message=f"权限不足：缺少 {perm}",
                http_status=403,
            )
        return current

    return _checker
