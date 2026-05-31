from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from graphdba.database.base import Base

if TYPE_CHECKING:
    from graphdba.database.models.role import Role
    from graphdba.database.models.business_database import BusinessDatabase

class RoleDatabase(Base):
    __tablename__ = "role_database"

    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    database_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("business_databases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    can_view: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    can_approve: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    role: Mapped["Role"] = relationship(back_populates="databases")
    database: Mapped["BusinessDatabase"] = relationship(back_populates="roles")
