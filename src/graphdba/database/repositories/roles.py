from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.database.models.role import Role


async def get_role_by_id(session: AsyncSession, role_id: int) -> Role | None:
    return await session.get(Role, role_id)


async def get_role_by_name(session: AsyncSession, name: str) -> Role | None:
    stmt = select(Role).where(Role.name == name)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_active_roles(session: AsyncSession) -> list[Role]:
    stmt = select(Role).where(Role.is_active.is_(True)).order_by(Role.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_role(
    session: AsyncSession,
    *,
    name: str,
    role_type: str = "MANAGER",
    description: str | None = None,
    can_view_alerts: bool = True,
    can_approve_tickets: bool = True,
    is_active: bool = True,
) -> Role:
    role = Role(
        name=name,
        type=role_type,
        description=description,
        can_view_alerts=can_view_alerts,
        can_approve_tickets=can_approve_tickets,
        is_active=is_active,
    )
    session.add(role)
    await session.flush()
    return role


async def set_role_active(
    session: AsyncSession,
    role: Role,
    *,
    is_active: bool,
) -> Role:
    role.is_active = is_active
    await session.flush()
    return role
