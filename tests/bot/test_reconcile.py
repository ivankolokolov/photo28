"""Тесты reconcile_studios: сверка реестра с активными студиями в БД."""
import pytest
from cryptography.fernet import Fernet
from aiogram import Bot

from src.services.studio_provisioning import provision_studio
from src.bot.registry import StudioBotRegistry
from src.bot import lifecycle
from src.bot.reconcile import reconcile_studios


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _mock_webhooks(monkeypatch):
    """Патчим Bot.set_webhook и Bot.delete_webhook на no-op на уровне класса."""
    async def noop_set_webhook(self_bot, url, **kw):
        pass

    async def noop_delete_webhook(self_bot, **kw):
        pass

    monkeypatch.setattr(Bot, "set_webhook", noop_set_webhook)
    monkeypatch.setattr(Bot, "delete_webhook", noop_delete_webhook)


@pytest.fixture(autouse=True)
def _empty_base_webhook_url(monkeypatch):
    """Гарантируем пустой base_webhook_url → guard в register_studio пропустит set_webhook."""
    monkeypatch.setattr(lifecycle.settings, "base_webhook_url", "")


@pytest.mark.asyncio
async def test_reconcile_adds_active_studio(db_session):
    """Пустой реестр + 1 активная студия → reconcile добавляет (added=1, removed=0)."""
    studio = await provision_studio(
        db_session,
        slug="rec1",
        name="Rec1",
        bot_token="123:TOKEN1",
        admin_username="admin1",
        admin_password="pass1",
    )
    assert studio.is_active  # provision_studio должна создавать активную студию

    registry = StudioBotRegistry()
    added, removed = await reconcile_studios(registry, db_session)

    assert added == 1
    assert removed == 0
    # Студия должна быть доступна по webhook_secret
    entry = registry.get_by_secret(studio.webhook_secret)
    assert entry is not None, "Студия должна быть в реестре после reconcile"
    sid, bot, dp = entry
    assert sid == studio.id


@pytest.mark.asyncio
async def test_reconcile_removes_deactivated_studio(db_session):
    """Студия в реестре стала is_active=False → reconcile удаляет (added=0, removed=1)."""
    studio = await provision_studio(
        db_session,
        slug="rec2",
        name="Rec2",
        bot_token="456:TOKEN2",
        admin_username="admin2",
        admin_password="pass2",
    )
    assert studio.is_active

    # Первый reconcile: добавляем студию
    registry = StudioBotRegistry()
    added, removed = await reconcile_studios(registry, db_session)
    assert added == 1
    assert removed == 0
    assert registry.get_by_secret(studio.webhook_secret) is not None

    # Деактивируем студию и патчим session.close у бота перед вторым reconcile
    studio.is_active = False
    await db_session.commit()

    # Патчим session.close у всех ботов в реестре, чтобы не падало
    for _sid, bot, _dp in registry.entries():
        async def _fake_close():
            pass
        bot.session.close = _fake_close

    # Второй reconcile: удаляем студию
    added2, removed2 = await reconcile_studios(registry, db_session)
    assert added2 == 0
    assert removed2 == 1
    # Студия больше не в реестре
    assert registry.get_by_secret(studio.webhook_secret) is None
