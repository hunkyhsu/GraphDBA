from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.config.settings import get_settings
from graphdba.database.models.alert import Alert
from graphdba.database.models.business_database import BusinessDatabase
from graphdba.database.repositories import business_databases


class FastPathScriptError(Exception):
    """Raised when a fast-path script cannot safely complete."""


@dataclass(frozen=True)
class FastPathScriptResult:
    solved: bool
    metadata: dict[str, Any]


FastPathScriptHandler = Callable[[AsyncSession, Alert], Awaitable[FastPathScriptResult]]

CONNECTION_EXHAUSTED_HANDLER_KEY = "postgres_connections_exhausted_fast_path"
MAX_TERMINATED_IDLE_TRANSACTIONS = 5
IDLE_IN_TRANSACTION_MINUTES = 10
SOLVED_CONNECTION_RATIO = 0.90
EXCLUDED_USERS = ("postgres", "replication", "graphdba_agent")


async def resolve_business_database_target(
    session: AsyncSession,
    alert: Alert,
) -> BusinessDatabase | None:
    target = await business_databases.find_business_database_for_alert_target(
        session,
        cluster_name=alert.cluster_name,
        database_name=alert.database_name,
        environment=alert.environment,
        host=alert.host,
        port=alert.port,
    )
    if target is not None:
        return target

    if alert.database_name is None:
        return await business_databases.find_business_database_for_alert_target(
            session,
            cluster_name=alert.cluster_name,
            environment=alert.environment,
            host=alert.host,
            port=alert.port,
        )
    return None


def connection_kwargs(target: BusinessDatabase) -> dict[str, Any]:
    settings = get_settings().database
    return {
        "host": target.host,
        "port": target.port,
        "database": target.database_name,
        "user": target.agent_rolename,
        "password": settings.password,
        "server_settings": {
            "application_name": "graphdba_fast_path",
            "statement_timeout": str(get_settings().security.max_query_timeout_ms),
        },
    }


async def handle_postgres_connections_exhausted(
    session: AsyncSession,
    alert: Alert,
) -> FastPathScriptResult:
    target = await resolve_business_database_target(session, alert)
    if target is None:
        raise FastPathScriptError("No active business database target found for alert")

    conn = await asyncpg.connect(**connection_kwargs(target))
    try:
        before = await fetch_connection_usage(conn)
        victims = await conn.fetch(
            """
            SELECT pid, usename, application_name, state, now() - xact_start AS age
            FROM pg_stat_activity
            WHERE state = 'idle in transaction'
              AND xact_start < now() - ($1 * interval '1 minute')
              AND pid <> pg_backend_pid()
              AND usename <> ALL($2::text[])
            ORDER BY xact_start ASC
            LIMIT $3
            """,
            IDLE_IN_TRANSACTION_MINUTES,
            list(EXCLUDED_USERS),
            MAX_TERMINATED_IDLE_TRANSACTIONS,
        )

        terminated = []
        for victim in victims:
            terminated_ok = await conn.fetchval("SELECT pg_terminate_backend($1)", victim["pid"])
            terminated.append(
                {
                    "pid": victim["pid"],
                    "usename": victim["usename"],
                    "application_name": victim["application_name"],
                    "state": victim["state"],
                    "age": str(victim["age"]),
                    "terminated": bool(terminated_ok),
                }
            )

        after = await fetch_connection_usage(conn)
        solved = after["connection_ratio"] < SOLVED_CONNECTION_RATIO
        return FastPathScriptResult(
            solved=solved,
            metadata={
                "target": {
                    "cluster_name": target.cluster_name,
                    "database_name": target.database_name,
                    "environment": target.environment,
                    "host": target.host,
                    "port": target.port,
                    "agent_rolename": target.agent_rolename,
                },
                "limits": {
                    "idle_in_transaction_minutes": IDLE_IN_TRANSACTION_MINUTES,
                    "max_terminated_sessions": MAX_TERMINATED_IDLE_TRANSACTIONS,
                    "solved_connection_ratio": SOLVED_CONNECTION_RATIO,
                    "excluded_users": list(EXCLUDED_USERS),
                },
                "before": before,
                "after": after,
                "terminated_sessions": terminated,
            },
        )
    finally:
        await conn.close()


async def fetch_connection_usage(conn: asyncpg.Connection) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        SELECT
          count(*)::int AS active_connections,
          current_setting('max_connections')::int AS max_connections,
          count(*)::float / current_setting('max_connections')::int AS connection_ratio
        FROM pg_stat_activity
        """
    )
    return {
        "active_connections": row["active_connections"],
        "max_connections": row["max_connections"],
        "connection_ratio": row["connection_ratio"],
    }


FAST_PATH_SCRIPT_HANDLERS: dict[str, FastPathScriptHandler] = {
    CONNECTION_EXHAUSTED_HANDLER_KEY: handle_postgres_connections_exhausted,
}


async def run_fast_path_script(
    session: AsyncSession,
    *,
    handler_key: str | None,
    alert: Alert,
) -> FastPathScriptResult:
    if handler_key is None:
        raise FastPathScriptError("Fast-path policy is missing handler_key")

    handler = FAST_PATH_SCRIPT_HANDLERS.get(handler_key)
    if handler is None:
        raise FastPathScriptError(f"Unknown fast-path handler: {handler_key}")

    return await handler(session, alert)
