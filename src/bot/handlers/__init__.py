"""Обработчики бота."""
from aiogram import Router

from src.bot.handlers.start import build_start_router
from src.bot.handlers.order import build_order_router
from src.bot.handlers.delivery import build_delivery_router
from src.bot.handlers.payment import build_payment_router
from src.bot.handlers.my_orders import build_my_orders_router
from src.bot.handlers.manager import build_manager_router
from src.bot.handlers.crop import build_crop_router


def setup_routers() -> Router:
    """Настраивает и возвращает главный роутер."""
    main_router = Router()

    main_router.include_router(build_start_router())
    main_router.include_router(build_order_router())
    main_router.include_router(build_delivery_router())
    main_router.include_router(build_payment_router())
    main_router.include_router(build_my_orders_router())
    main_router.include_router(build_manager_router())
    main_router.include_router(build_crop_router())

    return main_router
