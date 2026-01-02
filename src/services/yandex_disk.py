"""Сервис интеграции с Яндекс.Диском."""
import asyncio
from pathlib import Path
from typing import Optional
import yadisk_async

from src.config import settings
from src.models.order import Order


class YandexDiskService:
    """Сервис для работы с Яндекс.Диском."""
    
    BASE_FOLDER = "/Photo28_Orders"
    
    def __init__(self):
        self.token = settings.yandex_disk_token
        self._client: Optional[yadisk_async.YaDisk] = None
    
    @property
    def client(self) -> yadisk_async.YaDisk:
        """Ленивая инициализация клиента."""
        if self._client is None:
            self._client = yadisk_async.YaDisk(token=self.token)
        return self._client
    
    async def check_connection(self) -> bool:
        """Проверяет подключение к Яндекс.Диску."""
        try:
            return await self.client.check_token()
        except Exception:
            return False
    
    async def ensure_folder(self, path: str) -> None:
        """Создаёт папку, если она не существует."""
        try:
            if not await self.client.exists(path):
                await self.client.mkdir(path)
        except Exception as e:
            # Папка может уже существовать
            pass
    
    def get_order_folder(self, order: Order) -> str:
        """Возвращает путь к папке заказа на Яндекс.Диске."""
        # Структура: /Photo28_Orders/YYYY-MM/order_number/
        date_folder = order.created_at.strftime("%Y-%m")
        return f"{self.BASE_FOLDER}/{date_folder}/{order.order_number}"
    
    async def upload_order_photos(
        self,
        order: Order,
        local_photos_dir: Path,
    ) -> list[str]:
        """
        Загружает фото заказа на Яндекс.Диск.
        
        Args:
            order: Заказ
            local_photos_dir: Локальная директория с фото
        
        Returns:
            Список путей к загруженным файлам на Я.Диске
        """
        if not self.token:
            raise ValueError("Яндекс.Диск токен не настроен")
        
        # Создаём структуру папок
        await self.ensure_folder(self.BASE_FOLDER)
        date_folder = order.created_at.strftime("%Y-%m")
        await self.ensure_folder(f"{self.BASE_FOLDER}/{date_folder}")
        
        order_folder = self.get_order_folder(order)
        await self.ensure_folder(order_folder)
        
        # Загружаем файлы
        uploaded_paths = []
        
        for file_path in local_photos_dir.glob("*.*"):
            if file_path.is_file():
                remote_path = f"{order_folder}/{file_path.name}"
                
                try:
                    await self.client.upload(str(file_path), remote_path, overwrite=True)
                    uploaded_paths.append(remote_path)
                except Exception as e:
                    print(f"Ошибка загрузки {file_path}: {e}")
        
        return uploaded_paths
    
    async def get_order_public_link(self, order: Order) -> Optional[str]:
        """
        Получает публичную ссылку на папку заказа.
        
        Returns:
            Публичная ссылка или None
        """
        order_folder = self.get_order_folder(order)
        
        try:
            # Публикуем папку
            await self.client.publish(order_folder)
            
            # Получаем публичную ссылку
            meta = await self.client.get_meta(order_folder)
            return meta.public_url
        except Exception as e:
            print(f"Ошибка получения публичной ссылки: {e}")
            return None
    
    async def list_orders(self) -> list[dict]:
        """Возвращает список заказов на Яндекс.Диске."""
        orders = []
        
        try:
            async for item in await self.client.listdir(self.BASE_FOLDER):
                if item.type == "dir":
                    # Это папка с месяцем
                    month_path = f"{self.BASE_FOLDER}/{item.name}"
                    async for order_item in await self.client.listdir(month_path):
                        if order_item.type == "dir":
                            orders.append({
                                "order_number": order_item.name,
                                "path": f"{month_path}/{order_item.name}",
                                "created": order_item.created,
                            })
        except Exception as e:
            print(f"Ошибка получения списка заказов: {e}")
        
        return orders
    
    async def close(self) -> None:
        """Закрывает соединение."""
        if self._client:
            await self._client.close()
            self._client = None

