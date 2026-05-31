from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from graphdba.config.settings import get_settings

database_settings = get_settings().database

engine: AsyncEngine = create_async_engine(
    database_settings.connection_string,
    echo=False,
    pool_size=database_settings.pool_size,
    max_overflow=database_settings.max_overflow,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session