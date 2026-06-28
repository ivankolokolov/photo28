"""Проверка тестовых фейков aiogram."""
import pytest
from tests.bot.conftest import FakeBot, FakeMessage, FakeCallbackQuery, make_state


@pytest.mark.asyncio
async def test_fake_message_answer_records_call():
    msg = FakeMessage(text="привет", from_user_id=42)
    await msg.answer("ответ", parse_mode="HTML")
    assert msg.bot.calls[-1]["method"] == "send_message"
    assert msg.bot.calls[-1]["text"] == "ответ"
    assert msg.from_user.id == 42


@pytest.mark.asyncio
async def test_fake_callback_answer():
    cb = FakeCallbackQuery(data="go_to_payment", from_user_id=7)
    await cb.answer()
    assert cb.answered is True
    assert cb.data == "go_to_payment"


@pytest.mark.asyncio
async def test_fake_message_edit_caption_and_media():
    msg = FakeMessage(caption="старая подпись")
    assert msg.caption == "старая подпись"
    await msg.edit_caption("новая", parse_mode="HTML")
    assert msg.bot.calls[-1]["method"] == "edit_caption"
    await msg.edit_media("media_obj")
    assert msg.bot.calls[-1]["method"] == "edit_media"
    await msg.delete()
    assert msg.answers[-1]["method"] == "delete"


@pytest.mark.asyncio
async def test_make_state_roundtrip():
    state = make_state()
    await state.update_data(order_id=5)
    data = await state.get_data()
    assert data["order_id"] == 5
