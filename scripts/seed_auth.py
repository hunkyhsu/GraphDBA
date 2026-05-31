import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from graphdba.app.core.security import hash_password
from graphdba.database.repositories import (
    business_databases,
    role_databases,
    roles,
    user_roles,
    users,
)
from graphdba.database.session import AsyncSessionLocal, engine


@dataclass(frozen=True)
class SeedUser:
    employee_id: str
    name: str
    password: str
    role_name: str


@dataclass(frozen=True)
class SeedRole:
    name: str
    role_type: str
    description: str
    can_view_alerts: bool
    can_approve_tickets: bool


@dataclass(frozen=True)
class SeedDatabase:
    cluster_name: str
    database_name: str
    host: str
    port: int
    environment: str
    agent_rolename: str


SEED_ROLES = [
    SeedRole(
        name="ClusterA_manager",
        role_type="MANAGER",
        description="Can view and approve changes for ClusterA development databases.",
        can_view_alerts=True,
        can_approve_tickets=True,
    ),
    SeedRole(
        name="ClusterA_viewer",
        role_type="VIEWER",
        description="Can view ClusterA development alerts but cannot approve changes.",
        can_view_alerts=True,
        can_approve_tickets=False,
    ),
]

SEED_USERS = [
    SeedUser(
        employee_id="E10001",
        name="Alice",
        password="alice123",
        role_name="ClusterA_manager",
    ),
    SeedUser(
        employee_id="E10002",
        name="Bob",
        password="bob123",
        role_name="ClusterA_viewer",
    ),
]

SEED_DATABASES = [
    SeedDatabase(
        cluster_name="ClusterA",
        database_name="db_1",
        host="127.0.0.1",
        port=5432,
        environment="DEV",
        agent_rolename="graphdba_agent",
    ),
    SeedDatabase(
        cluster_name="ClusterA",
        database_name="db_2",
        host="127.0.0.1",
        port=5432,
        environment="DEV",
        agent_rolename="graphdba_agent",
    ),
]


async def seed_auth_data() -> None:
    async with AsyncSessionLocal() as session:
        role_by_name = {}
        for seed_role in SEED_ROLES:
            role = await roles.get_role_by_name(session, seed_role.name)
            if role is None:
                role = await roles.create_role(
                    session,
                    name=seed_role.name,
                    role_type=seed_role.role_type,
                    description=seed_role.description,
                    can_view_alerts=seed_role.can_view_alerts,
                    can_approve_tickets=seed_role.can_approve_tickets,
                )
            role_by_name[seed_role.name] = role

        database_by_name = {}
        for seed_database in SEED_DATABASES:
            database = await business_databases.get_business_database(
                session,
                cluster_name=seed_database.cluster_name,
                database_name=seed_database.database_name,
                environment=seed_database.environment,
            )
            if database is None:
                database = await business_databases.create_business_database(
                    session,
                    cluster_name=seed_database.cluster_name,
                    database_name=seed_database.database_name,
                    host=seed_database.host,
                    port=seed_database.port,
                    environment=seed_database.environment,
                    agent_rolename=seed_database.agent_rolename,
                )
            database_by_name[seed_database.database_name] = database

        manager_role = role_by_name["ClusterA_manager"]
        viewer_role = role_by_name["ClusterA_viewer"]
        for database in database_by_name.values():
            await role_databases.grant_role_database_access(
                session,
                role_id=manager_role.id,
                database_id=database.id,
                can_view=True,
                can_approve=True,
            )

        await role_databases.grant_role_database_access(
            session,
            role_id=viewer_role.id,
            database_id=database_by_name["db_1"].id,
            can_view=True,
            can_approve=False,
        )

        for seed_user in SEED_USERS:
            user = await users.get_user_by_employee_id(session, seed_user.employee_id)
            if user is None:
                user = await users.create_user(
                    session,
                    employee_id=seed_user.employee_id,
                    name=seed_user.name,
                    password_hash=hash_password(seed_user.password),
                    password_changed_at=datetime.now(timezone.utc),
                )

            role = role_by_name[seed_user.role_name]
            await user_roles.assign_role_to_user(
                session,
                user_id=user.id,
                role_id=role.id,
            )

        await session.commit()


async def main() -> None:
    try:
        await seed_auth_data()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
