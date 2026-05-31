from enum import StrEnum
from typing import TYPE_CHECKING
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Identity,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from graphdba.database.base import AuditMixin, Base

if TYPE_CHECKING:
    from graphdba.database.models.user_role import UserRole
    from graphdba.database.models.role_database import RoleDatabase

class RoleType(StrEnum):
    VIEWER="VIEWER"
    MANAGER="MANAGER"
    ADMIN="ADMIN"

class Role(Base, AuditMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
    )
    type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=RoleType.MANAGER.value,
        server_default=text("'MANAGER'"),
    )
    __table_args__ = (
        CheckConstraint(
            type.in_([e.value for e in RoleType]),
            name="ck_roles_type",
        ),
    )
    description: Mapped[str | None] = mapped_column(
        Text,
    )
    can_view_alerts: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    can_approve_tickets: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    users: Mapped[list["UserRole"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )
    databases: Mapped[list["RoleDatabase"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )
