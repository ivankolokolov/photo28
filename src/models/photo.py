"""Модель фотографии."""
from enum import Enum
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.order import Order


class PhotoFormat(str, Enum):
    """Форматы фотографий."""
    POLAROID_STANDARD = "polaroid_standard"  # Полароид 7.6х10 стандарт
    POLAROID_WIDE = "polaroid_wide"          # Полароид 7.6х10 широкий
    INSTAX = "instax"                         # Инстакс 5.4х8.6
    CLASSIC = "classic"                       # Классика 10х15 без рамки
    
    @property
    def display_name(self) -> str:
        """Название формата для отображения."""
        names = {
            PhotoFormat.POLAROID_STANDARD: "Полароид 7.6х10 стандарт",
            PhotoFormat.POLAROID_WIDE: "Полароид 7.6х10 широкий",
            PhotoFormat.INSTAX: "Инстакс 5.4х8.6",
            PhotoFormat.CLASSIC: "Классика 10х15 без рамки",
        }
        return names[self]
    
    @property
    def short_name(self) -> str:
        """Короткое название формата."""
        names = {
            PhotoFormat.POLAROID_STANDARD: "Полароид стандарт",
            PhotoFormat.POLAROID_WIDE: "Полароид широкий",
            PhotoFormat.INSTAX: "Инстакс",
            PhotoFormat.CLASSIC: "Классика",
        }
        return names[self]


class Photo(Base):
    """Фотография в заказе."""
    
    __tablename__ = "photos"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    
    # Формат фото
    format: Mapped[PhotoFormat] = mapped_column(SQLEnum(PhotoFormat))
    
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
    
    # Данные кадрирования (JSON: {x, y, width, height, rotate, scaleX, scaleY})
    crop_data: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    # Флаг: кроп подтверждён пользователем
    crop_confirmed: Mapped[bool] = mapped_column(default=False)
    
    # Relationships
    order: Mapped["Order"] = relationship(back_populates="photos")
    
    def __repr__(self) -> str:
        return f"<Photo {self.id}: {self.format.value}>"

