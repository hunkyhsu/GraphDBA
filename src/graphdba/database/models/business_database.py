from enum import StrEnum
from typing import TYPE_CHECKING
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Identity,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from graphdba.database.base import AuditMixin, Base

if TYPE_CHECKING:
    from graphdba.database.models.role_database import RoleDatabase

class Environment(StrEnum):
    PROD="PROD"
    DEV="DEV"
    STAGE="STAGE"

class BusinessDatabase(Base, AuditMixin):
    __tablename__ = "business_databases"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    cluster_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    database_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    host: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    environment: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=Environment.DEV.value,
        server_default=text("'DEV'"),
    )
    __table_args__ = (
        CheckConstraint(
            environment.in_([e.value for e in Environment]),
            name="ck_business_databases_environment",
        ),
        UniqueConstraint(
            "cluster_name",
            "database_name",
            "environment",
            name="uq_business_databases_cluster_database_environment",
        ),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    agent_rolename: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    roles: Mapped[list["RoleDatabase"]] = relationship(
        back_populates="database",
        cascade="all, delete-orphan",
    )
