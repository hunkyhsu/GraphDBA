import asyncio
import os
import re
from dataclasses import dataclass

import asyncpg

from graphdba.config.settings import get_settings
from graphdba.database.repositories import business_databases
from graphdba.database.session import AsyncSessionLocal, engine


IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


@dataclass(frozen=True)
class SeedBusinessDatabase:
    cluster_name: str
    database_name: str
    host: str
    port: int
    environment: str
    agent_rolename: str


SEED_BUSINESS_DATABASES = [
    SeedBusinessDatabase(
        cluster_name="ClusterA",
        database_name="business_db_a",
        host="127.0.0.1",
        port=5432,
        environment="DEV",
        agent_rolename="graphdba_agent",
    ),
    SeedBusinessDatabase(
        cluster_name="ClusterA",
        database_name="business_db_b",
        host="127.0.0.1",
        port=5432,
        environment="DEV",
        agent_rolename="graphdba_agent",
    ),
]


def quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"Unsafe PostgreSQL identifier: {identifier}")
    return f'"{identifier}"'


def admin_connection_kwargs(database: str) -> dict[str, object]:
    settings = get_settings().database
    return {
        "host": os.getenv("BUSINESS_SEED__HOST", settings.host),
        "port": int(os.getenv("BUSINESS_SEED__PORT", str(settings.port))),
        "user": os.getenv("BUSINESS_SEED__USER", settings.user),
        "password": os.getenv("BUSINESS_SEED__PASSWORD", settings.password),
        "database": database,
    }


async def ensure_database_exists(seed_database: SeedBusinessDatabase) -> None:
    maintenance_database = os.getenv("BUSINESS_SEED__MAINTENANCE_DB", "postgres")
    conn = await asyncpg.connect(**admin_connection_kwargs(maintenance_database))
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            seed_database.database_name,
        )
        if exists:
            return

        await conn.execute(
            f"CREATE DATABASE {quote_identifier(seed_database.database_name)}"
        )
    finally:
        await conn.close()


async def seed_business_schema(seed_database: SeedBusinessDatabase) -> None:
    conn = await asyncpg.connect(**admin_connection_kwargs(seed_database.database_name))
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                order_ref TEXT NOT NULL UNIQUE,
                customer_id BIGINT NOT NULL REFERENCES customers(id),
                amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
                order_status TEXT NOT NULL DEFAULT 'created',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            """
            INSERT INTO customers (email, full_name, status)
            VALUES
                ('alice@example.test', 'Alice Example', 'active'),
                ('bob@example.test', 'Bob Example', 'active')
            ON CONFLICT (email) DO NOTHING
            """
        )
        await conn.execute(
            """
            INSERT INTO orders (order_ref, customer_id, amount_cents, order_status)
            SELECT 'seed-order-001', id, 1200, 'created'
            FROM customers
            WHERE email = 'alice@example.test'
            ON CONFLICT (order_ref) DO NOTHING
            """
        )
    finally:
        await conn.close()


async def register_business_databases() -> None:
    async with AsyncSessionLocal() as session:
        for seed_database in SEED_BUSINESS_DATABASES:
            existing = await business_databases.get_business_database(
                session,
                cluster_name=seed_database.cluster_name,
                database_name=seed_database.database_name,
                environment=seed_database.environment,
            )
            if existing is not None:
                continue

            await business_databases.create_business_database(
                session,
                cluster_name=seed_database.cluster_name,
                database_name=seed_database.database_name,
                host=seed_database.host,
                port=seed_database.port,
                environment=seed_database.environment,
                agent_rolename=seed_database.agent_rolename,
            )

        await session.commit()


async def seed_business_databases() -> None:
    for seed_database in SEED_BUSINESS_DATABASES:
        await ensure_database_exists(seed_database)
        await seed_business_schema(seed_database)

    await register_business_databases()


async def main() -> None:
    try:
        await seed_business_databases()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
