"""Модель пользователя."""
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import BigInteger, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.order import Order
    from src.models.studio import Studio


class User(Base):
    """Пользователь бота (в рамках конкретной студии)."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("studio_id", "telegram_id", name="uq_user_studio_telegram"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    studio: Mapped["Studio"] = relationship(lazy="selectin")
    orders: Mapped[List["Order"]] = relationship(back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User s{self.studio_id}:{self.telegram_id}: {self.username or self.first_name}>"

    @property
    def display_name(self) -> str:
        if self.first_name:
            if self.last_name:
                return f"{self.first_name} {self.last_name}"
            return self.first_name
        return self.username or f"User_{self.telegram_id}"
