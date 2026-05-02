"""异步数据库会话工厂。

对照 CONVENTIONS §2.2 / §12.2：
- 全异步（asyncpg + create_async_engine）
- get_db() 用于 FastAPI Depends，每次请求一个 session，自动 close
- expire_on_commit=False，避免 commit 后属性懒加载触发额外查询
"""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每个请求一个 AsyncSession。"""
    async with async_session_maker() as session:
        yield session
