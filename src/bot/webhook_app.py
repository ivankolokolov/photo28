"""aiohttp-приложение для приёма webhook-апдейтов всех студий."""
import logging
from aiohttp import web
from aiogram.types import Update

from src.bot.registry import StudioBotRegistry

logger = logging.getLogger(__name__)

# Типизированный ключ для app-хранилища (избегает NotAppKeyWarning)
REGISTRY_KEY: web.AppKey["StudioBotRegistry"] = web.AppKey("registry", StudioBotRegistry)


async def _handle_webhook(request: web.Request) -> web.Response:
    registry: StudioBotRegistry = request.app[REGISTRY_KEY]
    secret = request.match_info["secret"]
    entry = registry.get_by_secret(secret)
    if entry is None:
        return web.Response(status=404, text="unknown webhook")
    studio_id, bot, dp = entry
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")
    update = Update.model_validate(data)
    await dp.feed_webhook_update(bot, update)
    return web.Response(status=200)


async def _handle_health(request: web.Request) -> web.Response:
    registry: StudioBotRegistry = request.app[REGISTRY_KEY]
    return web.json_response({"status": "ok", "studios": len(registry.entries())})


def build_webhook_app(registry: StudioBotRegistry) -> web.Application:
    app = web.Application()
    app[REGISTRY_KEY] = registry
    app.router.add_post("/webhook/{secret}", _handle_webhook)
    app.router.add_get("/healthz", _handle_health)
    return app
