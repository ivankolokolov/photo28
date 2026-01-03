#!/usr/bin/env python3
"""Скрипт инициализации базы данных."""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db, async_session
from src.services.order_service import OrderService
from src.services.settings_service import SettingsService, DEFAULT_SETTINGS, SettingType


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

