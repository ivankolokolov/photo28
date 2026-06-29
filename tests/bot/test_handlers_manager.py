"""Тесты хендлеров manager.py — StudioContext."""
import pytest
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.models.order import OrderStatus
from tests.bot.conftest import FakeBot, FakeCallbackQuery, FakeMessage, make_ctx


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


# ---------------------------------------------------------------------------
# manager_confirm_payment — PAID → CONFIRMED
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_confirm_payment_transitions_paid_to_confirmed(db_session):
    """manager_confirm_payment переводит заказ PAID→CONFIRMED и уведомляет клиента."""
    from src.bot.handlers.manager import manager_confirm_payment

    studio = await provision_studio(
        db_session, slug="s1", name="Studio1", bot_token="t1",
        admin_username="a", admin_password="p",
    )
    ctx = await make_ctx(db_session, studio)

    # Создаём пользователя и заказ
    user = await ctx.orders.get_or_create_user(telegram_id=777, username="client")
    order = await ctx.orders.create_order(user)
    await ctx.orders.update_order_status(order, OrderStatus.PAID)

    # Группаповое сообщение менеджера
    bot = FakeBot()
    group_msg = FakeMessage(caption="🧾 заказ", bot=bot)
    callback = FakeCallbackQuery(
        data=f"mgr_confirm:{order.id}",
        from_user_id=555,
        message=group_msg,
        bot=bot,
    )

    await manager_confirm_payment(callback, bot=bot, ctx=ctx)

    # Статус изменён на CONFIRMED
    refreshed = await ctx.orders.get_order_by_id(order.id)
    assert refreshed.status == OrderStatus.CONFIRMED

    # Клиент получил уведомление с "подтверждена"
    client_msgs = [
        c for c in bot.calls
        if c.get("method") == "send_message"
        and c.get("chat_id") == 777
    ]
    assert client_msgs, "Клиент не получил уведомление"
    assert "подтверждена" in client_msgs[0]["text"].lower() or "подтверждена" in client_msgs[0]["text"]

    # callback.answer вызван
    assert callback.answered


# ---------------------------------------------------------------------------
# manager_confirm_payment — не-PAID заказ → алерт, статус не меняется
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_confirm_payment_non_paid_order_sends_alert(db_session):
    """manager_confirm_payment для не-PAID заказа отвечает алертом и не меняет статус."""
    from src.bot.handlers.manager import manager_confirm_payment

    studio = await provision_studio(
        db_session, slug="s2", name="Studio2", bot_token="t2",
        admin_username="b", admin_password="p",
    )
    ctx = await make_ctx(db_session, studio)

    user = await ctx.orders.get_or_create_user(telegram_id=888, username="client2")
    order = await ctx.orders.create_order(user)
    # Статус остаётся DRAFT (не PAID)

    bot = FakeBot()
    group_msg = FakeMessage(caption="🧾 заказ", bot=bot)
    callback = FakeCallbackQuery(
        data=f"mgr_confirm:{order.id}",
        from_user_id=555,
        message=group_msg,
        bot=bot,
    )

    await manager_confirm_payment(callback, bot=bot, ctx=ctx)

    # Статус НЕ изменился
    refreshed = await ctx.orders.get_order_by_id(order.id)
    assert refreshed.status == OrderStatus.DRAFT

    # Алерт отправлен
    assert callback.answered
    assert callback.answer_text is not None
