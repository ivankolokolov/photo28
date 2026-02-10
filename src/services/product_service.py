"""Сервис управления товарами/форматами."""
import json
import logging
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.product import Product

logger = logging.getLogger(__name__)


class ProductService:
    """Сервис для работы с товарами/форматами.
    
    Использует кеш на уровне класса — продукты загружаются при старте
    и обновляются при изменениях через админку.
    """
    
    _products: Dict[int, Product] = {}
    _top_level: List[Product] = []
    _cache_loaded: bool = False
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def load_cache(self) -> None:
        """Загружает все продукты в кеш."""
        query = (
            select(Product)
            .options(
                selectinload(Product.children),
                selectinload(Product.parent),
            )
            .order_by(Product.sort_order)
        )
        result = await self.session.execute(query)
        products = result.scalars().unique().all()
        
        ProductService._products = {p.id: p for p in products}
        ProductService._top_level = [
            p for p in products
            if p.parent_id is None and p.is_active
        ]
        ProductService._cache_loaded = True
        logger.info(f"Загружено {len(products)} товаров в кеш")
    
    @classmethod
    def get_product(cls, product_id: int) -> Optional[Product]:
        """Получает продукт из кеша."""
        return cls._products.get(product_id)
    
    @classmethod
    def get_top_level_products(cls) -> List[Product]:
        """Возвращает активные продукты верхнего уровня (для клавиатуры бота)."""
        return [p for p in cls._top_level if p.is_active]
    
    @classmethod
    def get_active_children(cls, parent_id: int) -> List[Product]:
        """Возвращает активные дочерние продукты."""
        parent = cls._products.get(parent_id)
        if not parent:
            return []
        return sorted(
            [c for c in parent.children if c.is_active],
            key=lambda x: x.sort_order
        )
    
    @classmethod
    def get_all_purchasable(cls) -> List[Product]:
        """Возвращает все товары, которые можно купить (не категории)."""
        result = []
        for p in cls._top_level:
            if not p.is_active:
                continue
            children = [c for c in p.children if c.is_active]
            if children:
                result.extend(children)
            else:
                result.append(p)
        return result
    
    @classmethod
    def is_cache_loaded(cls) -> bool:
        return cls._cache_loaded
    
    @classmethod
    def invalidate_cache(cls):
        """Сбрасывает кеш."""
        cls._products.clear()
        cls._top_level.clear()
        cls._cache_loaded = False
    
    # === CRUD операции ===
    
    async def get_all_products(self) -> List[Product]:
        """Получает все продукты из БД."""
        query = (
            select(Product)
            .options(
                selectinload(Product.children),
                selectinload(Product.parent),
            )
            .order_by(Product.sort_order)
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())
    
    async def get_product_by_id(self, product_id: int) -> Optional[Product]:
        """Получает продукт по ID из БД."""
        query = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.children))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def create_product(self, **kwargs) -> Product:
        """Создаёт новый продукт."""
        product = Product(**kwargs)
        self.session.add(product)
        await self.session.commit()
        await self.session.refresh(product)
        await self.load_cache()
        return product
    
    async def update_product(self, product_id: int, **kwargs) -> Optional[Product]:
        """Обновляет продукт."""
        product = await self.get_product_by_id(product_id)
        if not product:
            return None
        
        for key, value in kwargs.items():
            if hasattr(product, key):
                setattr(product, key, value)
        
        await self.session.commit()
        await self.session.refresh(product)
        await self.load_cache()
        return product
    
    async def delete_product(self, product_id: int) -> bool:
        """Удаляет продукт."""
        product = await self.get_product_by_id(product_id)
        if not product:
            return False
        
        await self.session.delete(product)
        await self.session.commit()
        await self.load_cache()
        return True
    
    async def toggle_product(self, product_id: int) -> Optional[Product]:
        """Включает/выключает продукт."""
        product = await self.get_product_by_id(product_id)
        if not product:
            return None
        
        product.is_active = not product.is_active
        await self.session.commit()
        await self.session.refresh(product)
        await self.load_cache()
        return product
