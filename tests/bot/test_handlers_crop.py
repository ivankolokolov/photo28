"""Тесты хендлеров crop.py — StudioContext."""
import json
import pytest
from types import SimpleNamespace
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.bot.states import OrderStates
from tests.bot.conftest import FakeBot, FakeCallbackQuery, FakeMessage, make_state, make_ctx


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_skip_crop_shows_order_summary_and_sets_state(db_session):
    """skip_crop показывает сводку заказа и устанавливает состояние reviewing_order."""
    from src.bot.handlers.crop import skip_crop

    studio = await provision_studio(
        db_session, slug="crop1", name="CropStudio", bot_token="tc1",
        admin_username="a", admin_password="p",
    )
    ctx = await make_ctx(db_session, studio)

    user = await ctx.orders.get_or_create_user(telegram_id=777, username="cropuser")
    order = await ctx.orders.create_order(user)

    products = ctx.products.top_level()
    product = products[0]
    await ctx.orders.add_photo(order, product.id, "file_id_1")
    await ctx.orders.add_photo(order, product.id, "file_id_2")

    order = await ctx.orders.get_order_by_id(order.id)

    bot = FakeBot()
    msg = FakeMessage(bot=bot, from_user_id=777)
    cb = FakeCallbackQuery(data="skip_crop", from_user_id=777, message=msg, bot=bot)
    state = make_state(user_id=777)
    await state.update_data(order_id=order.id)

    await skip_crop(cb, state, ctx)

    assert cb.answered
    # Сводка заказа показана через edit_text
    edit_calls = [c for c in msg.bot.calls if c.get("method") == "edit_text"]
    assert len(edit_calls) > 0
    assert any("Ваш заказ" in c.get("text", "") for c in edit_calls)
    assert await state.get_state() == OrderStates.reviewing_order.state


@pytest.mark.asyncio
async def test_handle_webapp_data_saves_crop_and_sends_delivery(db_session):
    """handle_webapp_data сохраняет кроп и отправляет сообщение доставки."""
    from src.bot.handlers.crop import handle_webapp_data

    studio = await provision_studio(
        db_session, slug="crop2", name="CropStudio2", bot_token="tc2",
        admin_username="b", admin_password="p",
    )
    ctx = await make_ctx(db_session, studio)

    user = await ctx.orders.get_or_create_user(telegram_id=888, username="cropuser2")
    order = await ctx.orders.create_order(user)

    products = ctx.products.top_level()
    product = products[0]
    await ctx.orders.add_photo(order, product.id, "file_id_crop")
    order = await ctx.orders.get_order_by_id(order.id)
    photo = order.photos[0]

    crop_payload = {"photos": [{"id": photo.id, "crop": {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.9}}]}
    web_app_data = SimpleNamespace(data=json.dumps(crop_payload))

    bot = FakeBot()
    state = make_state(user_id=888)
    await state.update_data(order_id=order.id)
    msg = FakeMessage(bot=bot, from_user_id=888, web_app_data=web_app_data)

    await handle_webapp_data(msg, state, ctx)

    # Кроп сохранён
    updated_photo = await ctx.orders.get_photo_by_id(photo.id)
    assert updated_photo is not None
    assert updated_photo.crop_confirmed is True

    # Сообщение доставки отправлено
    answer_calls = [c for c in bot.calls if c.get("method") == "send_message"]
    assert len(answer_calls) > 0

    # Состояние переключено
    assert await state.get_state() == OrderStates.selecting_delivery.state


def test_build_crop_router_registers_handlers():
    from src.bot.handlers.crop import build_crop_router
    from aiogram import Router
    r = build_crop_router()
    assert isinstance(r, Router)
    assert len(r.message.handlers) >= 1
    assert len(r.callback_query.handlers) >= 2
