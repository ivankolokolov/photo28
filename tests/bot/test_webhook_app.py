"""Тесты webhook-приложения."""
import os
import pytest
from cryptography.fernet import Fernet
from aiohttp.test_utils import TestClient, TestServer

from src.services.studio_provisioning import provision_studio
from src.bot.registry import StudioBotRegistry
from src.bot.webhook_app import build_webhook_app


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_unknown_secret_404(db_session):
    reg = StudioBotRegistry()
    app = build_webhook_app(reg)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/webhook/doesnotexist", json={"update_id": 1})
        assert resp.status == 404


@pytest.mark.asyncio
async def test_known_secret_feeds_dispatcher(db_session, monkeypatch):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                               admin_username="a", admin_password="p")
    reg = StudioBotRegistry()
    reg.add(s)
    _sid, bot, dp = reg.get_by_secret(s.webhook_secret)

    called = {}
    async def fake_feed(b, update):
        called["bot"] = b
        called["update_id"] = update.update_id
    monkeypatch.setattr(dp, "feed_webhook_update", fake_feed)

    app = build_webhook_app(reg)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(f"/webhook/{s.webhook_secret}", json={"update_id": 42})
        assert resp.status == 200
    assert called["update_id"] == 42
    assert called["bot"] is bot


@pytest.mark.asyncio
async def test_healthz(db_session):
    reg = StudioBotRegistry()
    app = build_webhook_app(reg)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/healthz")
        assert resp.status == 200
        body = await resp.json()
        assert body["status"] == "ok"
