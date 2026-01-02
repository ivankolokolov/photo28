#!/usr/bin/env python3
"""Скрипт инициализации базы данных."""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db, async_session
from src.services.order_service import OrderService


async def main():
    """Инициализация БД и создание тестовых данных."""
    print("🔧 Инициализация базы данных...")
    await init_db()
    print("✅ Таблицы созданы!")
    
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

