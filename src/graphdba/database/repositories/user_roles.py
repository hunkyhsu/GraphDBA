from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.database.models.role import Role
from graphdba.database.models.user_role import UserRole


async def get_user_role(
    session: AsyncSession,
    *,
    user_id: int,
    role_id: int,
) -> UserRole | None:
    stmt = select(UserRole).where(
        UserRole.user_id == user_id,
        UserRole.role_id == role_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_roles_for_user(session: AsyncSession, user_id: int) -> list[Role]:
    stmt = (
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            Role.is_active.is_(True),
        )
        .order_by(Role.name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def assign_role_to_user(
    session: AsyncSession,
    *,
    user_id: int,
    role_id: int,
) -> UserRole:
    existing = await get_user_role(session, user_id=user_id, role_id=role_id)
    if existing is not None:
        return existing

    user_role = UserRole(user_id=user_id, role_id=role_id)
    session.add(user_role)
    await session.flush()
    return user_role


async def remove_role_from_user(
    session: AsyncSession,
    *,
    user_id: int,
    role_id: int,
) -> bool:
    stmt = delete(UserRole).where(
        UserRole.user_id == user_id,
        UserRole.role_id == role_id,
    ).returning(UserRole.user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
