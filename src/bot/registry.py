"""Реестр студий: сборка Bot и Dispatcher на студию с композицией роутеров."""
from typing import Callable, Dict, List

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from src.models.studio import Studio
from src.services.crypto import decrypt_secret
from src.bot.middlewares.studio import StudioMiddleware

from src.bot.handlers.start import build_start_router
from src.bot.handlers.order import build_order_router
from src.bot.handlers.delivery import build_delivery_router
from src.bot.handlers.payment import build_payment_router
from src.bot.handlers.my_orders import build_my_orders_router
from src.bot.handlers.manager import build_manager_router
from src.bot.handlers.crop import build_crop_router

# Базовые фабрики роутеров — каждая создаёт новый Router при вызове.
# build_dispatcher можно вызывать для любого числа студий в одном процессе:
# у каждой студии будет независимый набор роутеров без конфликтов.
BASE_ROUTER_FACTORIES: List[Callable[[], Router]] = [
    build_start_router,
    build_order_router,
    build_delivery_router,
    build_payment_router,
    build_my_orders_router,
    build_manager_router,
    build_crop_router,
]

# Доп-роутеры под конкретные студии (ключ — slug). Кастомный экран для студии =
# добавить сюда фабрику её роутера. По умолчанию пусто.
STUDIO_ROUTER_FACTORIES: Dict[str, List[Callable[[], Router]]] = {}


async def load_active_studios(session) -> list[Studio]:
    """Возвращает активные студии."""
    result = await session.execute(select(Studio).where(Studio.is_active.is_(True)))
    return list(result.scalars().all())


def build_dispatcher(studio: Studio) -> Dispatcher:
    """Собирает Dispatcher для студии: базовые роутеры + её доп-роутеры + middleware.

    Может вызываться многократно для разных студий в одном процессе — каждая
    фабрика в BASE_ROUTER_FACTORIES создаёт новый Router, поэтому конфликтов
    aiogram 'router is already attached' не возникает.
    """
    dp = Dispatcher(storage=MemoryStorage())
    for factory in BASE_ROUTER_FACTORIES:
        dp.include_router(factory())
    for factory in STUDIO_ROUTER_FACTORIES.get(studio.slug, []):
        dp.include_router(factory())
    mw = StudioMiddleware(studio.id)
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)
    return dp


def build_bot(studio: Studio) -> Bot:
    """Создаёт Bot с расшифрованным токеном студии."""
    return Bot(
        token=decrypt_secret(studio.bot_token),
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
