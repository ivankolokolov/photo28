#!/usr/bin/env python3
"""Скрипт для массовой загрузки фотографий на Яндекс.Диск."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.database import init_db, async_session
from src.services.order_service import OrderService
from src.services.file_service import FileService
from src.services.yandex_disk import YandexDiskService
from src.models.order import OrderStatus


async def backup_completed_orders():
    """Загружает фото завершённых заказов на Яндекс.Диск."""
    await init_db()
    
    if not settings.yandex_disk_token:
        print("❌ Яндекс.Диск токен не настроен!")
        return
    
    yandex = YandexDiskService()
    file_service = FileService(settings.bot_token)
    
    # Проверяем подключение
    if not await yandex.check_connection():
        print("❌ Не удалось подключиться к Яндекс.Диску!")
        return
    
    print("✅ Подключено к Яндекс.Диску\n")
    
    async with async_session() as session:
        service = OrderService(session)
        
        # Получаем завершённые заказы
        shipped_orders = await service.get_orders_by_status(OrderStatus.SHIPPED)
        delivered_orders = await service.get_orders_by_status(OrderStatus.DELIVERED)
        
        orders = shipped_orders + delivered_orders
        
        print(f"📦 Найдено {len(orders)} завершённых заказов\n")
        
        for order in orders:
            order_dir = file_service.photos_dir / order.order_number
            
            if not order_dir.exists():
                print(f"⚠️ {order.order_number}: фото не скачаны")
                continue
            
            photos = list(order_dir.glob("*.*"))
            if not photos:
                print(f"⚠️ {order.order_number}: папка пуста")
                continue
            
            print(f"📤 {order.order_number}: загрузка {len(photos)} файлов...")
            
            try:
                await yandex.upload_order_photos(order, order_dir)
                print(f"✅ {order.order_number}: загружено!")
            except Exception as e:
                print(f"❌ {order.order_number}: ошибка - {e}")
    
    await yandex.close()
    print("\n🎉 Готово!")


if __name__ == "__main__":
    asyncio.run(backup_completed_orders())

