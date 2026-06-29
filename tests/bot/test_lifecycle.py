"""Тесты lifecycle (register/unregister без реальной сети — мокаем set_webhook)."""
import pytest
from cryptography.fernet import Fernet
from aiogram import Bot

from src.services.studio_provisioning import provision_studio
from src.bot.registry import StudioBotRegistry
from src.bot import lifecycle


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


def test_webhook_url_for(monkeypatch):
    monkeypatch.setattr(lifecycle.settings, "base_webhook_url", "https://b.example")
    assert lifecycle.webhook_url_for("abc") == "https://b.example/webhook/abc"


@pytest.mark.asyncio
async def test_register_sets_webhook(db_session, monkeypatch):
    monkeypatch.setattr(lifecycle.settings, "base_webhook_url", "https://b.example")
    s = await provision_studio(
        db_session,
        slug="s1",
        name="S1",
        bot_token="123:ABC",
        admin_username="a",
        admin_password="p",
    )
    calls = {}

    # Мокаем Bot.set_webhook на уровне класса до вызова registry.add,
    # чтобы перехватить вызов внутри register_studio (который сам вызывает registry.add).
    async def fake_set_webhook(self_bot, url, **kw):
        calls["url"] = url

    monkeypatch.setattr(Bot, "set_webhook", fake_set_webhook)

    reg = StudioBotRegistry()
    await lifecycle.register_studio(reg, s)

    # register_studio должен добавить студию в реестр
    entry = reg.get_by_secret(s.webhook_secret)
    assert entry is not None, "Студия должна быть добавлена в реестр"

    # register_studio должен вызвать set_webhook с правильным URL
    assert "url" in calls, "set_webhook должен быть вызван"
    assert calls["url"] == f"https://b.example/webhook/{s.webhook_secret}"


@pytest.mark.asyncio
async def test_unregister_deletes_webhook(db_session, monkeypatch):
    monkeypatch.setattr(lifecycle.settings, "base_webhook_url", "https://b.example")
    s = await provision_studio(
        db_session,
        slug="s2",
        name="S2",
        bot_token="123:DEF",
        admin_username="b",
        admin_password="q",
    )
    calls = {"set": [], "delete": [], "close": []}

    async def fake_set_webhook(self_bot, url, **kw):
        calls["set"].append(url)

    async def fake_delete_webhook(self_bot, **kw):
        calls["delete"].append(True)

    async def fake_session_close(self_session):
        calls["close"].append(True)

    monkeypatch.setattr(Bot, "set_webhook", fake_set_webhook)
    monkeypatch.setattr(Bot, "delete_webhook", fake_delete_webhook)
    # Мокаем session.close через Bot.session.close — aiogram Bot.session — это AiohttpSession
    # Доступ к нему через экземпляр, поэтому патчим после add
    reg = StudioBotRegistry()
    await lifecycle.register_studio(reg, s)

    # Получаем бота и патчим его session.close
    entry = reg.get_by_secret(s.webhook_secret)
    assert entry is not None
    _sid, bot, _dp = entry
    bot.session.close = lambda: (calls["close"].append(True), None)[1]  # type: ignore

    # Заменяем close на корутину
    import asyncio
    async def fake_close():
        calls["close"].append(True)

    bot.session.close = fake_close  # type: ignore

    await lifecycle.unregister_studio(reg, s.id)

    # После unregister студии не должно быть в реестре
    assert reg.get_by_secret(s.webhook_secret) is None, "Студия должна быть удалена из реестра"
    assert len(calls["delete"]) == 1, "delete_webhook должен быть вызван"
    assert len(calls["close"]) == 1, "session.close должен быть вызван"
