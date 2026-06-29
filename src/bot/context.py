"""Студия-скоупленный контекст для хендлеров бота."""
from dataclasses import dataclass
from typing import Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.studio import Studio
from src.models.product import Product
from src.services.order_service import OrderService
from src.services.settings_service import SettingsService
from src.services.product_service import ProductService


class SettingsFacade:
    """Студия-скоупленная обёртка над SettingsService (кеш в памяти)."""
    def __init__(self, studio_id: int):
        self.studio_id = studio_id

    def get(self, key: str, default: Any = None) -> Any:
        return SettingsService.get(self.studio_id, key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        return SettingsService.get_int(self.studio_id, key, default)

    def get_float(self, key: str, default: float = 0.0) -> float:
        return SettingsService.get_float(self.studio_id, key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        return SettingsService.get_bool(self.studio_id, key, default)


class ProductsFacade:
    """Студия-скоупленная обёртка над ProductService (кеш в памяти)."""
    def __init__(self, studio_id: int):
        self.studio_id = studio_id

    def get(self, product_id: int) -> Optional[Product]:
        return ProductService.get_product(self.studio_id, product_id)

    def top_level(self) -> List[Product]:
        return ProductService.get_top_level_products(self.studio_id)

    def children(self, parent_id: int) -> List[Product]:
        return ProductService.get_active_children(self.studio_id, parent_id)

    def all_purchasable(self) -> List[Product]:
        return ProductService.get_all_purchasable(self.studio_id)


@dataclass
class StudioContext:
    """Всё, что нужно хендлеру для работы в рамках одной студии."""
    studio_id: int
    studio: Studio
    session: AsyncSession
    orders: OrderService
    settings: SettingsFacade
    products: ProductsFacade


def build_studio_context(session: AsyncSession, studio: Studio) -> StudioContext:
    """Собирает StudioContext для заданной студии и сессии."""
    return StudioContext(
        studio_id=studio.id,
        studio=studio,
        session=session,
        orders=OrderService(session, studio.id),
        settings=SettingsFacade(studio.id),
        products=ProductsFacade(studio.id),
    )
