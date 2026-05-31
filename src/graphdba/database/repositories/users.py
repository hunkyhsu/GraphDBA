from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.database.models.user import User


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_employee_id(
    session: AsyncSession,
    employee_id: str,
) -> User | None:
    stmt = select(User).where(User.employee_id == employee_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    employee_id: str,
    name: str,
    password_hash: str,
    is_active: bool = True,
    password_changed_at: datetime | None = None,
) -> User:
    user = User(
        employee_id=employee_id,
        name=name,
        password_hash=password_hash,
        is_active=is_active,
        password_changed_at=password_changed_at,
    )
    session.add(user)
    await session.flush()
    return user


async def record_failed_login(
    session: AsyncSession,
    user: User,
    *,
    locked_until: datetime | None = None,
) -> User:
    user.failed_login_count += 1
    user.locked_until = locked_until
    await session.flush()
    return user


async def reset_login_failures(session: AsyncSession, user: User) -> User:
    user.failed_login_count = 0
    user.locked_until = None
    await session.flush()
    return user


async def update_user_password(
    session: AsyncSession,
    user: User,
    *,
    password_hash: str,
    password_changed_at: datetime,
) -> User:
    user.password_hash = password_hash
    user.password_changed_at = password_changed_at
    user.failed_login_count = 0
    user.locked_until = None
    await session.flush()
    return user


async def set_user_active(
    session: AsyncSession,
    user: User,
    *,
    is_active: bool,
) -> User:
    user.is_active = is_active
    await session.flush()
    return user
