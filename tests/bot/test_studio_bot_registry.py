"""Тесты in-memory реестра ботов студий."""
import os
import pytest
from cryptography.fernet import Fernet
from aiogram import Bot, Dispatcher

from src.services.studio_provisioning import provision_studio
from src.bot.registry import StudioBotRegistry


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_add_and_get_by_secret(db_session):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                               admin_username="a", admin_password="p")
    reg = StudioBotRegistry()
    reg.add(s)
    found = reg.get_by_secret(s.webhook_secret)
    assert found is not None
    studio_id, bot, dp = found
    assert studio_id == s.id
    assert isinstance(bot, Bot) and isinstance(dp, Dispatcher)
    assert reg.get_by_secret("nope") is None


@pytest.mark.asyncio
async def test_remove(db_session):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                               admin_username="a", admin_password="p")
    reg = StudioBotRegistry()
    reg.add(s)
    bot = reg.remove(s.id)
    assert bot is not None
    assert reg.get_by_secret(s.webhook_secret) is None


@pytest.mark.asyncio
async def test_skips_studio_without_token(db_session):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                               admin_username="a", admin_password="p")
    s.bot_token = None
    await db_session.commit()
    reg = StudioBotRegistry()
    reg.add(s)  # не должно падать
    assert reg.get_by_secret(s.webhook_secret) is None
