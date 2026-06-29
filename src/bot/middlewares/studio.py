"""Middleware, инжектирующий StudioContext в хендлеры."""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import select

from src.database import async_session
from src.models.studio import Studio
from src.bot.context import build_studio_context

logger = logging.getLogger(__name__)


class StudioMiddleware(BaseMiddleware):
    """Привязан к одной студии (свой Dispatcher на студию)."""

    def __init__(self, studio_id: int):
        self.studio_id = studio_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with async_session() as session:
            studio = (
                await session.execute(
                    select(Studio).where(Studio.id == self.studio_id)
                )
            ).scalar_one_or_none()

            if studio is None or not studio.is_active:
                logger.warning("Студия %s неактивна/не найдена — апдейт пропущен", self.studio_id)
                return None

            data["ctx"] = build_studio_context(session, studio)
            return await handler(event, data)
