"""Тесты studio-aware NotificationService."""
import pytest
from src.models.studio import Studio
from src.models.setting import Setting
from src.models.order import DeliveryType, OrderStatus
from src.services.settings_service import SettingsService, SettingKeys
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


@pytest.mark.asyncio
async def test_shipped_pickup_uses_studio_address(db_session):
    SettingsService.invalidate_cache()
    s = Studio(slug="s1", name="S1", manager_chat_id="-1001234")
    db_session.add(s); await db_session.commit()
    db_session.add(Setting(
        studio_id=s.id, key=SettingKeys.DELIVERY_PICKUP_ADDRESS,
        value="г. Питер, ул. Студийная 1",
    ))
    await db_session.commit()
    await SettingsService(db_session).load_cache(s.id)

    bot = FakeBot()
    svc = NotificationService(bot, s, SettingsFacade(s.id), ProductsFacade(s.id))

    class _PickupOrder(_Order):
        delivery_type = DeliveryType.PICKUP

    msg = svc._get_shipped_message(_PickupOrder())
    assert "г. Питер, ул. Студийная 1" in msg


@pytest.mark.asyncio
async def test_confirmed_status_full_text(db_session):
    s = Studio(slug="s1", name="S1", manager_chat_id="-1001234")
    db_session.add(s); await db_session.commit()
    bot = FakeBot()
    svc = NotificationService(bot, s, SettingsFacade(s.id), ProductsFacade(s.id))

    assert await svc.notify_client_status_changed(_Order(), OrderStatus.CONFIRMED.value) is True
    sent = bot.calls[-1]["text"]
    assert "Сообщим, когда фотографии" in sent
