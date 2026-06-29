"""Тест выборки активных студий и прогрева кешей."""
import os, pytest
from cryptography.fernet import Fernet
from src.services.studio_provisioning import provision_studio
from src.bot.registry import load_active_studios


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_load_active_studios_excludes_inactive(db_session):
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    b = await provision_studio(db_session, slug="b", name="B", bot_token="t", admin_username="b", admin_password="p")
    b.is_active = False
    await db_session.commit()
    studios = await load_active_studios(db_session)
    slugs = {s.slug for s in studios}
    assert "a" in slugs and "b" not in slugs
