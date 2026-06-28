"""Реестр студий: сборка Bot и Dispatcher на студию с композицией роутеров."""
from typing import Callable, Dict, List

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.models.studio import Studio
from src.services.crypto import decrypt_secret
from src.bot.middlewares.studio import StudioMiddleware

from src.bot.handlers.start import router as start_router
from src.bot.handlers.order import router as order_router
from src.bot.handlers.delivery import router as delivery_router
from src.bot.handlers.payment import router as payment_router
from src.bot.handlers.my_orders import router as my_orders_router
from src.bot.handlers.manager import router as manager_router
from src.bot.handlers.crop import router as crop_router

# Базовые роутеры — одинаковы для всех студий.
BASE_ROUTER_FACTORIES: List[Callable[[], Router]] = [
    lambda: start_router,
    lambda: order_router,
    lambda: delivery_router,
    lambda: payment_router,
    lambda: my_orders_router,
    lambda: manager_router,
    lambda: crop_router,
]

# Доп-роутеры под конкретные студии (ключ — slug). Кастомный экран для студии =
# добавить сюда фабрику её роутера. По умолчанию пусто.
STUDIO_ROUTER_FACTORIES: Dict[str, List[Callable[[], Router]]] = {}


def build_dispatcher(studio: Studio) -> Dispatcher:
    """Собирает Dispatcher для студии: базовые роутеры + её доп-роутеры + middleware.

    Базовые роутеры — module-level singletons: включаются в dp только если ещё
    не прикреплены к другому роутеру (aiogram запрещает двойное parent).
    Поддержка нескольких параллельных студий (фабрики, создающие новые роутеры)
    вводится в Task 9.
    """
    dp = Dispatcher(storage=MemoryStorage())
    for factory in BASE_ROUTER_FACTORIES:
        r = factory()
        if r._parent_router is None:
            dp.include_router(r)
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
