"""Тесты StudioMiddleware."""
import os
import pytest
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.bot.middlewares.studio import StudioMiddleware
from tests.bot.conftest import FakeMessage


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_middleware_injects_ctx(db_session, monkeypatch):
    studio = await provision_studio(db_session, slug="s1", name="S1", bot_token="t1",
                                    admin_username="a1", admin_password="p")
    # Подменяем async_session, чтобы middleware использовал тестовую сессию
    import src.bot.middlewares.studio as mod

    class _SessionCtx:
        async def __aenter__(self): return db_session
        async def __aexit__(self, *a): return False
    monkeypatch.setattr(mod, "async_session", lambda: _SessionCtx())

    mw = StudioMiddleware(studio_id=studio.id)
    captured = {}

    async def handler(event, data):
        captured["ctx"] = data.get("ctx")
        return "ok"

    result = await mw(handler, FakeMessage(text="/start"), {})
    assert result == "ok"
    assert captured["ctx"].studio_id == studio.id
    assert captured["ctx"].studio.slug == "s1"


@pytest.mark.asyncio
async def test_middleware_skips_inactive_studio(db_session, monkeypatch):
    studio = await provision_studio(db_session, slug="s1", name="S1", bot_token="t1",
                                    admin_username="a1", admin_password="p")
    studio.is_active = False
    await db_session.commit()
    import src.bot.middlewares.studio as mod

    class _SessionCtx:
        async def __aenter__(self): return db_session
        async def __aexit__(self, *a): return False
    monkeypatch.setattr(mod, "async_session", lambda: _SessionCtx())

    mw = StudioMiddleware(studio_id=studio.id)
    called = {"n": 0}

    async def handler(event, data):
        called["n"] += 1

    await mw(handler, FakeMessage(text="/start"), {})
    assert called["n"] == 0  # хендлер не вызван для неактивной студии
