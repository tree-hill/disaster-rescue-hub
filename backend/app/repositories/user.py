"""User 数据访问层。

对照 BUILD_ORDER P2.2（get_by_username / find_by_id / save）+ 一个辅助方法
get_roles_and_permissions（避免把 SQL 漏到 service 层，违反 CONVENTIONS §1.2）。

User / Role / UserRole 模型未定义 SQLAlchemy relationship()，因此 roles +
permissions 用显式 JOIN 查询。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Role, User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def save(self, user: User) -> User:
        """新增或附加已存在的对象（不在此 commit，由调用方控制事务边界）。"""
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_roles_and_permissions(
        self, user_id: UUID
    ) -> tuple[list[str], list[str]]:
        """返回 (roles_names_sorted, permissions_sorted_unique)。"""
        stmt = (
            select(Role.name, Role.permissions)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        rows = (await self.session.execute(stmt)).all()
        role_names: list[str] = []
        perms: set[str] = set()
        for name, perm_list in rows:
            role_names.append(name)
            for p in perm_list or []:
                perms.add(p)
        return sorted(role_names), sorted(perms)
