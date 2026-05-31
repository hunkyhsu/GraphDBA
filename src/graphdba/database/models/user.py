from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import BigInteger, Boolean, DateTime, Identity, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from graphdba.database.base import AuditMixin, Base

if TYPE_CHECKING:
    from graphdba.database.models.user_role import UserRole

class User(Base, AuditMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    employee_id: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
