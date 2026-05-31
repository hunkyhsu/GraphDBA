from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.database.models.business_database import BusinessDatabase


async def get_business_database_by_id(
    session: AsyncSession,
    database_id: int,
) -> BusinessDatabase | None:
    return await session.get(BusinessDatabase, database_id)


async def get_business_database(
    session: AsyncSession,
    *,
    cluster_name: str,
    database_name: str,
    environment: str,
) -> BusinessDatabase | None:
    stmt = select(BusinessDatabase).where(
        BusinessDatabase.cluster_name == cluster_name,
        BusinessDatabase.database_name == database_name,
        BusinessDatabase.environment == environment,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_active_business_databases(
    session: AsyncSession,
) -> list[BusinessDatabase]:
    stmt = (
        select(BusinessDatabase)
        .where(BusinessDatabase.is_active.is_(True))
        .order_by(
            BusinessDatabase.environment,
            BusinessDatabase.cluster_name,
            BusinessDatabase.database_name,
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_business_database(
    session: AsyncSession,
    *,
    cluster_name: str,
    database_name: str,
    host: str,
    port: int,
    agent_rolename: str,
    environment: str = "DEV",
    is_active: bool = True,
) -> BusinessDatabase:
    database = BusinessDatabase(
        cluster_name=cluster_name,
        database_name=database_name,
        host=host,
        port=port,
        environment=environment,
        is_active=is_active,
        agent_rolename=agent_rolename,
    )
    session.add(database)
    await session.flush()
    return database


async def set_business_database_active(
    session: AsyncSession,
    database: BusinessDatabase,
    *,
    is_active: bool,
) -> BusinessDatabase:
    database.is_active = is_active
    await session.flush()
    return database
