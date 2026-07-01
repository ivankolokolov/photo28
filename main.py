"""Точка входа: webhook-сервер всех активных студий."""
import asyncio
import logging
import os
from aiohttp import web

from src.database import init_db, async_session
from src.bot.registry import StudioBotRegistry, load_active_studios
from src.bot.webhook_app import build_webhook_app, REGISTRY_KEY
from src.bot.lifecycle import startup, shutdown
from src.bot.background import cleanup_old_drafts_once
from src.bot.reconcile import reconcile_studios

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60
RECONCILE_INTERVAL_SECONDS = 30

# Типизированные ключи для хранения фоновых задач (избегают NotAppKeyWarning)
CLEANUP_TASK_KEY: web.AppKey["asyncio.Task"] = web.AppKey("cleanup_task", asyncio.Task)
RECONCILE_TASK_KEY: web.AppKey["asyncio.Task"] = web.AppKey("reconcile_task", asyncio.Task)


async def _cleanup_loop():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            async with async_session() as session:
                studios = await load_active_studios(session)
                await cleanup_old_drafts_once(session, [s.id for s in studios], days=7)
        except Exception as e:
            logger.error("Ошибка очистки черновиков: %s", e)


async def _reconcile_loop(registry: StudioBotRegistry):
    while True:
        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)
        try:
            async with async_session() as session:
                added, removed = await reconcile_studios(registry, session)
                if added or removed:
                    logger.info("Reconcile: +%d -%d студий", added, removed)
        except Exception as e:
            logger.error("Ошибка reconcile-цикла: %s", e)


async def _on_startup(app: web.Application):
    await init_db()
    async with async_session() as session:
        await startup(app[REGISTRY_KEY], session)
    app[CLEANUP_TASK_KEY] = asyncio.create_task(_cleanup_loop())
    app[RECONCILE_TASK_KEY] = asyncio.create_task(_reconcile_loop(app[REGISTRY_KEY]))


async def _on_shutdown(app: web.Application):
    app[CLEANUP_TASK_KEY].cancel()
    app[RECONCILE_TASK_KEY].cancel()
    await shutdown(app[REGISTRY_KEY])


def main():
    registry = StudioBotRegistry()
    app = build_webhook_app(registry)
    app.on_startup.append(_on_startup)
    app.on_shutdown.append(_on_shutdown)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("WEBHOOK_PORT", "8081")))


if __name__ == "__main__":
    main()
