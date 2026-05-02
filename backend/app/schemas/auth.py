"""认证相关 Pydantic v2 Schemas。

严格对照 DATA_CONTRACTS §5（Auth Schemas）和 API_SPEC §1（/auth/* 接口）。
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(..., min_length=1, max_length=50)
    # bcrypt 上限 72B，留 128 给 Pydantic 兜底；service 层再做精确处理
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # 秒，对应 JWT access TTL


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class CurrentUser(BaseModel):
    id: UUID
    username: str
    display_name: str
    roles: list[str]
    permissions: list[str]
