"""Модель товара/формата."""
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, Float, ForeignKey, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.photo import Photo


class Product(Base):
    """Товар/формат фотографии.
    
    Двухуровневая структура:
    - parent_id = NULL, has children → категория (Полароид, Инстакс...)
    - parent_id = NULL, no children → самостоятельный товар (Большие, Альбом...)
    - parent_id = X → вариант (Вертикальный, Горизонтальный...)
    """
    
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("studio_id", "slug", name="uq_product_studio_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Для двухуровневой навигации
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True
    )

    # Идентификатор (slug) — уникален в рамках студии
    slug: Mapped[str] = mapped_column(String(100), index=True)
    
    # Отображение
    name: Mapped[str] = mapped_column(String(255))  # Полное название
    short_name: Mapped[str] = mapped_column(String(100))  # Короткое
    emoji: Mapped[str] = mapped_column(String(10), default="📷")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Ценообразование
    price_per_unit: Mapped[int] = mapped_column(Integer, default=0)  # Базовая цена за штуку
    price_type: Mapped[str] = mapped_column(
        String(20), default="per_unit"
    )  # "per_unit", "tiered", "fixed"
    
    # Для tiered: JSON [{"min_qty": 50, "price": 19}]
    price_tiers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Группа ценообразования (товары в одной группе суммируются для тиров)
    # Например: "polaroid" — полароид+половинка+инстакс считаются вместе
    pricing_group: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Для кропа
    aspect_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Управление
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    parent: Mapped[Optional["Product"]] = relationship(
        "Product",
        remote_side=[id],
        back_populates="children"
    )
    children: Mapped[List["Product"]] = relationship(
        "Product",
        back_populates="parent",
        cascade="all, delete-orphan"
    )
    photos: Mapped[List["Photo"]] = relationship(back_populates="product")
    
    def __repr__(self) -> str:
        return f"<Product {self.slug}: {self.name}>"
    
    @property
    def is_category(self) -> bool:
        """Является ли категорией (имеет дочерние товары)."""
        return self.parent_id is None and len(self.children) > 0
    
    @property
    def is_standalone(self) -> bool:
        """Самостоятельный товар без вариантов."""
        return self.parent_id is None and len(self.children) == 0
    
    @property
    def is_variant(self) -> bool:
        """Является ли вариантом другого товара."""
        return self.parent_id is not None
    
    @property
    def display_price(self) -> str:
        """Цена для отображения."""
        if self.price_type == "fixed":
            return f"{self.price_per_unit}₽"
        elif self.price_type == "tiered":
            return f"от {self.price_per_unit}₽/шт"
        else:
            return f"{self.price_per_unit}₽/шт"
    
    def get_price_tiers(self) -> list:
        """Возвращает тиры как список словарей."""
        if not self.price_tiers:
            return []
        import json
        try:
            return json.loads(self.price_tiers)
        except (json.JSONDecodeError, TypeError):
            return []
