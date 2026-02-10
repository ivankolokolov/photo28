"""Модель фотографии."""
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.order import Order
    from src.models.product import Product


class Photo(Base):
    """Фотография в заказе."""
    
    __tablename__ = "photos"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    
    # Формат/товар
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    
    # Telegram file_id для быстрого доступа
    telegram_file_id: Mapped[str] = mapped_column(String(255))
    
    # Локальный путь к файлу
    local_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Путь на Яндекс.Диске после завершения заказа
    yandex_disk_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Порядковый номер фото в заказе
    position: Mapped[int] = mapped_column(Integer, default=0)
    
    # Тип файла: True если отправлен как документ (без сжатия)
    is_document: Mapped[bool] = mapped_column(default=False)
    
    # File ID миниатюры для быстрого превью
    thumbnail_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Автоматически определённый кроп (JSON от SmartCropService)
    auto_crop_data: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    # Уверенность авто-кропа (0-1)
    crop_confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    
    # Метод авто-кропа: "face", "saliency", "center"
    crop_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Количество найденных лиц
    faces_found: Mapped[int] = mapped_column(Integer, default=0)
    
    # Финальные данные кадрирования
    crop_data: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    # Флаг: кроп подтверждён пользователем
    crop_confirmed: Mapped[bool] = mapped_column(default=False)
    
    # Relationships
    order: Mapped["Order"] = relationship(back_populates="photos")
    product: Mapped["Product"] = relationship(back_populates="photos")
    
    def __repr__(self) -> str:
        return f"<Photo {self.id}: product={self.product_id}>"
