"""密码哈希 + JWT 编/解码。

对照：
- CONVENTIONS §11（bcrypt work factor 12，JWT 不放敏感数据）
- API_SPEC §0.2（Access 24h / Refresh 7d，HS256 Bearer）
- DATA_CONTRACTS §5（CurrentUser.roles）
- BUSINESS_RULES §6.1（401_AUTH_TOKEN_EXPIRED_001 / 401_AUTH_TOKEN_INVALID_001）

设计：
- payload 只放 sub（user_id）+ roles + type + exp + iat，不放 username/display_name
- decode_token 直接抛 jose 原生异常（ExpiredSignatureError / JWTError），由 P2.4
  中间件统一翻译为 BusinessError 与对应错误码
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt work factor 12，对照 CONVENTIONS.md §11
_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _encode(
    sub: str,
    token_type: str,
    ttl: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": sub,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: UUID | str, roles: list[str]) -> str:
    return _encode(
        sub=str(user_id),
        token_type=TOKEN_TYPE_ACCESS,
        ttl=timedelta(hours=settings.jwt_access_ttl_hours),
        extra={"roles": roles},
    )


def create_refresh_token(user_id: UUID | str) -> str:
    return _encode(
        sub=str(user_id),
        token_type=TOKEN_TYPE_REFRESH,
        ttl=timedelta(days=settings.jwt_refresh_ttl_days),
    )


def decode_token(token: str) -> dict[str, Any]:
    """解码 JWT。

    可能抛 jose.ExpiredSignatureError / jose.JWTError，调用方（P2.4 中间件）
    需将其翻译为 401_AUTH_TOKEN_EXPIRED_001 / 401_AUTH_TOKEN_INVALID_001。
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def access_token_expires_in() -> int:
    """Access Token 寿命（秒），用于 TokenResponse.expires_in。"""
    return settings.jwt_access_ttl_hours * 3600
