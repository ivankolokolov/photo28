"""Модель заказа."""
from enum import Enum
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, Enum as SQLEnum, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.user import User
    from src.models.photo import Photo


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
    
    @property
    def display_name(self) -> str:
        """Название способа доставки."""
        names = {
            DeliveryType.OZON: "ОЗОН доставка",
            DeliveryType.COURIER: "Курьер",
            DeliveryType.PICKUP: "Самовывоз",
        }
        return names[self]
    
    @property
    def delivery_cost(self) -> int:
        """Стоимость доставки в рублях."""
        costs = {
            DeliveryType.OZON: 100,
            DeliveryType.COURIER: 0,  # По согласованию
            DeliveryType.PICKUP: 0,
        }
        return costs[self]


class Order(Base):
    """Заказ пользователя."""
    
    __tablename__ = "orders"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    
    # Номер заказа для отображения клиенту
    order_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    
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
    
    def photos_by_format(self) -> dict:
        """Группировка фотографий по форматам."""
        from collections import Counter
        from src.models.photo import PhotoFormat
        
        if not self.photos:
            return {}
        
        counts = Counter(photo.format for photo in self.photos)
        return {fmt: counts.get(fmt, 0) for fmt in PhotoFormat if counts.get(fmt, 0) > 0}

