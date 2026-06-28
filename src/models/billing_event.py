"""Событие тарификации — один напечатанный отпечаток (наполняется в под-проекте №2)."""
from decimal import Decimal
from datetime import datetime
from sqlalchemy import Integer, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class BillingEvent(Base):
    """Факт печати одного изображения = одна единица комиссии платформы."""

    __tablename__ = "billing_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    photo_position: Mapped[int] = mapped_column(Integer, default=0)
    fee: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    printed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<BillingEvent studio={self.studio_id} order={self.order_id} fee={self.fee}>"
