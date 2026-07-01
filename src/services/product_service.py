"""Сервис управления товарами/форматами (пер-студийный кеш)."""
import logging
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.product import Product

logger = logging.getLogger(__name__)


class ProductService:
    """Кеш товаров на уровне класса, ключённый по studio_id."""

    # {studio_id: {product_id: Product}}
    _products: Dict[int, Dict[int, Product]] = {}
    # {studio_id: [Product, ...]} — верхний уровень
    _top_level: Dict[int, List[Product]] = {}

    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_cache(self, studio_id: int) -> None:
        query = (
            select(Product)
            .where(Product.studio_id == studio_id)
            .options(selectinload(Product.children), selectinload(Product.parent))
            .order_by(Product.sort_order)
        )
        result = await self.session.execute(query)
        products = result.scalars().unique().all()
        ProductService._products[studio_id] = {p.id: p for p in products}
        ProductService._top_level[studio_id] = [
            p for p in products if p.parent_id is None and p.is_active
        ]
        logger.info(f"Студия {studio_id}: загружено {len(products)} товаров")

    @classmethod
    def get_product(cls, studio_id: int, product_id: int) -> Optional[Product]:
        return cls._products.get(studio_id, {}).get(product_id)

    @classmethod
    def get_top_level_products(cls, studio_id: int) -> List[Product]:
        return [p for p in cls._top_level.get(studio_id, []) if p.is_active]

    @classmethod
    def get_active_children(cls, studio_id: int, parent_id: int) -> List[Product]:
        parent = cls._products.get(studio_id, {}).get(parent_id)
        if not parent:
            return []
        return sorted(
            [c for c in parent.children if c.is_active],
            key=lambda x: x.sort_order,
        )

    @classmethod
    def get_all_purchasable(cls, studio_id: int) -> List[Product]:
        result = []
        for p in cls._top_level.get(studio_id, []):
            if not p.is_active:
                continue
            children = [c for c in p.children if c.is_active]
            if children:
                result.extend(children)
            else:
                result.append(p)
        return result

    @classmethod
    def invalidate_cache(cls, studio_id: Optional[int] = None):
        if studio_id is None:
            cls._products.clear()
            cls._top_level.clear()
        else:
            cls._products.pop(studio_id, None)
            cls._top_level.pop(studio_id, None)

    # === CRUD ===

    async def get_all_products(self, studio_id: int) -> List[Product]:
        query = (
            select(Product)
            .where(Product.studio_id == studio_id)
            .options(selectinload(Product.children), selectinload(Product.parent))
            .order_by(Product.sort_order)
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    async def get_product_by_id(self, product_id: int) -> Optional[Product]:
        query = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.children))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_product(self, studio_id: int, **kwargs) -> Product:
        product = Product(studio_id=studio_id, **kwargs)
        self.session.add(product)
        await self.session.commit()
        await self.session.refresh(product)
        await self.load_cache(studio_id)
        return product

    async def update_product(self, product_id: int, studio_id: int, **kwargs) -> Optional[Product]:
        product = await self.get_product_by_id(product_id)
        if not product or product.studio_id != studio_id:
            return None
        for key, value in kwargs.items():
            if hasattr(product, key):
                setattr(product, key, value)
        await self.session.commit()
        await self.session.refresh(product)
        await self.load_cache(product.studio_id)
        return product

    async def delete_product(self, product_id: int, studio_id: int) -> bool:
        product = await self.get_product_by_id(product_id)
        if not product or product.studio_id != studio_id:
            return False
        await self.session.delete(product)
        await self.session.commit()
        await self.load_cache(studio_id)
        return True

    async def toggle_product(self, product_id: int, studio_id: int) -> Optional[Product]:
        product = await self.get_product_by_id(product_id)
        if not product or product.studio_id != studio_id:
            return None
        product.is_active = not product.is_active
        await self.session.commit()
        await self.session.refresh(product)
        await self.load_cache(product.studio_id)
        return product
