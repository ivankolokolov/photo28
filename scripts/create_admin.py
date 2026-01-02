#!/usr/bin/env python3
"""Скрипт для создания промокодов через командную строку."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db, async_session
from src.services.order_service import OrderService


async def create_promocode():
    """Интерактивное создание промокода."""
    await init_db()
    
    print("=== Создание промокода ===\n")
    
    code = input("Код промокода: ").strip().upper()
    if not code:
        print("Ошибка: код не может быть пустым")
        return
    
    discount_type = input("Тип скидки (1 - процент, 2 - фикс. сумма): ").strip()
    
    discount_percent = None
    discount_amount = None
    
    if discount_type == "1":
        discount_percent = int(input("Процент скидки: "))
    else:
        discount_amount = int(input("Сумма скидки (₽): "))
    
    max_uses_str = input("Макс. использований (Enter - без ограничений): ").strip()
    max_uses = int(max_uses_str) if max_uses_str else None
    
    description = input("Описание (опционально): ").strip() or None
    
    async with async_session() as session:
        service = OrderService(session)
        promo = await service.create_promocode(
            code=code,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            max_uses=max_uses,
            description=description,
        )
        
        print(f"\n✅ Промокод {promo.code} создан!")
        if promo.discount_percent:
            print(f"   Скидка: {promo.discount_percent}%")
        else:
            print(f"   Скидка: {promo.discount_amount}₽")


if __name__ == "__main__":
    asyncio.run(create_promocode())

