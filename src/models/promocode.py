"""Модель промокода."""
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Promocode(Base):
    """Промокод для скидки."""
    
    __tablename__ = "promocodes"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Код промокода (уникальный, регистронезависимый)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    
    # Описание промокода
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Тип скидки: процент или фиксированная сумма
    discount_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Процент скидки
    discount_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # Фиксированная сумма в рублях
    
    # Ограничения
    min_order_amount: Mapped[int] = mapped_column(Integer, default=0)  # Минимальная сумма заказа
    min_photos: Mapped[int] = mapped_column(Integer, default=0)  # Минимальное количество фото в заказе
    require_subscription: Mapped[bool] = mapped_column(Boolean, default=False)  # Требуется подписка на канал
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Максимальное число использований
    current_uses: Mapped[int] = mapped_column(Integer, default=0)  # Текущее число использований
    
    # Даты действия
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Активность
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    def __repr__(self) -> str:
        return f"<Promocode {self.code}>"
    
    def is_valid(self, order_amount: int = 0, photos_count: int = 0) -> tuple[bool, str]:
        """
        Проверяет валидность промокода.
        
        Возвращает (is_valid, error_message).
        Подписку на канал проверяет вызывающий код через Telegram API.
        """
        if not self.is_active:
            return False, "Промокод неактивен"
        
        now = datetime.now()
        
        if self.valid_from and now < self.valid_from:
            return False, "Промокод ещё не активирован"
        
        if self.valid_until and now > self.valid_until:
            return False, "Срок действия промокода истёк"
        
        if self.max_uses and self.current_uses >= self.max_uses:
            return False, "Промокод исчерпан"
        
        if order_amount < self.min_order_amount:
            return False, f"Минимальная сумма заказа: {self.min_order_amount}₽"
        
        if self.min_photos > 0 and photos_count < self.min_photos:
            return False, f"Нужно минимум {self.min_photos} фото в заказе (сейчас {photos_count})"
        
        # require_subscription проверяется отдельно через Telegram Bot API
        
        return True, ""
    
    def calculate_discount(self, order_amount: int) -> int:
        """Рассчитывает размер скидки для заданной суммы заказа."""
        if self.discount_amount:
            return min(self.discount_amount, order_amount)
        
        if self.discount_percent:
            return int(order_amount * self.discount_percent / 100)
        
        return 0
