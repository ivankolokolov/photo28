"""Точка входа: polling всех активных студий."""
import asyncio
import logging

from src.database import init_db, async_session
from src.services.settings_service import SettingsService
from src.services.product_service import ProductService
from src.bot.registry import load_active_studios, build_bot, build_dispatcher

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    async with async_session() as session:
        studios = await load_active_studios(session)
        for s in studios:
            await SettingsService(session).load_cache(s.id)
            await ProductService(session).load_cache(s.id)

    if not studios:
        logger.warning("Нет активных студий — бот простаивает.")
        return

    bots, tasks = [], []
    for studio in studios:
        bot = build_bot(studio)
        dp = build_dispatcher(studio)
        bots.append(bot)
        tasks.append(dp.start_polling(bot, handle_signals=False))
        logger.info("Студия %s (%s): polling запущен", studio.slug, studio.id)

    try:
        await asyncio.gather(*tasks)
    finally:
        for bot in bots:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
