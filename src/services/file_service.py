"""Сервис работы с файлами."""
import os
import asyncio
from pathlib import Path
from typing import Optional
import aiohttp

from src.config import settings
from src.models.order import Order
from src.models.photo import Photo


class FileService:
    """Сервис для работы с файлами фотографий."""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.photos_dir = settings.photos_dir
        self.temp_dir = settings.temp_dir
        
        # Создаём директории
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def get_order_dir(self, order: Order) -> Path:
        """Возвращает директорию для хранения фото заказа."""
        order_dir = self.photos_dir / order.order_number
        order_dir.mkdir(parents=True, exist_ok=True)
        return order_dir
    
    async def download_photo_from_telegram(
        self,
        file_id: str,
        order: Order,
        photo: Photo,
    ) -> str:
        """
        Скачивает фото из Telegram и сохраняет локально.
        
        Returns:
            Путь к сохранённому файлу
        """
        # Получаем информацию о файле
        file_info_url = f"https://api.telegram.org/bot{self.bot_token}/getFile"
        
        async with aiohttp.ClientSession() as session:
            # Получаем file_path от Telegram API
            async with session.get(file_info_url, params={"file_id": file_id}) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    raise Exception(f"Не удалось получить информацию о файле: {data}")
                
                file_path = data["result"]["file_path"]
            
            # Скачиваем файл
            download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    raise Exception(f"Не удалось скачать файл: {resp.status}")
                
                content = await resp.read()
        
        # Определяем расширение файла
        ext = Path(file_path).suffix or ".jpg"
        
        # Формируем имя файла: order_number_format_position.ext
        # Получаем slug продукта для имени файла
        from src.services.product_service import ProductService
        product = ProductService.get_product(photo.product_id)
        product_slug = product.slug if product else f"product{photo.product_id}"
        filename = f"{order.order_number}_{product_slug}_{photo.position:03d}{ext}"
        
        # Сохраняем файл
        order_dir = self.get_order_dir(order)
        local_path = order_dir / filename
        
        with open(local_path, "wb") as f:
            f.write(content)
        
        return str(local_path)
    
    async def download_all_order_photos(self, order: Order) -> list[str]:
        """
        Скачивает все фото заказа.
        
        Returns:
            Список путей к скачанным файлам
        """
        tasks = []
        for photo in order.photos:
            if not photo.local_path:
                tasks.append(
                    self.download_photo_from_telegram(
                        photo.telegram_file_id,
                        order,
                        photo,
                    )
                )
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return [r for r in results if isinstance(r, str)]
        
        return []
    
    def get_order_photos_paths(self, order: Order) -> list[Path]:
        """Возвращает пути ко всем фото заказа на диске."""
        order_dir = self.get_order_dir(order)
        if not order_dir.exists():
            return []
        
        return sorted(order_dir.glob("*.*"))
    
    def delete_order_photos(self, order: Order) -> None:
        """Удаляет все локальные фото заказа."""
        order_dir = self.photos_dir / order.order_number
        if order_dir.exists():
            import shutil
            shutil.rmtree(order_dir)
    
    def get_storage_stats(self) -> dict:
        """Возвращает статистику использования хранилища."""
        total_size = 0
        file_count = 0
        
        for path in self.photos_dir.rglob("*"):
            if path.is_file():
                total_size += path.stat().st_size
                file_count += 1
        
        return {
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_count": file_count,
            "orders_count": len(list(self.photos_dir.iterdir())),
        }

