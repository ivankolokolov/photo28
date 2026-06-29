import os, pytest
from cryptography.fernet import Fernet
from src.services.studio_provisioning import provision_studio
from src.bot.handlers.start import cmd_start
from src.bot.states import OrderStates
from tests.bot.conftest import FakeMessage, make_state, make_ctx


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_cmd_start_creates_order_and_greets(db_session):
    studio = await provision_studio(db_session, slug="s1", name="StudioOne", bot_token="t",
                                    admin_username="a", admin_password="p")
    ctx = await make_ctx(db_session, studio)
    msg = FakeMessage(text="/start", from_user_id=999)
    state = make_state(user_id=999)

    await cmd_start(msg, state, ctx)

    # приветствие отправлено и содержит имя студии
    assert any("StudioOne" in c.get("text", "") for c in msg.bot.calls)
    # создан черновик заказа в этой студии
    assert (await state.get_data()).get("order_id") is not None
    assert await ctx.orders.get_user_draft_order(
        await ctx.orders.get_or_create_user(telegram_id=999)) is not None
    assert await state.get_state() == OrderStates.selecting_format.state
