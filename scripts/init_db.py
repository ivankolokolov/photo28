#!/usr/bin/env python3
"""Скрипт инициализации базы данных."""
import asyncio
import json
import sys
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db, async_session
from src.services.order_service import OrderService
from src.services.settings_service import SettingsService, DEFAULT_SETTINGS, SettingType
from src.models.product import Product
from sqlalchemy import select


# === Данные товаров ===

PRODUCTS_SEED = [
    # === Категории верхнего уровня с дочерними ===
    
    # Полароид (категория)
    {
        "slug": "polaroid",
        "name": "Полароид",
        "short_name": "Полароид",
        "emoji": "📷",
        "description": "Формат 7.6×10 см",
        "price_per_unit": 0,
        "price_type": "tiered",
        "sort_order": 10,
        "children": [
            {
                "slug": "polaroid_vertical",
                "name": "Вертикальный",
                "short_name": "Полароид верт.",
                "emoji": "📷",
                "price_per_unit": 24,
                "price_type": "tiered",
                "price_tiers": json.dumps([{"min_qty": 50, "price": 19}]),
                "pricing_group": "polaroid",
                "aspect_ratio": 0.76,
                "sort_order": 11,
            },
            {
                "slug": "polaroid_horizontal",
                "name": "Горизонтальный",
                "short_name": "Полароид гориз.",
                "emoji": "📷",
                "price_per_unit": 24,
                "price_type": "tiered",
                "price_tiers": json.dumps([{"min_qty": 50, "price": 19}]),
                "pricing_group": "polaroid",
                "aspect_ratio": 1.316,
                "sort_order": 12,
            },
        ],
    },
    
    # Инстакс (категория)
    {
        "slug": "instax",
        "name": "Инстакс",
        "short_name": "Инстакс",
        "emoji": "📸",
        "description": "Формат 5.4×8.6 см",
        "price_per_unit": 0,
        "price_type": "tiered",
        "sort_order": 30,
        "children": [
            {
                "slug": "instax_standard",
                "name": "Обычный",
                "short_name": "Инстакс обычный",
                "emoji": "📸",
                "price_per_unit": 24,
                "price_type": "tiered",
                "price_tiers": json.dumps([{"min_qty": 50, "price": 19}]),
                "pricing_group": "polaroid",
                "aspect_ratio": 0.628,
                "sort_order": 31,
            },
            {
                "slug": "instax_frameless",
                "name": "Без нижней рамки",
                "short_name": "Инстакс б/рамки",
                "emoji": "📸",
                "price_per_unit": 24,
                "price_type": "tiered",
                "price_tiers": json.dumps([{"min_qty": 50, "price": 19}]),
                "pricing_group": "polaroid",
                "aspect_ratio": 0.628,
                "sort_order": 32,
            },
        ],
    },
    
    # Классика (категория)
    {
        "slug": "classic",
        "name": "Классика 10×15",
        "short_name": "Классика",
        "emoji": "🖼",
        "description": "Формат 10×15 см",
        "price_per_unit": 0,
        "price_type": "tiered",
        "sort_order": 40,
        "children": [
            {
                "slug": "classic_framed",
                "name": "С рамкой",
                "short_name": "Классика с рамкой",
                "emoji": "🖼",
                "price_per_unit": 27,
                "price_type": "tiered",
                "price_tiers": json.dumps([{"min_qty": 50, "price": 25}]),
                "pricing_group": "classic",
                "aspect_ratio": 0.667,
                "sort_order": 41,
            },
            {
                "slug": "classic_frameless",
                "name": "Без рамки",
                "short_name": "Классика б/рамки",
                "emoji": "🖼",
                "price_per_unit": 27,
                "price_type": "tiered",
                "price_tiers": json.dumps([{"min_qty": 50, "price": 25}]),
                "pricing_group": "classic",
                "aspect_ratio": 0.667,
                "sort_order": 42,
            },
        ],
    },
    
    # === Самостоятельные товары ===
    
    {
        "slug": "half",
        "name": "Половинка",
        "short_name": "Половинка",
        "emoji": "📷",
        "price_per_unit": 24,
        "price_type": "tiered",
        "price_tiers": json.dumps([{"min_qty": 50, "price": 19}]),
        "pricing_group": "polaroid",
        "aspect_ratio": 0.76,
        "sort_order": 20,
    },
    
    {
        "slug": "large",
        "name": "Большие 15×20",
        "short_name": "Большие 15×20",
        "emoji": "🖼",
        "price_per_unit": 50,
        "price_type": "per_unit",
        "aspect_ratio": 0.75,
        "sort_order": 50,
    },
    
    {
        "slug": "magnet_polaroid",
        "name": "Магнит полароид",
        "short_name": "Магнит",
        "emoji": "🧲",
        "price_per_unit": 150,
        "price_type": "per_unit",
        "aspect_ratio": 0.76,
        "sort_order": 60,
    },
    
    {
        "slug": "album_20x20",
        "name": "Альбом 20×20",
        "short_name": "Альбом 20×20",
        "emoji": "📕",
        "price_per_unit": 600,
        "price_type": "per_unit",
        "sort_order": 70,
    },
    
    {
        "slug": "album_instax",
        "name": "Альбом для инстакс",
        "short_name": "Альбом инстакс",
        "emoji": "📗",
        "price_per_unit": 300,
        "price_type": "per_unit",
        "sort_order": 80,
    },
]


