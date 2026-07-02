"""Модель локального агента печати студии."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class PrintAgent(Base):
    """Агент печати, привязанный к студии (пайринг по коду → токен)."""

    __tablename__ = "print_agents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    token_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    pairing_code: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    paired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    printer_status: Mapped[str] = mapped_column(String(255), default="")
    queue_len: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<PrintAgent studio={self.studio_id} name={self.name}>"
