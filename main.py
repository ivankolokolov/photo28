"""Точка входа для Telegram бота."""
import asyncio
import logging
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import settings
from src.database import init_db, async_session
from src.bot.handlers import setup_routers
from src.services.settings_service import SettingsService, SettingKeys


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Флаг для остановки бота
_shutdown_requested = False


async def check_restart_signal():
    """Проверяет сигнал перезапуска из админки."""
    global _shutdown_requested
    
    while not _shutdown_requested:
        await asyncio.sleep(10)  # Проверяем каждые 10 секунд
        
        try:
            async with async_session() as session:
                service = SettingsService(session)
                await service.load_cache()
                
                # Обновляем кеш товаров
                from src.services.product_service import ProductService
                product_service = ProductService(session)
                await product_service.load_cache()
            
            # Проверяем немедленный перезапуск
            if SettingsService.get_bool(SettingKeys.RESTART_REQUESTED, False):
                logger.info("🔄 Получен запрос на перезапуск из админки")
                
                # Сбрасываем флаг
                async with async_session() as session:
                    service = SettingsService(session)
                    await service.set_value(SettingKeys.RESTART_REQUESTED, "false")
                
                _shutdown_requested = True
                break
            
            # Проверяем запланированный перезапуск
            scheduled_str = SettingsService.get(SettingKeys.RESTART_SCHEDULED_TIME, "")
            if scheduled_str:
                try:
                    scheduled_time = datetime.fromisoformat(scheduled_str)
                    if datetime.now() >= scheduled_time:
                        logger.info(f"🌙 Запланированный перезапуск: {scheduled_time}")
                        
                        # Сбрасываем время
                        async with async_session() as session:
                            service = SettingsService(session)
                            await service.set_value(SettingKeys.RESTART_SCHEDULED_TIME, "")
                        
                        _shutdown_requested = True
                        break
                except ValueError:
                    pass
                    
        except Exception as e:
            logger.error(f"Ошибка проверки сигнала перезапуска: {e}")


async def cleanup_old_drafts():
    """Фоновая задача для очистки старых черновиков (раз в день)."""
    from src.services.order_service import OrderService
    
    while True:
        # Ждём до следующей проверки (каждые 6 часов)
        await asyncio.sleep(6 * 60 * 60)
        
        try:
            async with async_session() as session:
                service = OrderService(session)
                deleted_count = await service.delete_old_drafts(days=7)
                
                if deleted_count > 0:
                    logger.info(f"🧹 Очищено {deleted_count} старых черновиков (старше 7 дней)")
        except Exception as e:
            logger.error(f"Ошибка очистки черновиков: {e}")


async def main():
    """Основная функция запуска бота."""
    global _shutdown_requested
    
    # Инициализация базы данных
    logger.info("Инициализация базы данных...")
    await init_db()
    
    # Загрузка настроек в кеш
    logger.info("Загрузка настроек...")
    async with async_session() as session:
        settings_service = SettingsService(session)
        await settings_service.load_cache()
        
        # Сбрасываем флаг перезапуска при старте
        await settings_service.set_value(SettingKeys.RESTART_REQUESTED, "false")
    logger.info("Настройки загружены")
    
    # Загрузка товаров в кеш
    logger.info("Загрузка товаров...")
    from src.services.product_service import ProductService
    async with async_session() as session:
        product_service = ProductService(session)
        await product_service.load_cache()
    logger.info("Товары загружены")
    
    # Создаём директории для хранения файлов
    settings.ensure_dirs()
    
    # Инициализация бота
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    
    # Инициализация диспетчера с хранилищем состояний
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Подключаем роутеры
    dp.include_router(setup_routers())
    
    # Запускаем фоновые задачи
    restart_checker = asyncio.create_task(check_restart_signal())
    drafts_cleaner = asyncio.create_task(cleanup_old_drafts())
    
    # Запускаем polling (без webhook — работает без публичного IP)
    logger.info("Бот запущен в режиме polling...")
    
    try:
        # Polling с возможностью прерывания
        while not _shutdown_requested:
            try:
                await asyncio.wait_for(
                    dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()),
                    timeout=None
                )
            except asyncio.CancelledError:
                break
    finally:
        restart_checker.cancel()
        drafts_cleaner.cancel()
        await bot.session.close()
        
        if _shutdown_requested:
            logger.info("🔄 Бот завершает работу для перезапуска...")
            sys.exit(0)  # Код 0 — systemd перезапустит


if __name__ == "__main__":
    asyncio.run(main())

