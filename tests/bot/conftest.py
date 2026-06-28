"""Фейковые aiogram-объекты и хелперы для тестов хендлеров."""
from types import SimpleNamespace
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey


class FakeBot:
    """Фейковый Bot: пишет все исходящие вызовы в .calls."""
    def __init__(self, bot_id: int = 100):
        self.id = bot_id
        self.calls: list[dict] = []

    async def send_message(self, chat_id, text, **kw):
        self.calls.append({"method": "send_message", "chat_id": chat_id, "text": text, **kw})

    async def send_photo(self, chat_id, photo, caption=None, **kw):
        self.calls.append({"method": "send_photo", "chat_id": chat_id, "photo": photo, "caption": caption, **kw})

    async def send_document(self, chat_id, document, caption=None, **kw):
        self.calls.append({"method": "send_document", "chat_id": chat_id, "document": document, "caption": caption, **kw})


class FakeMessage:
    """Фейковый Message с async .answer()."""
    def __init__(self, text=None, from_user_id=1, chat_id=1, bot=None,
                 photo=None, document=None, web_app_data=None, media_group_id=None):
        self.text = text
        self.bot = bot or FakeBot()
        self.from_user = SimpleNamespace(id=from_user_id, username="u", first_name="A", last_name="B", full_name="A B")
        self.chat = SimpleNamespace(id=chat_id, type="private", title=None)
        self.photo = photo
        self.document = document
        self.web_app_data = web_app_data
        self.media_group_id = media_group_id
        self.answers: list[dict] = []

    async def answer(self, text, **kw):
        rec = {"method": "send_message", "chat_id": self.chat.id, "text": text, **kw}
        self.answers.append(rec)
        self.bot.calls.append(rec)

    async def edit_text(self, text, **kw):
        rec = {"method": "edit_text", "text": text, **kw}
        self.answers.append(rec)
        self.bot.calls.append(rec)

    async def delete(self):
        self.bot.calls.append({"method": "delete"})


class FakeCallbackQuery:
    """Фейковый CallbackQuery с async .answer()."""
    def __init__(self, data, from_user_id=1, message=None, bot=None):
        self.data = data
        self.bot = bot or (message.bot if message else FakeBot())
        self.from_user = SimpleNamespace(id=from_user_id, username="u", first_name="A", last_name="B", full_name="A B")
        self.message = message or FakeMessage(bot=self.bot)
        self.answered = False
        self.answer_text = None

    async def answer(self, text=None, show_alert=False, **kw):
        self.answered = True
        self.answer_text = text


def make_state(bot_id: int = 100, chat_id: int = 1, user_id: int = 1) -> FSMContext:
    """Реальный FSMContext поверх изолированного MemoryStorage."""
    storage = MemoryStorage()
    key = StorageKey(bot_id=bot_id, chat_id=chat_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)
