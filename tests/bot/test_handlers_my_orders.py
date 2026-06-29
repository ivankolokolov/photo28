"""Тесты хендлеров my_orders.py — StudioContext."""
import os
import pytest
from cryptography.fernet import Fernet

from src.models.order import DeliveryType, OrderStatus
from src.services.studio_provisioning import provision_studio
from src.services.delivery_options import delivery_display_name
from tests.bot.conftest import FakeBot, FakeCallbackQuery, FakeMessage, make_state, make_ctx


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_cmd_orders_shows_orders_list_and_sets_state(db_session):
    """cmd_orders показывает список заказов пользователя и ставит состояние viewing_orders."""
    from src.bot.handlers.my_orders import cmd_orders
    from src.bot.states import MyOrdersStates

    studio = await provision_studio(
        db_session, slug="s1", name="Studio1", bot_token="t1",
        admin_username="a", admin_password="p",
    )
    ctx = await make_ctx(db_session, studio)

    # Создаём пользователя и не-черновиковый заказ
    user = await ctx.orders.get_or_create_user(telegram_id=101, username="user1")
    order = await ctx.orders.create_order(user)
    # Переводим в статус, отличный от DRAFT, чтобы get_user_orders возвращал заказ
    await ctx.orders.update_order_status(order, OrderStatus.PENDING_PAYMENT)

    msg = FakeMessage(text="/orders", from_user_id=101)
    state = make_state(user_id=101)

    await cmd_orders(msg, state, ctx)

    # Проверяем, что сообщение было отправлено
    assert msg.answers, "Ожидался хотя бы один ответ"
    # Проверяем состояние
    assert await state.get_state() == MyOrdersStates.viewing_orders.state


@pytest.mark.asyncio
async def test_show_order_details_contains_delivery_display_name(db_session):
    """show_order_details содержит delivery_display_name(ctx.settings, PICKUP)."""
    from src.bot.handlers.my_orders import show_order_details
    from src.bot.states import MyOrdersStates

    studio = await provision_studio(
        db_session, slug="s2", name="Studio2", bot_token="t2",
        admin_username="b", admin_password="p",
    )
    ctx = await make_ctx(db_session, studio)

    # Создаём пользователя и заказ с типом доставки PICKUP
    user = await ctx.orders.get_or_create_user(telegram_id=202, username="user2")
    order = await ctx.orders.create_order(user)

    # Добавляем фото к заказу
    products = ctx.products.top_level()
    product = products[0]
    await ctx.orders.add_photo(order, product.id, "test_file_id")

    # Устанавливаем тип доставки PICKUP и переводим в не-черновой статус
    await ctx.orders.set_delivery_info(order, delivery_type=DeliveryType.PICKUP)
    await ctx.orders.update_order_status(order, OrderStatus.PENDING_PAYMENT)

    # Получаем ожидаемое отображаемое имя доставки
    expected_delivery_name = delivery_display_name(ctx.settings, DeliveryType.PICKUP)

    bot = FakeBot()
    msg = FakeMessage(bot=bot, from_user_id=202)
    cb = FakeCallbackQuery(
        data=f"order_details:{order.id}",
        from_user_id=202,
        message=msg,
        bot=bot,
    )
    state = make_state(user_id=202)

    await show_order_details(cb, state, ctx)

    # Проверяем, что сообщение было отредактировано с именем доставки
    edits = [c for c in bot.calls if c.get("method") == "edit_text"]
    assert edits, "Ожидался вызов edit_text"
    detail_text = edits[0]["text"]
    assert expected_delivery_name in detail_text, (
        f"Ожидалось '{expected_delivery_name}' в тексте деталей: {detail_text!r}"
    )
    # Проверяем состояние
    assert await state.get_state() == MyOrdersStates.viewing_order_details.state


def test_build_my_orders_router_registers_handlers():
    from src.bot.handlers.my_orders import build_my_orders_router
    from aiogram import Router
    r = build_my_orders_router()
    assert isinstance(r, Router)
    assert len(r.message.handlers) >= 2
    assert len(r.callback_query.handlers) >= 2
