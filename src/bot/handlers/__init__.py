"""Обработчики бота."""
from aiogram import Router

from src.bot.handlers.start import router as start_router
from src.bot.handlers.order import router as order_router
from src.bot.handlers.delivery import router as delivery_router
from src.bot.handlers.payment import router as payment_router
from src.bot.handlers.my_orders import router as my_orders_router
from src.bot.handlers.manager import router as manager_router


def setup_routers() -> Router:
    """Настраивает и возвращает главный роутер."""
    main_router = Router()
    
    main_router.include_router(start_router)
    main_router.include_router(order_router)
    main_router.include_router(delivery_router)
    main_router.include_router(payment_router)
    main_router.include_router(my_orders_router)
    main_router.include_router(manager_router)
    
    return main_router

