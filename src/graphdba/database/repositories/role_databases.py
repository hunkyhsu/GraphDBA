from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.database.models.role import Role
from graphdba.database.models.business_database import BusinessDatabase
from graphdba.database.models.role_database import RoleDatabase
from graphdba.database.models.user_role import UserRole

async def get_role_database(
    session: AsyncSession,
    *,
    role_id: int,
    database_id: int,
) -> RoleDatabase | None:
    stmt = select(RoleDatabase).where(
        RoleDatabase.role_id == role_id,
        RoleDatabase.database_id == database_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_databases_for_role(
    session: AsyncSession,
    role_id: int,
) -> list[BusinessDatabase]:
    stmt = (
        select(BusinessDatabase)
        .join(RoleDatabase, RoleDatabase.database_id == BusinessDatabase.id)
        .where(
            RoleDatabase.role_id == role_id,
            BusinessDatabase.is_active.is_(True),
        )
        .order_by(
            BusinessDatabase.environment,
            BusinessDatabase.cluster_name,
            BusinessDatabase.database_name,
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def grant_role_database_access(
    session: AsyncSession,
    *,
    role_id: int,
    database_id: int,
    can_view: bool = True,
    can_approve: bool = True,
) -> RoleDatabase:
    existing = await get_role_database(
        session,
        role_id=role_id,
        database_id=database_id,
    )
    if existing is not None:
        existing.can_view = can_view
        existing.can_approve = can_approve
        await session.flush()
        return existing

    permission = RoleDatabase(
        role_id=role_id,
        database_id=database_id,
        can_view=can_view,
        can_approve=can_approve,
    )
    session.add(permission)
    await session.flush()
    return permission


async def revoke_role_database_access(
    session: AsyncSession,
    *,
    role_id: int,
    database_id: int,
) -> bool:
    stmt = delete(RoleDatabase).where(
        RoleDatabase.role_id == role_id,
        RoleDatabase.database_id == database_id,
    ).returning(RoleDatabase.role_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def user_can_view_database(
    session: AsyncSession,
    *,
    user_id: int,
    database_id: int,
) -> bool:
    stmt = select(
        exists().where(
            UserRole.user_id == user_id,
            UserRole.role_id == Role.id,
            Role.is_active.is_(True),
            Role.can_view_alerts.is_(True),
            RoleDatabase.role_id == Role.id,
            RoleDatabase.database_id == database_id,
            RoleDatabase.can_view.is_(True),
        )
    )
    result = await session.execute(stmt)
    return bool(result.scalar())


async def user_can_approve_database(
    session: AsyncSession,
    *,
    user_id: int,
    database_id: int,
) -> bool:
    stmt = select(
        exists().where(
            UserRole.user_id == user_id,
            UserRole.role_id == Role.id,
            Role.is_active.is_(True),
            Role.can_approve_tickets.is_(True),
            RoleDatabase.role_id == Role.id,
            RoleDatabase.database_id == database_id,
            RoleDatabase.can_approve.is_(True),
        )
    )
    result = await session.execute(stmt)
    return bool(result.scalar())
