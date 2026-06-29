"""Тесты сборки Dispatcher на студию."""
import pytest
from cryptography.fernet import Fernet
from aiogram import Dispatcher

from src.services.studio_provisioning import provision_studio
from src.bot.registry import build_dispatcher, STUDIO_ROUTER_FACTORIES, BASE_ROUTER_FACTORIES


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


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


@pytest.mark.asyncio
async def test_two_studios_build_independent_dispatchers(db_session):
    s1 = await provision_studio(db_session, slug="a", name="A", bot_token="t1", admin_username="a", admin_password="p")
    s2 = await provision_studio(db_session, slug="b", name="B", bot_token="t2", admin_username="b", admin_password="p")
    dp1 = build_dispatcher(s1)
    dp2 = build_dispatcher(s2)
    assert dp1 is not dp2
    assert len(dp1.sub_routers) >= 7 and len(dp2.sub_routers) >= 7  # обе получили базовые роутеры
