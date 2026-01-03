"""Точка входа для Telegram бота."""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import settings
from src.database import init_db, async_session
from src.bot.handlers import setup_routers
from src.services.settings_service import SettingsService


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Основная функция запуска бота."""
    # Инициализация базы данных
    logger.info("Инициализация базы данных...")
    await init_db()
    
    # Загрузка настроек в кеш
    logger.info("Загрузка настроек...")
    async with async_session() as session:
        settings_service = SettingsService(session)
        await settings_service.load_cache()
    logger.info("Настройки загружены")
    
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
    
    # Запускаем polling (без webhook — работает без публичного IP)
    logger.info("Бот запущен в режиме polling...")
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

