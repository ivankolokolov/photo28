"""Жизненный цикл webhook'ов студий."""
import logging

from src.config import settings
from src.services.settings_service import SettingsService
from src.services.product_service import ProductService
from src.bot.registry import StudioBotRegistry, load_active_studios

logger = logging.getLogger(__name__)


def webhook_url_for(secret: str) -> str:
    return f"{settings.base_webhook_url}/webhook/{secret}"


async def register_studio(registry: StudioBotRegistry, studio) -> None:
    registry.add(studio)
    entry = registry.get_by_secret(studio.webhook_secret) if studio.webhook_secret else None
    if entry is None:
        return
    if not settings.base_webhook_url:
        logger.warning(
            "Студия %s (%s): BASE_WEBHOOK_URL не задан, set_webhook пропущен",
            studio.slug, studio.id,
        )
        return
    _sid, bot, _dp = entry
    await bot.set_webhook(webhook_url_for(studio.webhook_secret))
    logger.info("Студия %s (%s): webhook установлен", studio.slug, studio.id)


async def unregister_studio(registry: StudioBotRegistry, studio_id: int) -> None:
    bot = registry.remove(studio_id)
    if bot is None:
        return
    try:
        await bot.delete_webhook()
    finally:
        await bot.session.close()
    logger.info("Студия %s: webhook снят", studio_id)


async def startup(registry: StudioBotRegistry, session) -> None:
    studios = await load_active_studios(session)
    for s in studios:
        await SettingsService(session).load_cache(s.id)
        await ProductService(session).load_cache(s.id)
        await register_studio(registry, s)


async def shutdown(registry: StudioBotRegistry) -> None:
    for _sid, bot, _dp in registry.entries():
        try:
            await bot.delete_webhook()
        finally:
            await bot.session.close()
