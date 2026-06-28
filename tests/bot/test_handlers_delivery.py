"""Тесты хендлеров delivery.py — StudioContext."""
import os
import pytest
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from tests.bot.conftest import FakeBot, FakeCallbackQuery, FakeMessage, make_state, make_ctx


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_get_delivery_message_contains_enabled_names(db_session):
    """get_delivery_message(ctx) содержит названия включённых способов доставки."""
    from src.bot.handlers.delivery import get_delivery_message

    studio = await provision_studio(
        db_session, slug="s1", name="Studio1", bot_token="t1",
        admin_username="a", admin_password="p",
    )
    ctx = await make_ctx(db_session, studio)

    msg = get_delivery_message(ctx)

    # DEFAULT_SETTINGS включают OZON, COURIER, PICKUP с именами:
    # "ОЗОН доставка", "Курьером по Москве", "Самовывоз"
    assert "ОЗОН" in msg


@pytest.mark.asyncio
async def test_select_delivery_edits_message_and_sets_state(db_session):
    """select_delivery редактирует сообщение с меню доставки и ставит selecting_delivery."""
    from src.bot.handlers.delivery import select_delivery
    from src.bot.states import OrderStates

    studio = await provision_studio(
        db_session, slug="s2", name="Studio2", bot_token="t2",
        admin_username="b", admin_password="p",
    )
    ctx = await make_ctx(db_session, studio)

    bot = FakeBot()
    msg = FakeMessage(bot=bot, from_user_id=1)
    cb = FakeCallbackQuery(data="select_delivery", from_user_id=1, message=msg, bot=bot)
    state = make_state(user_id=1)

    await select_delivery(cb, state, ctx)

    # Проверяем, что сообщение было отредактировано
    edits = [c for c in bot.calls if c.get("method") == "edit_text"]
    assert edits, "Ожидался вызов edit_text"

    # Проверяем состояние
    assert await state.get_state() == OrderStates.selecting_delivery.state
