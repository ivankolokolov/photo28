"""Реестр студий: сборка Bot и Dispatcher на студию с композицией роутеров."""
import logging
from typing import Callable, Dict, List, Optional, Tuple

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

logger = logging.getLogger(__name__)

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


class StudioBotRegistry:
    """In-memory реестр активных ботов студий (secret → bot+dispatcher)."""

    def __init__(self):
        # secret -> (studio_id, bot, dispatcher)
        self._by_secret: Dict[str, Tuple[int, Bot, Dispatcher]] = {}
        self._secret_by_studio: Dict[int, str] = {}

    def add(self, studio: Studio) -> None:
        if not studio.bot_token or not studio.webhook_secret:
            logger.warning(
                "Студия %s пропущена в реестре: нет токена/секрета",
                getattr(studio, "id", "?"),
            )
            return
        bot = build_bot(studio)
        dp = build_dispatcher(studio)
        self._by_secret[studio.webhook_secret] = (studio.id, bot, dp)
        self._secret_by_studio[studio.id] = studio.webhook_secret

    def get_by_secret(self, secret: str) -> Optional[Tuple[int, Bot, Dispatcher]]:
        return self._by_secret.get(secret)

    def remove(self, studio_id: int) -> Optional[Bot]:
        secret = self._secret_by_studio.pop(studio_id, None)
        if secret is None:
            return None
        entry = self._by_secret.pop(secret, None)
        return entry[1] if entry else None

    def bots(self) -> List[Bot]:
        return [bot for (_sid, bot, _dp) in self._by_secret.values()]

    def entries(self) -> List[Tuple[int, Bot, Dispatcher]]:
        return list(self._by_secret.values())

    def studio_ids(self) -> set:
        """Возвращает множество studio_id, зарегистрированных в реестре."""
        return set(self._secret_by_studio.keys())


def build_bot(studio: Studio) -> Bot:
    """Создаёт Bot с расшифрованным токеном студии."""
    return Bot(
        token=decrypt_secret(studio.bot_token),
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
