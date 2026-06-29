"""Тест webhook_secret студии."""
import os
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from src.services.studio_provisioning import provision_studio
from src.models.studio import Studio


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_provision_sets_webhook_secret(db_session):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                               admin_username="a", admin_password="p")
    assert s.webhook_secret
    assert len(s.webhook_secret) >= 20


@pytest.mark.asyncio
async def test_webhook_secret_unique_across_studios(db_session):
    s1 = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                                admin_username="a", admin_password="p")
    s2 = await provision_studio(db_session, slug="s2", name="S2", bot_token="t",
                                admin_username="b", admin_password="p")
    assert s1.webhook_secret != s2.webhook_secret
