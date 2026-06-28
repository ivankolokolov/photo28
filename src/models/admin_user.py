"""Модель администратора (super_admin / studio_admin)."""
from enum import Enum
from typing import Optional
from sqlalchemy import String, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class AdminRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    STUDIO_ADMIN = "studio_admin"


class AdminUser(Base):
    """Учётная запись для входа в админку."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[AdminRole] = mapped_column(SQLEnum(AdminRole), default=AdminRole.STUDIO_ADMIN)
    # NULL для super_admin, иначе — id студии
    studio_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), nullable=True, index=True
    )

    def __repr__(self) -> str:
        return f"<AdminUser {self.username} ({self.role.value})>"
