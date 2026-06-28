"""Тесты хендлеров order.py — StudioContext."""
import os
import pytest
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.services.settings_service import SettingsService, SettingKeys
from tests.bot.conftest import FakeBot, FakeCallbackQuery, FakeMessage, make_state, make_ctx


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_get_min_photos_reads_studio_setting(db_session):
    """get_min_photos(ctx) читает настройку MIN_PHOTOS студии."""
    from src.bot.handlers.order import get_min_photos
    studio = await provision_studio(db_session, slug="s1", name="S1", bot_token="t1",
                                    admin_username="a", admin_password="p")
    await SettingsService(db_session).set_value(studio.id, SettingKeys.MIN_PHOTOS, "7")
    ctx = await make_ctx(db_session, studio)
    assert get_min_photos(ctx) == 7


@pytest.mark.asyncio
async def test_finish_photos_below_min_shows_alert(db_session):
    """finish_photos отвечает алертом если фото меньше минимума."""
    from src.bot.handlers.order import finish_photos
    studio = await provision_studio(db_session, slug="s2", name="S2", bot_token="t2",
                                    admin_username="b", admin_password="p")
    await SettingsService(db_session).set_value(studio.id, SettingKeys.MIN_PHOTOS, "5")
    ctx = await make_ctx(db_session, studio)

    # Создаём пользователя и заказ
    user = await ctx.orders.get_or_create_user(telegram_id=42, username="u")
    order = await ctx.orders.create_order(user)

    # Добавляем 2 фото (меньше минимума 5)
    products = ctx.products.top_level()
    product = products[0]
    for i in range(2):
        await ctx.orders.add_photo(order, product.id, f"file_id_{i}")

    # Обновляем order чтобы увидеть photos
    order = await ctx.orders.get_order_by_id(order.id)

    bot = FakeBot()
    msg = FakeMessage(bot=bot, from_user_id=42)
    cb = FakeCallbackQuery(data="finish_photos", from_user_id=42, message=msg, bot=bot)
    state = make_state(user_id=42)
    await state.update_data(order_id=order.id)

    await finish_photos(cb, state, bot, ctx)

    assert cb.answered
    assert cb.answer_text is not None
    assert "5" in cb.answer_text  # min_photos is 5
