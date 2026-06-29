"""Модель заказа."""
from enum import Enum
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, Enum as SQLEnum, Text, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.user import User
    from src.models.photo import Photo
    from src.models.studio import Studio


class OrderStatus(str, Enum):
    """Статусы заказа."""
    DRAFT = "draft"              # Заказ формируется
    PENDING_PAYMENT = "pending_payment"  # Ожидает оплаты
    PAID = "paid"                # Оплачен, ожидает подтверждения
    CONFIRMED = "confirmed"      # Оплата подтверждена
    PRINTING = "printing"        # В печати
    READY = "ready"              # Готов к отправке
    SHIPPED = "shipped"          # Отправлен
    DELIVERED = "delivered"      # Доставлен
    CANCELLED = "cancelled"      # Отменён
    
    @property
    def display_name(self) -> str:
        """Название статуса для отображения."""
        names = {
            OrderStatus.DRAFT: "Формируется",
            OrderStatus.PENDING_PAYMENT: "Ожидает оплаты",
            OrderStatus.PAID: "Ожидает подтверждения",
            OrderStatus.CONFIRMED: "Подтверждён",
            OrderStatus.PRINTING: "В печати",
            OrderStatus.READY: "Готов к отправке",
            OrderStatus.SHIPPED: "Отправлен",
            OrderStatus.DELIVERED: "Доставлен",
            OrderStatus.CANCELLED: "Отменён",
        }
        return names[self]


class DeliveryType(str, Enum):
    """Способы доставки."""
    OZON = "ozon"
    COURIER = "courier"
    PICKUP = "pickup"


class Order(Base):
    """Заказ пользователя (в рамках студии)."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("studio_id", "order_number", name="uq_order_studio_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    # Номер заказа для отображения клиенту (уникален в рамках студии)
    order_number: Mapped[str] = mapped_column(String(20), index=True)

    # Статус заказа
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus),
        default=OrderStatus.DRAFT
    )
    
    # Способ доставки
    delivery_type: Mapped[Optional[DeliveryType]] = mapped_column(
        SQLEnum(DeliveryType),
        nullable=True
    )
    
    # Информация о доставке
    delivery_city: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    delivery_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivery_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    delivery_datetime: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Стоимость
    photos_cost: Mapped[int] = mapped_column(Integer, default=0)  # Стоимость фото в рублях
    delivery_cost: Mapped[int] = mapped_column(Integer, default=0)  # Стоимость доставки
    discount: Mapped[int] = mapped_column(Integer, default=0)  # Скидка в рублях
    promocode_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("promocodes.id"),
        nullable=True
    )
    
    # Квитанция об оплате (file_id)
    payment_receipt_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Дата оплаты
    paid_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    # Примечания менеджера
    manager_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="orders")
    studio: Mapped["Studio"] = relationship(lazy="selectin")
    photos: Mapped[List["Photo"]] = relationship(
        back_populates="order",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Order {self.order_number}: {self.status.value}>"
    
    @property
    def total_cost(self) -> int:
        """Итоговая стоимость заказа."""
        return self.photos_cost + self.delivery_cost - self.discount
    
    @property
    def photos_count(self) -> int:
        """Общее количество фотографий в заказе."""
        return len(self.photos) if self.photos else 0
    
    def photos_by_product(self) -> dict:
        """Группировка фотографий по товарам. Returns {product_id: count}."""
        from collections import Counter
        
        if not self.photos:
            return {}
        
        return dict(Counter(photo.product_id for photo in self.photos))
