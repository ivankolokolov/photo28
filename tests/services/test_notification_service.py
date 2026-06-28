"""Тесты studio-aware NotificationService."""
import pytest
from src.models.studio import Studio
from src.bot.context import SettingsFacade, ProductsFacade
from src.services.notification_service import NotificationService
from tests.bot.conftest import FakeBot


class _Order:
    order_number = "240101-AAAA"
    id = 1
    def photos_by_product(self): return {}
    photos_count = 0
    total_cost = 100
    delivery_type = None
    delivery_address = None
    class user:  # noqa
        username = "client"; first_name = "C"; telegram_id = 555


@pytest.mark.asyncio
async def test_manager_chat_id_from_studio(db_session):
    s = Studio(slug="s1", name="S1", manager_chat_id="-1001234")
    db_session.add(s); await db_session.commit()
    bot = FakeBot()
    svc = NotificationService(bot, s, SettingsFacade(s.id), ProductsFacade(s.id))
    assert svc._get_manager_chat_id() == -1001234


@pytest.mark.asyncio
async def test_no_chat_id_returns_none(db_session):
    s = Studio(slug="s1", name="S1", manager_chat_id=None)
    db_session.add(s); await db_session.commit()
    bot = FakeBot()
    svc = NotificationService(bot, s, SettingsFacade(s.id), ProductsFacade(s.id))
    assert svc._get_manager_chat_id() is None
    # notify должен мягко вернуть False без чата
    assert await svc.notify_receipt_uploaded(_Order(), "file_xyz") is False