async def seed_products(session):
    """Создаёт товары из PRODUCTS_SEED."""
    print("\n📦 Создание товаров...")
    
    for product_data in PRODUCTS_SEED:
        children_data = product_data.pop("children", [])
        
        # Проверяем, существует ли товар
        existing = await session.execute(
            select(Product).where(Product.slug == product_data["slug"])
        )
        parent = existing.scalar_one_or_none()
        
        if parent:
            print(f"  ⏭️ {product_data['name']} (уже существует)")
        else:
            parent = Product(**product_data)
            session.add(parent)
            await session.flush()
            print(f"  ✅ {product_data['name']}")
        
        # Дочерние товары
        for child_data in children_data:
            existing_child = await session.execute(
                select(Product).where(Product.slug == child_data["slug"])
            )
            if existing_child.scalar_one_or_none():
                print(f"    ⏭️ └ {child_data['name']} (уже существует)")
            else:
                child = Product(parent_id=parent.id, **child_data)
                session.add(child)
                print(f"    ✅ └ {child_data['name']}")
    
    await session.commit()
    print("  📦 Товары созданы!")


async def main():
    """Инициализация БД и создание тестовых данных."""
    print("🔧 Инициализация базы данных...")
    await init_db()
    print("✅ Таблицы созданы!")
    
    # Создаём настройки по умолчанию
    print("\n⚙️ Создание настроек по умолчанию...")
    async with async_session() as session:
        settings_service = SettingsService(session)
        
        for setting_data in DEFAULT_SETTINGS:
            existing = await settings_service.get_by_key(setting_data["key"])
            if not existing:
                await settings_service.create_setting(
                    key=setting_data["key"],
                    value=setting_data["value"],
                    value_type=setting_data["value_type"],
                    display_name=setting_data["display_name"],
                    description=setting_data.get("description", ""),
                    group=setting_data.get("group", "general"),
                    sort_order=setting_data.get("sort_order", 0),
                )
                print(f"  ✅ {setting_data['display_name']}")
            else:
                print(f"  ⏭️ {setting_data['display_name']} (уже существует)")
    
    # Создаём товары
    async with async_session() as session:
        await seed_products(session)
    
    # Создаём тестовый промокод
    print("\n🎟 Создание тестового промокода...")
    async with async_session() as session:
        service = OrderService(session)
        
        try:
            promo = await service.create_promocode(
                code="WELCOME10",
                discount_percent=10,
                description="Скидка 10% для новых клиентов",
            )
            print(f"✅ Промокод создан: {promo.code}")
        except Exception as e:
            print(f"⚠️ Промокод уже существует или ошибка: {e}")
    
    print("\n🎉 Инициализация завершена!")


if __name__ == "__main__":
    asyncio.run(main())
