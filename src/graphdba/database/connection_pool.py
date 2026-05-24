from __future__ import annotations
from collections.abc import AsyncIterator
import logging
import asyncpg
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from graphdba.config.settings import get_settings

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_db_pool() -> AsyncIterator[asyncpg.Pool]:
    """
    Creates and yields a robust asyncpg connection pool.
    """
    pool = None
    database_settings = get_settings().database
    try:
        pool = await asyncpg.create_pool(
            host=database_settings.host,
            port=database_settings.port,
            database=database_settings.db,
            user=database_settings.user,
            password=database_settings.password,
            min_size=database_settings.min_connections,
            max_size=database_settings.max_connections,
            max_inactive_connection_lifetime=database_settings.max_inactive_connection_lifetime,
            server_settings={
                "application_name": "mcp_connection_pool",
                "statement_timeout": str(get_settings().security.max_query_timeout_ms)
            },
        )
        logger.info("Connection pool created. min_size=%d, max_size=%d", database_settings.min_connections, database_settings.max_connections)
        yield pool
    finally:
        if pool:
            await pool.close()
            logger.info("Connection pool closed.")

@asynccontextmanager
async def read_lifespan(_server: FastMCP) -> AsyncIterator[dict[str, asyncpg.Pool]]:
    """Read Server lifespan"""
    async with get_db_pool() as pool:
        yield {"Read MCP connection pool": pool}

@asynccontextmanager
async def write_lifespan(_server: FastMCP) -> AsyncIterator[dict[str, asyncpg.Pool]]:
    """Write Server lifespan"""
    async with get_db_pool() as pool:
        yield {"Write MCP connection pool": pool}