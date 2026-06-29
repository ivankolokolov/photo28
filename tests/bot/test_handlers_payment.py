"""Тесты хендлеров payment.py — StudioContext."""
import os
import pytest
from types import SimpleNamespace
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.models.order import OrderStatus, DeliveryType
from tests.bot.conftest import FakeBot, FakeCallbackQuery, FakeMessage, make_state, make_ctx


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


# ---------------------------------------------------------------------------
# skip_promocode
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skip_promocode_sets_pending_payment_and_shows_studio_phone(db_session):
    """skip_promocode ставит статус PENDING_PAYMENT и показывает payment_phone студии."""
    from src.bot.handlers.payment import skip_promocode

    studio = await provision_studio(
        db_session, slug="s1", name="Studio1", bot_token="t1",
        admin_username="a", admin_password="p",
    )
    # Устанавливаем реквизиты оплаты на студию
    studio.payment_phone = "+79991234567"
    studio.payment_card = "4000000000001234"
    studio.payment_receiver = "ТестОплата"
    await db_session.commit()
    await db_session.refresh(studio)

    ctx = await make_ctx(db_session, studio)

    # Создаём пользователя и заказ с доставкой
    user = await ctx.orders.get_or_create_user(telegram_id=42, username="tester")
    order = await ctx.orders.create_order(user)
    await ctx.orders.set_delivery_info(order, DeliveryType.PICKUP)

    state = make_state(user_id=42)
    await state.update_data(order_id=order.id)

    bot = FakeBot()
    msg = FakeMessage(bot=bot, from_user_id=42)
    cb = FakeCallbackQuery(data="skip_promocode", from_user_id=42, message=msg, bot=bot)

    await skip_promocode(cb, state, ctx)

    # Статус обновлён
    refreshed = await ctx.orders.get_order_by_id(order.id)
    assert refreshed.status == OrderStatus.PENDING_PAYMENT

    # Сообщение содержит payment_phone из ctx.studio
    edits = [c for c in bot.calls if c.get("method") == "edit_text"]
    assert edits, "Ожидался вызов edit_text"
    assert "+79991234567" in edits[0]["text"]


# ---------------------------------------------------------------------------
# process_payment_receipt_photo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_payment_receipt_photo_saves_receipt_and_notifies_manager(db_session):
    """process_payment_receipt_photo сохраняет file_id, ставит PAID и шлёт фото менеджеру."""
    from src.bot.handlers.payment import process_payment_receipt_photo

    studio = await provision_studio(
        db_session, slug="s2", name="Studio2", bot_token="t2",
        admin_username="b", admin_password="p",
    )
    studio.manager_chat_id = "-100123456"
    studio.manager_username = "mgr_test"
    await db_session.commit()
    await db_session.refresh(studio)

    ctx = await make_ctx(db_session, studio)

    user = await ctx.orders.get_or_create_user(telegram_id=55, username="buyer")
    order = await ctx.orders.create_order(user)
    await ctx.orders.set_delivery_info(order, DeliveryType.PICKUP)
    # Статус PENDING_PAYMENT перед загрузкой квитанции
    await ctx.orders.update_order_status(order, OrderStatus.PENDING_PAYMENT)

    state = make_state(user_id=55)
    await state.update_data(order_id=order.id)

    bot = FakeBot()
    # FakeMessage с photo (список; handler берёт photo[-1].file_id)
    photo_obj = SimpleNamespace(file_id="receipt_file_abc")
    msg = FakeMessage(bot=bot, from_user_id=55, photo=[photo_obj])
    msg.chat = SimpleNamespace(id=55, type="private", title=None)

    await process_payment_receipt_photo(msg, state, bot, ctx)

    # Статус PAID
    refreshed = await ctx.orders.get_order_by_id(order.id)
    assert refreshed.status == OrderStatus.PAID
    assert refreshed.payment_receipt_file_id == "receipt_file_abc"

    # Менеджеру отправлено фото
    photos_sent = [c for c in bot.calls if c.get("method") == "send_photo"]
    assert photos_sent, "Ожидался вызов send_photo для менеджера"
    assert photos_sent[0]["chat_id"] == -100123456

    # Клиенту отправлено итоговое сообщение с manager_username из студии
    user_msgs = [c for c in msg.answers if c.get("method") == "send_message"]
    assert user_msgs, "Ожидалось финальное сообщение клиенту"
    assert "mgr_test" in user_msgs[0]["text"]
