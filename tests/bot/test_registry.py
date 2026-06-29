"""Тесты сборки Dispatcher на студию."""
import os
import pytest
from cryptography.fernet import Fernet
from aiogram import Dispatcher

from src.services.studio_provisioning import provision_studio
from src.bot.registry import build_dispatcher, STUDIO_ROUTER_FACTORIES, BASE_ROUTER_FACTORIES

from src.bot.handlers.start import router as _start_router
from src.bot.handlers.order import router as _order_router
from src.bot.handlers.delivery import router as _delivery_router
from src.bot.handlers.payment import router as _payment_router
from src.bot.handlers.my_orders import router as _my_orders_router
from src.bot.handlers.manager import router as _manager_router
from src.bot.handlers.crop import router as _crop_router


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _reset_singleton_routers():
    # Тестовый шим: модульные router-синглтоны нельзя переиспользовать между
    # вызовами build_dispatcher (aiogram 3.4.1: один parent на роутер).
    # Сбрасываем _parent_router перед каждым тестом, чтобы каждый тест строил
    # диспетчер начисто. Будет удалён, когда Task 9/2b введёт фабрики.
    routers = [_start_router, _order_router, _delivery_router, _payment_router,
               _my_orders_router, _manager_router, _crop_router]
    for r in routers:
        r._parent_router = None
    yield
    for r in routers:
        r._parent_router = None


@pytest.mark.asyncio
async def test_build_dispatcher_has_studio_middleware(db_session):
    studio = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                                    admin_username="a", admin_password="p")
    dp = build_dispatcher(studio)
    assert isinstance(dp, Dispatcher)
    # StudioMiddleware навешан на message-обсервер
    from src.bot.middlewares.studio import StudioMiddleware
    assert any(isinstance(m, StudioMiddleware) for m in dp.message.outer_middleware)
    assert len(dp.sub_routers) >= 7  # все базовые роутеры включены


def test_base_router_factories_nonempty():
    assert len(BASE_ROUTER_FACTORIES) >= 7


@pytest.mark.asyncio
async def test_studio_specific_routers_included(db_session, monkeypatch):
    from aiogram import Router
    marker = Router(name="custom_marker")
    monkeypatch.setitem(STUDIO_ROUTER_FACTORIES, "s1", [lambda: marker])
    studio = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                                    admin_username="a", admin_password="p")
    dp = build_dispatcher(studio)
    # роутер студии включён в дерево
    assert any(r.name == "custom_marker" for r in dp.sub_routers)
