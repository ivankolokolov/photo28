# Мультитенантность бота (рантайм) — План реализации (под-проект №1, план 2a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать рантайм Telegram-бота мультитенантным: каждый бот привязан к студии, `studio_id` доезжает до всех хендлеров через инжектируемый `StudioContext`, все вызовы сервисов и хелперов студия-скоупленные; добавлена возможность кастомных хендлеров на отдельную студию. Polling сохраняется (webhook — план 2b).

**Architecture:** Один процесс, по одному `Bot` + собственному `Dispatcher` на каждую активную студию. Каждый `Dispatcher` собирается из базового набора роутеров плюс опциональных роутеров конкретной студии (реестр по slug). `StudioMiddleware`, привязанный к `studio_id` своей студии, на каждый апдейт открывает БД-сессию, строит `StudioContext` (studio_id + запись Studio + `OrderService` + фасады settings/products) и кладёт его в `data["ctx"]`. Хендлеры и хелперы принимают `ctx` и больше не открывают сессии и не дёргают глобальные сервисы напрямую. Сервисы `PricingService`/`NotificationService`/`FileService` и enum `DeliveryType` переводятся на studio-скоуп.

**Tech Stack:** Python 3.9+, aiogram 3.4.1 (BaseMiddleware, Router, Dispatcher, MemoryStorage), SQLAlchemy 2.0 async, PostgreSQL, pytest + pytest-asyncio. Тесты хендлеров — на фейковых aiogram-объектах (Message/CallbackQuery/Bot) + реальной тестовой БД.

## Global Constraints

- Python 3.9+. Использовать проектный venv: `/Users/user/Work/photo28/.venv/bin/python -m pytest`.
- PostgreSQL только; тесты на `TEST_DATABASE_URL` (`photo28_test`); фикстура `db_session` пересоздаёт схему per-test. `FERNET_KEY` задаётся в тестах через autouse-фикстуру там, где нужен.
- Сервисный слой из плана 1 НЕ менять по сигнатурам: `SettingsService.get(studio_id, key, default)`, `ProductService.get_product(studio_id, product_id)` и т.д. остаются studio_id-first. Новый код адаптируется к ним, а не наоборот.
- Тенантность ЯВНАЯ: `studio_id`/`ctx` передаются явно. Никаких скрытых глобалов (ContextVar) для студии.
- Каждый бот привязан к одной студии через свой `Dispatcher` + `StudioMiddleware(studio_id)`.
- Кастомные хендлеры на студию подключаются через реестр `STUDIO_ROUTER_FACTORIES[slug]` без правки базовых роутеров.
- Пути хранилища фото: `storage/{studio_id}/{order_number}/...`.
- Пристойный вывод тестов под `-W error`. Commit-сообщения на русском, префиксы `feat:`/`test:`/`refactor:`/`chore:`.
- `OrderService(session, studio_id)` — конструктор из плана 1; в рантайме `studio_id` берётся из `ctx`, НЕ хардкодится.

## Карта файлов

Создаётся:
- `src/bot/context.py` — `StudioContext`, `SettingsFacade`, `ProductsFacade`.
- `src/bot/middlewares/__init__.py`, `src/bot/middlewares/studio.py` — `StudioMiddleware`.
- `src/bot/registry.py` — `build_dispatcher(studio)`, `BASE_ROUTER_FACTORIES`, `STUDIO_ROUTER_FACTORIES`, `StudioBotRegistry`.
- `src/services/delivery_options.py` — studio-скоупленные helpers доставки (заменяют свойства enum `DeliveryType`).
- `tests/bot/__init__.py`, `tests/bot/conftest.py` — фейковые aiogram-объекты + фабрика `StudioContext` для тестов.
- тесты под каждую задачу.

Модифицируется:
- `src/services/pricing.py` — studio_id-first.
- `src/services/notification_service.py` — конструктор `(bot, studio, settings)`, manager_chat_id из `Studio`.
- `src/services/file_service.py` — пути `storage/{studio_id}/...`, studio_id в lookup продукта.
- `src/services/order_service.py` — `recalculate_order_cost` передаёт `self.studio_id` в Pricing.
- `src/models/order.py` — удалить свойства `DeliveryType.display_name/delivery_cost/is_enabled` (перенесены в `delivery_options.py`).
- `src/config.py` — `bot_token` опционален (токены — из Studio); пометить payment/manager поля как unused в рантайме.
- `src/bot/handlers/*.py` (7 файлов) — перевод на `ctx`.
- `main.py` — построение реестра студий, polling всех ботов.

---

### Task 1: Тестовая оснастка для хендлеров (фейковые aiogram-объекты)

**Files:**
- Create: `tests/bot/__init__.py`
- Create: `tests/bot/conftest.py`
- Test: `tests/bot/test_fakes.py`

**Interfaces:**
- Produces:
  - `FakeBot` — записывает вызовы `send_message`/`send_photo`/`send_document`/`edit_text` в список `.calls: list[dict]`; асинхронные методы.
  - `FakeMessage(text=None, from_user_id=1, chat_id=1, content_type=...)` — с async `.answer(text, **kw)` (пишет в `bot.calls`), атрибутами `.from_user`, `.chat`, `.photo`, `.document`, `.web_app_data`.
  - `FakeCallbackQuery(data, from_user_id=1, message=FakeMessage)` — с async `.answer()`, `.message`.
  - `make_state()` — реальный `FSMContext` поверх `MemoryStorage` (изолированный per-test).
  - `make_ctx(db_session, studio_id)` — строит реальный `StudioContext` (после Task 2 доступен; до этого фикстура помечается и реализуется в Task 2). На этом шаге — только фейки aiogram.

- [ ] **Step 1: Написать тест `tests/bot/test_fakes.py`**

```python
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
async def test_make_state_roundtrip():
    state = make_state()
    await state.update_data(order_id=5)
    data = await state.get_data()
    assert data["order_id"] == 5
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_fakes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.bot.conftest'` (или ImportError фейков).

- [ ] **Step 3: Создать `tests/bot/__init__.py`** (пустой) и `tests/bot/conftest.py`

```python
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
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_fakes.py -v`
Expected: PASS (3 теста).

- [ ] **Step 5: Commit**

```bash
git add tests/bot/
git commit -m "test: тестовая оснастка aiogram (FakeBot/FakeMessage/FakeCallbackQuery/make_state)"
```

---

### Task 2: StudioContext + фасады settings/products

**Files:**
- Create: `src/bot/context.py`
- Modify: `tests/bot/conftest.py` (добавить фикстуру `make_ctx`)
- Test: `tests/bot/test_context.py`

**Interfaces:**
- Consumes: `SettingsService` (studio_id-first), `ProductService` (studio_id-first), `OrderService(session, studio_id)`, `Studio` модель.
- Produces:
  - `SettingsFacade(studio_id)` с методами `get(key, default=None)`, `get_int(key, default=0)`, `get_float(key, default=0.0)`, `get_bool(key, default=False)` — делегируют в `SettingsService.<m>(self.studio_id, key, default)`.
  - `ProductsFacade(studio_id)` с методами `get(product_id)`, `top_level()`, `children(parent_id)`, `all_purchasable()` — делегируют в `ProductService.*`.
  - `StudioContext` (dataclass) с полями: `studio_id: int`, `studio: Studio`, `session: AsyncSession`, `orders: OrderService`, `settings: SettingsFacade`, `products: ProductsFacade`. Классметод/функция `build_studio_context(session, studio) -> StudioContext`.

- [ ] **Step 1: Написать тест `tests/bot/test_context.py`**

```python
"""Тесты StudioContext и фасадов."""
import os
import pytest
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.bot.context import build_studio_context, SettingsFacade, ProductsFacade
from src.services.settings_service import SettingKeys


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_context_facades_are_studio_scoped(db_session):
    s1 = await provision_studio(db_session, slug="s1", name="S1", bot_token="t1",
                                admin_username="a1", admin_password="p")
    s2 = await provision_studio(db_session, slug="s2", name="S2", bot_token="t2",
                                admin_username="a2", admin_password="p")
    # дефолтные настройки загружены провижинингом; различим их
    from src.services.settings_service import SettingsService
    await SettingsService(db_session).set_value(s1.id, SettingKeys.MIN_PHOTOS, "10")
    await SettingsService(db_session).set_value(s2.id, SettingKeys.MIN_PHOTOS, "3")
    await SettingsService(db_session).load_cache(s1.id)
    await SettingsService(db_session).load_cache(s2.id)

    ctx1 = build_studio_context(db_session, s1)
    ctx2 = build_studio_context(db_session, s2)

    assert ctx1.studio_id == s1.id
    assert ctx1.settings.get_int(SettingKeys.MIN_PHOTOS, 0) == 10
    assert ctx2.settings.get_int(SettingKeys.MIN_PHOTOS, 0) == 3
    assert ctx1.orders.studio_id == s1.id
    assert isinstance(ctx1.products, ProductsFacade)


@pytest.mark.asyncio
async def test_products_facade_top_level(db_session):
    s1 = await provision_studio(db_session, slug="s1", name="S1", bot_token="t1",
                                admin_username="a1", admin_password="p")
    from src.services.product_service import ProductService
    await ProductService(db_session).load_cache(s1.id)
    ctx = build_studio_context(db_session, s1)
    # CATALOG_TEMPLATE из провижининга даёт несколько товаров верхнего уровня
    assert len(ctx.products.top_level()) >= 1
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_context.py -v`
Expected: FAIL — нет модуля `src.bot.context`.

- [ ] **Step 3: Создать `src/bot/context.py`**

```python
"""Студия-скоупленный контекст для хендлеров бота."""
from dataclasses import dataclass
from typing import Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.studio import Studio
from src.models.product import Product
from src.services.order_service import OrderService
from src.services.settings_service import SettingsService
from src.services.product_service import ProductService


class SettingsFacade:
    """Студия-скоупленная обёртка над SettingsService (кеш в памяти)."""
    def __init__(self, studio_id: int):
        self.studio_id = studio_id

    def get(self, key: str, default: Any = None) -> Any:
        return SettingsService.get(self.studio_id, key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        return SettingsService.get_int(self.studio_id, key, default)

    def get_float(self, key: str, default: float = 0.0) -> float:
        return SettingsService.get_float(self.studio_id, key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        return SettingsService.get_bool(self.studio_id, key, default)


class ProductsFacade:
    """Студия-скоупленная обёртка над ProductService (кеш в памяти)."""
    def __init__(self, studio_id: int):
        self.studio_id = studio_id

    def get(self, product_id: int) -> Optional[Product]:
        return ProductService.get_product(self.studio_id, product_id)

    def top_level(self) -> List[Product]:
        return ProductService.get_top_level_products(self.studio_id)

    def children(self, parent_id: int) -> List[Product]:
        return ProductService.get_active_children(self.studio_id, parent_id)

    def all_purchasable(self) -> List[Product]:
        return ProductService.get_all_purchasable(self.studio_id)


@dataclass
class StudioContext:
    """Всё, что нужно хендлеру для работы в рамках одной студии."""
    studio_id: int
    studio: Studio
    session: AsyncSession
    orders: OrderService
    settings: SettingsFacade
    products: ProductsFacade


def build_studio_context(session: AsyncSession, studio: Studio) -> StudioContext:
    """Собирает StudioContext для заданной студии и сессии."""
    return StudioContext(
        studio_id=studio.id,
        studio=studio,
        session=session,
        orders=OrderService(session, studio.id),
        settings=SettingsFacade(studio.id),
        products=ProductsFacade(studio.id),
    )
```

- [ ] **Step 4: Добавить фикстуру `make_ctx` в `tests/bot/conftest.py`**

В конец файла добавить:

```python
async def make_ctx(db_session, studio):
    """Строит реальный StudioContext для тестов хендлеров."""
    from src.bot.context import build_studio_context
    from src.services.settings_service import SettingsService
    from src.services.product_service import ProductService
    await SettingsService(db_session).load_cache(studio.id)
    await ProductService(db_session).load_cache(studio.id)
    return build_studio_context(db_session, studio)
```

- [ ] **Step 5: Запустить — убедиться, что проходит**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_context.py -v`
Expected: PASS (2 теста).

- [ ] **Step 6: Commit**

```bash
git add src/bot/context.py tests/bot/
git commit -m "feat: StudioContext + фасады settings/products для хендлеров"
```

---

### Task 3: StudioMiddleware (инжекция ctx + сессии)

**Files:**
- Create: `src/bot/middlewares/__init__.py`
- Create: `src/bot/middlewares/studio.py`
- Test: `tests/bot/test_studio_middleware.py`

**Interfaces:**
- Consumes: `build_studio_context` (Task 2), `async_session` (src.database), `OrderService.get_or_create_user`.
- Produces: `StudioMiddleware(studio_id: int)` — aiogram `BaseMiddleware`. На каждый апдейт: открывает `async with async_session() as session`, грузит запись `Studio` по `studio_id`, строит `ctx = build_studio_context(session, studio)`, кладёт `data["ctx"] = ctx`, вызывает `await handler(event, data)`. Сессия закрывается по выходу из контекста. Если студия не найдена или `is_active=False` — обработчик не вызывается (апдейт игнорируется).

- [ ] **Step 1: Написать тест `tests/bot/test_studio_middleware.py`**

```python
"""Тесты StudioMiddleware."""
import os
import pytest
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.bot.middlewares.studio import StudioMiddleware
from tests.bot.conftest import FakeMessage


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_middleware_injects_ctx(db_session, monkeypatch):
    studio = await provision_studio(db_session, slug="s1", name="S1", bot_token="t1",
                                    admin_username="a1", admin_password="p")
    # Подменяем async_session, чтобы middleware использовал тестовую сессию
    import src.bot.middlewares.studio as mod

    class _SessionCtx:
        async def __aenter__(self): return db_session
        async def __aexit__(self, *a): return False
    monkeypatch.setattr(mod, "async_session", lambda: _SessionCtx())

    mw = StudioMiddleware(studio_id=studio.id)
    captured = {}

    async def handler(event, data):
        captured["ctx"] = data.get("ctx")
        return "ok"

    result = await mw(handler, FakeMessage(text="/start"), {})
    assert result == "ok"
    assert captured["ctx"].studio_id == studio.id
    assert captured["ctx"].studio.slug == "s1"


@pytest.mark.asyncio
async def test_middleware_skips_inactive_studio(db_session, monkeypatch):
    studio = await provision_studio(db_session, slug="s1", name="S1", bot_token="t1",
                                    admin_username="a1", admin_password="p")
    studio.is_active = False
    await db_session.commit()
    import src.bot.middlewares.studio as mod

    class _SessionCtx:
        async def __aenter__(self): return db_session
        async def __aexit__(self, *a): return False
    monkeypatch.setattr(mod, "async_session", lambda: _SessionCtx())

    mw = StudioMiddleware(studio_id=studio.id)
    called = {"n": 0}

    async def handler(event, data):
        called["n"] += 1

    await mw(handler, FakeMessage(text="/start"), {})
    assert called["n"] == 0  # хендлер не вызван для неактивной студии
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_studio_middleware.py -v`
Expected: FAIL — нет модуля `src.bot.middlewares.studio`.

- [ ] **Step 3: Создать `src/bot/middlewares/__init__.py`** (пустой) и `src/bot/middlewares/studio.py`

```python
"""Middleware, инжектирующий StudioContext в хендлеры."""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import select

from src.database import async_session
from src.models.studio import Studio
from src.bot.context import build_studio_context

logger = logging.getLogger(__name__)


class StudioMiddleware(BaseMiddleware):
    """Привязан к одной студии (свой Dispatcher на студию)."""

    def __init__(self, studio_id: int):
        self.studio_id = studio_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with async_session() as session:
            studio = (
                await session.execute(
                    select(Studio).where(Studio.id == self.studio_id)
                )
            ).scalar_one_or_none()

            if studio is None or not studio.is_active:
                logger.warning("Студия %s неактивна/не найдена — апдейт пропущен", self.studio_id)
                return None

            data["ctx"] = build_studio_context(session, studio)
            return await handler(event, data)
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_studio_middleware.py -v`
Expected: PASS (2 теста).

- [ ] **Step 5: Commit**

```bash
git add src/bot/middlewares/ tests/bot/test_studio_middleware.py
git commit -m "feat: StudioMiddleware — инжекция StudioContext по студии"
```

---

### Task 4: PricingService → studio_id-first

**Files:**
- Modify: `src/services/pricing.py`
- Modify: `src/services/order_service.py` (recalculate_order_cost)
- Test: `tests/services/test_pricing_tenancy.py`

**Interfaces:**
- Consumes: `ProductService.get_product(studio_id, product_id)`.
- Produces: classmethods PricingService теперь принимают `studio_id` первым аргументом:
  - `get_product(studio_id, product_id)`, `calculate_total_cost(studio_id, photos_by_product)`, `format_price_breakdown(studio_id, photos_by_product)`, `get_price_optimization_hint(studio_id, photos_by_product)`. `_calculate_tiered_cost(product, count)` без изменений (работает на объекте Product).
  - `OrderService.recalculate_order_cost` вызывает `PricingService.calculate_total_cost(self.studio_id, photos_by_product)`.

- [ ] **Step 1: Написать тест `tests/services/test_pricing_tenancy.py`**

```python
"""Тесты studio-скоупленного PricingService."""
import pytest
from src.models.studio import Studio
from src.models.product import Product
from src.services.product_service import ProductService
from src.services.pricing import PricingService


@pytest.mark.asyncio
async def test_pricing_uses_studio_catalog(db_session):
    ProductService.invalidate_cache()
    s1 = Studio(slug="s1", name="S1"); s2 = Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2]); await db_session.commit()
    p1 = Product(studio_id=s1.id, slug="x", name="X", short_name="X",
                 price_per_unit=25, price_type="per_unit", is_active=True)
    p2 = Product(studio_id=s2.id, slug="x", name="X", short_name="X",
                 price_per_unit=40, price_type="per_unit", is_active=True)
    db_session.add_all([p1, p2]); await db_session.commit()
    await ProductService(db_session).load_cache(s1.id)
    await ProductService(db_session).load_cache(s2.id)

    assert PricingService.calculate_total_cost(s1.id, {p1.id: 10}) == 250
    assert PricingService.calculate_total_cost(s2.id, {p2.id: 10}) == 400
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/services/test_pricing_tenancy.py -v`
Expected: FAIL — `calculate_total_cost()` принимает 1 позиционный аргумент, не studio_id.

- [ ] **Step 3: Переписать `src/services/pricing.py`**

Заменить методы (сохранить логику тиров, добавить `studio_id` первым параметром и прокинуть в `get_product`):

```python
"""Сервис расчёта стоимости (studio-скоупленный)."""
from typing import Dict, List, Optional

from src.models.product import Product


class PricingService:
    """Расчёт стоимости заказа на каталоге конкретной студии."""

    @classmethod
    def get_product(cls, studio_id: int, product_id: int) -> Optional[Product]:
        from src.services.product_service import ProductService
        return ProductService.get_product(studio_id, product_id)

    @classmethod
    def calculate_total_cost(cls, studio_id: int, photos_by_product: Dict[int, int]) -> int:
        if not photos_by_product:
            return 0
        total = 0
        group_counts: Dict[str, int] = {}
        group_products: Dict[str, List[int]] = {}
        for product_id, count in photos_by_product.items():
            product = cls.get_product(studio_id, product_id)
            if not product:
                continue
            if product.price_type in ("fixed", "per_unit"):
                if product.pricing_group:
                    g = product.pricing_group
                    group_counts[g] = group_counts.get(g, 0) + count
                    group_products.setdefault(g, []).append(product_id)
                else:
                    total += product.price_per_unit * count
            elif product.price_type == "tiered":
                if product.pricing_group:
                    g = product.pricing_group
                    group_counts[g] = group_counts.get(g, 0) + count
                    group_products.setdefault(g, []).append(product_id)
                else:
                    total += cls._calculate_tiered_cost(product, count)
        for g, total_count in group_counts.items():
            if group_products[g]:
                product = cls.get_product(studio_id, group_products[g][0])
                if product:
                    total += cls._calculate_tiered_cost(product, total_count)
        return total

    @classmethod
    def _calculate_tiered_cost(cls, product: Product, count: int) -> int:
        if count <= 0:
            return 0
        tiers = product.get_price_tiers()
        if not tiers:
            return product.price_per_unit * count
        sorted_tiers = sorted(tiers, key=lambda t: t.get("min_qty", 0), reverse=True)
        for tier in sorted_tiers:
            if count >= tier.get("min_qty", 0):
                return tier.get("price", product.price_per_unit) * count
        return product.price_per_unit * count

    @classmethod
    def format_price_breakdown(cls, studio_id: int, photos_by_product: Dict[int, int]) -> List[str]:
        lines = []
        group_counts: Dict[str, int] = {}
        group_names: Dict[str, str] = {}
        for product_id, count in photos_by_product.items():
            product = cls.get_product(studio_id, product_id)
            if not product:
                continue
            if product.pricing_group:
                g = product.pricing_group
                group_counts[g] = group_counts.get(g, 0) + count
                group_names.setdefault(g, product.pricing_group.capitalize())
                lines.append(f"• {product.short_name}: {count} шт.")
            else:
                cost = product.price_per_unit * count
                lines.append(f"• {product.short_name}: {count} шт. × {product.price_per_unit}₽ = {cost}₽")
        for g, total_count in group_counts.items():
            for pid, cnt in photos_by_product.items():
                p = cls.get_product(studio_id, pid)
                if p and p.pricing_group == g:
                    cost = cls._calculate_tiered_cost(p, total_count)
                    lines.append(f"  └ Итого ({total_count} шт.): {cost}₽")
                    break
        return lines

    @classmethod
    def get_price_optimization_hint(cls, studio_id: int, photos_by_product: Dict[int, int]) -> Optional[str]:
        group_totals: Dict[str, int] = {}
        group_example: Dict[str, Product] = {}
        for product_id, count in photos_by_product.items():
            product = cls.get_product(studio_id, product_id)
            if not product:
                continue
            key = product.pricing_group or f"individual_{product_id}"
            group_totals[key] = group_totals.get(key, 0) + count
            group_example.setdefault(key, product)
        for key, total_count in group_totals.items():
            product = group_example.get(key)
            if not product:
                continue
            tiers = product.get_price_tiers()
            if not tiers:
                continue
            for tier in sorted(tiers, key=lambda t: t.get("min_qty", 0)):
                min_qty = tier.get("min_qty", 0)
                tier_price = tier.get("price", 0)
                if total_count < min_qty and (min_qty - total_count) <= 10:
                    current_cost = product.price_per_unit * total_count
                    optimal_cost = tier_price * min_qty
                    if optimal_cost <= current_cost + 200:
                        return (
                            f"💡 Если заказать {min_qty} шт вместо {total_count} — "
                            f"цена за штуку станет {tier_price}₽!"
                        )
        return None
```

- [ ] **Step 4: Обновить `OrderService.recalculate_order_cost`** (`src/services/order_service.py`)

Заменить тело:
```python
    async def recalculate_order_cost(self, order: Order) -> Order:
        """Пересчитывает стоимость заказа."""
        photos_by_product = order.photos_by_product()
        order.photos_cost = PricingService.calculate_total_cost(self.studio_id, photos_by_product)
        await self.session.commit()
        await self.session.refresh(order)
        return order
```

- [ ] **Step 5: Запустить тест + полный сервисный набор**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/services/test_pricing_tenancy.py tests/services/test_order_service_tenancy.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/pricing.py src/services/order_service.py tests/services/test_pricing_tenancy.py
git commit -m "feat: studio-скоупленный PricingService + recalculate_order_cost"
```

---

### Task 5: Delivery options helper (замена свойств enum DeliveryType)

**Files:**
- Create: `src/services/delivery_options.py`
- Modify: `src/models/order.py` (удалить свойства `display_name`/`delivery_cost`/`is_enabled` у `DeliveryType`)
- Test: `tests/services/test_delivery_options.py`

**Interfaces:**
- Consumes: `SettingsFacade` (Task 2), `DeliveryType`, `SettingKeys`.
- Produces (модуль `delivery_options.py`), все принимают `settings: SettingsFacade`:
  - `delivery_display_name(settings, dt: DeliveryType) -> str`
  - `delivery_cost(settings, dt: DeliveryType) -> int`
  - `delivery_is_enabled(settings, dt: DeliveryType) -> bool`
- `DeliveryType` остаётся простым enum со значениями (OZON/COURIER/PICKUP); свойства, читавшие глобальный SettingsService, удалены.
- ВНИМАНИЕ: `OrderService.set_delivery_info` (план 1) использует `delivery_type.delivery_cost` — заменить на `delivery_cost(SettingsFacade(self.studio_id), delivery_type)`.

- [ ] **Step 1: Написать тест `tests/services/test_delivery_options.py`**

```python
"""Тесты studio-скоупленных опций доставки."""
import pytest
from src.models.studio import Studio
from src.models.setting import Setting, SettingType
from src.models.order import DeliveryType
from src.services.settings_service import SettingsService, SettingKeys
from src.bot.context import SettingsFacade
from src.services.delivery_options import (
    delivery_display_name, delivery_cost, delivery_is_enabled,
)


@pytest.mark.asyncio
async def test_delivery_helpers_read_studio_settings(db_session):
    SettingsService.invalidate_cache()
    s = Studio(slug="s1", name="S1"); db_session.add(s); await db_session.commit()
    db_session.add_all([
        Setting(studio_id=s.id, key=SettingKeys.DELIVERY_OZON_NAME, value="ОЗОН X"),
        Setting(studio_id=s.id, key=SettingKeys.DELIVERY_OZON_PRICE, value="150", value_type=SettingType.INTEGER),
        Setting(studio_id=s.id, key=SettingKeys.DELIVERY_OZON_ENABLED, value="true", value_type=SettingType.BOOLEAN),
    ])
    await db_session.commit()
    await SettingsService(db_session).load_cache(s.id)

    facade = SettingsFacade(s.id)
    assert delivery_display_name(facade, DeliveryType.OZON) == "ОЗОН X"
    assert delivery_cost(facade, DeliveryType.OZON) == 150
    assert delivery_is_enabled(facade, DeliveryType.OZON) is True
    assert delivery_cost(facade, DeliveryType.PICKUP) == 0
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/services/test_delivery_options.py -v`
Expected: FAIL — нет модуля `src.services.delivery_options`.

- [ ] **Step 3: Создать `src/services/delivery_options.py`**

```python
"""Студия-скоупленные опции доставки (заменяют свойства enum DeliveryType)."""
from src.models.order import DeliveryType
from src.services.settings_service import SettingKeys

_NAME_KEYS = {
    DeliveryType.OZON: SettingKeys.DELIVERY_OZON_NAME,
    DeliveryType.COURIER: SettingKeys.DELIVERY_COURIER_NAME,
    DeliveryType.PICKUP: SettingKeys.DELIVERY_PICKUP_NAME,
}
_DEFAULT_NAMES = {
    DeliveryType.OZON: "ОЗОН доставка",
    DeliveryType.COURIER: "Курьер",
    DeliveryType.PICKUP: "Самовывоз",
}
_PRICE_KEYS = {
    DeliveryType.OZON: SettingKeys.DELIVERY_OZON_PRICE,
    DeliveryType.COURIER: SettingKeys.DELIVERY_COURIER_PRICE,
}
_ENABLED_KEYS = {
    DeliveryType.OZON: SettingKeys.DELIVERY_OZON_ENABLED,
    DeliveryType.COURIER: SettingKeys.DELIVERY_COURIER_ENABLED,
    DeliveryType.PICKUP: SettingKeys.DELIVERY_PICKUP_ENABLED,
}


def delivery_display_name(settings, dt: DeliveryType) -> str:
    return settings.get(_NAME_KEYS[dt], _DEFAULT_NAMES[dt])


def delivery_cost(settings, dt: DeliveryType) -> int:
    if dt == DeliveryType.PICKUP:
        return 0
    return settings.get_int(_PRICE_KEYS[dt], 0)


def delivery_is_enabled(settings, dt: DeliveryType) -> bool:
    return settings.get_bool(_ENABLED_KEYS[dt], True)
```

- [ ] **Step 4: Удалить свойства из `DeliveryType` в `src/models/order.py`**

Удалить методы-свойства `display_name`, `delivery_cost`, `is_enabled` (строки 50-81 в текущем файле), оставив только enum-значения OZON/COURIER/PICKUP и (опционально) docstring:

```python
class DeliveryType(str, Enum):
    """Способы доставки."""
    OZON = "ozon"
    COURIER = "courier"
    PICKUP = "pickup"
```

Удалить теперь неиспользуемый `from src.services.settings_service import ...` внутри этих свойств (он был локальным импортом — просто исчезнет вместе с методами).

- [ ] **Step 5: Обновить `OrderService.set_delivery_info`** (`src/services/order_service.py`)

Заменить строку `order.delivery_cost = delivery_type.delivery_cost` на:
```python
        from src.bot.context import SettingsFacade
        from src.services.delivery_options import delivery_cost as _delivery_cost
        order.delivery_cost = _delivery_cost(SettingsFacade(self.studio_id), delivery_type)
```

- [ ] **Step 6: Запустить тесты**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/services/test_delivery_options.py tests/services/test_order_service_tenancy.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/services/delivery_options.py src/models/order.py src/services/order_service.py tests/services/test_delivery_options.py
git commit -m "refactor: studio-скоупленные опции доставки вместо свойств enum DeliveryType"
```

---

### Task 6: NotificationService → studio-aware

**Files:**
- Modify: `src/services/notification_service.py`
- Test: `tests/services/test_notification_service.py`

**Interfaces:**
- Consumes: `Studio` (manager_chat_id, manager_username), `SettingsFacade`, `ProductsFacade`, `delivery_display_name`.
- Produces: `NotificationService(bot, studio, settings, products)`:
  - `_get_manager_chat_id()` берёт `int(self.studio.manager_chat_id)` (а не из глобальных настроек); `None`, если не задан/невалиден.
  - `notify_new_order`, `notify_receipt_uploaded`, `notify_order_status_changed`, `notify_client_status_changed` используют `self.products.get(...)`, `delivery_display_name(self.settings, ...)`, и `self.studio.manager_username` для контактов.

- [ ] **Step 1: Написать тест `tests/services/test_notification_service.py`**

```python
"""Тесты studio-aware NotificationService."""
import pytest
from src.models.studio import Studio
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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/services/test_notification_service.py -v`
Expected: FAIL — конструктор `NotificationService(bot)` не принимает studio.

- [ ] **Step 3: Переписать `src/services/notification_service.py`**

Ключевые изменения: конструктор и `_get_manager_chat_id`, замена `ProductService.get_product(id)` → `self.products.get(id)`, `order.delivery_type.display_name` → `delivery_display_name(self.settings, order.delivery_type)`, `SettingsService.get(MANAGER_USERNAME)` → `self.studio.manager_username`. Полный файл:

```python
"""Сервис уведомлений для менеджеров (studio-aware)."""
import logging
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.models.order import Order, OrderStatus, DeliveryType
from src.models.studio import Studio
from src.services.delivery_options import delivery_display_name
from src.config import settings as app_settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Уведомления менеджерам/клиенту в рамках одной студии."""

    def __init__(self, bot: Bot, studio: Studio, settings, products):
        self.bot = bot
        self.studio = studio
        self.settings = settings
        self.products = products

    def _get_order_keyboard(self, order_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="✅ Подтвердить оплату",
                                         callback_data=f"mgr_confirm:{order_id}"))
        admin_url = getattr(app_settings, "admin_url", None)
        if admin_url:
            builder.row(InlineKeyboardButton(text="📋 Открыть в админке",
                                             url=f"{admin_url}/orders/{order_id}"))
        return builder.as_markup()

    def _get_manager_chat_id(self) -> Optional[int]:
        chat_id_str = self.studio.manager_chat_id
        if not chat_id_str:
            return None
        try:
            return int(chat_id_str)
        except (ValueError, TypeError):
            logger.error("Неверный manager_chat_id студии %s: %r", self.studio.id, chat_id_str)
            return None

    async def notify_new_order(self, order: Order) -> bool:
        chat_id = self._get_manager_chat_id()
        if not chat_id:
            logger.warning("manager_chat_id не настроен для студии %s", self.studio.id)
            return False
        photos_lines = []
        for product_id, count in order.photos_by_product().items():
            product = self.products.get(product_id)
            name = product.short_name if product else f"Товар #{product_id}"
            photos_lines.append(f"  • {name}: {count} шт.")
        client = f"@{order.user.username}" if order.user.username else (order.user.first_name or "Клиент")
        delivery_info = ""
        if order.delivery_type:
            delivery_info = f"\n\n🚚 <b>Доставка:</b> {delivery_display_name(self.settings, order.delivery_type)}"
            if order.delivery_address:
                delivery_info += f"\n📍 {order.delivery_address}"
        message = (
            f"🆕 <b>Новый заказ #{order.order_number}</b>\n\n"
            f"👤 Клиент: {client}\n📷 Фото:\n" + "\n".join(photos_lines) +
            f"\n\n💰 <b>Сумма: {order.total_cost}₽</b>{delivery_info}"
        )
        try:
            await self.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            return True
        except Exception as e:
            logger.error("Ошибка отправки уведомления: %s", e)
            return False

    async def notify_receipt_uploaded(self, order: Order, receipt_file_id: str) -> bool:
        chat_id = self._get_manager_chat_id()
        if not chat_id:
            return False
        client = f"@{order.user.username}" if order.user.username else (order.user.first_name or "Клиент")
        delivery_info = ""
        if order.delivery_type:
            delivery_info = f"\n🚚 {delivery_display_name(self.settings, order.delivery_type)}"
            if order.delivery_address:
                delivery_info += f"\n📍 {order.delivery_address}"
        caption = (
            f"🧾 <b>Новый заказ #{order.order_number}</b>\n\n"
            f"👤 Клиент: {client}\n📷 Фото: {order.photos_count} шт.\n"
            f"💰 Сумма: {order.total_cost}₽{delivery_info}"
        )
        try:
            await self.bot.send_photo(chat_id=chat_id, photo=receipt_file_id, caption=caption,
                                      parse_mode="HTML", reply_markup=self._get_order_keyboard(order.id))
            return True
        except Exception as e:
            logger.error("Ошибка отправки квитанции: %s", e)
            return False

    async def notify_order_status_changed(self, order: Order, old_status: str, new_status: str) -> bool:
        chat_id = self._get_manager_chat_id()
        if not chat_id:
            return False
        message = (f"🔄 <b>Статус заказа изменён</b>\n\n📦 Заказ: #{order.order_number}\n"
                   f"📊 {old_status} → <b>{new_status}</b>")
        try:
            await self.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            return True
        except Exception as e:
            logger.error("Ошибка отправки уведомления о статусе: %s", e)
            return False

    async def notify_client_status_changed(self, order: Order, new_status: str) -> bool:
        manager = self.studio.manager_username or "manager"
        status_messages = {
            OrderStatus.CONFIRMED.value: (
                f"✅ <b>Заказ #{order.order_number} подтверждён!</b>\n\n"
                "Мы начинаем работу над вашим заказом."),
            OrderStatus.PRINTING.value: (
                f"🖨 <b>Заказ #{order.order_number} в печати!</b>\n\nСкоро будут готовы!"),
            OrderStatus.READY.value: (
                f"📦 <b>Заказ #{order.order_number} готов!</b>\n\n"
                "Фотографии распечатаны и готовы к отправке."),
            OrderStatus.SHIPPED.value: self._get_shipped_message(order),
            OrderStatus.DELIVERED.value: (
                f"🎉 <b>Заказ #{order.order_number} доставлен!</b>\n\nСпасибо за заказ! 📸"),
            OrderStatus.CANCELLED.value: (
                f"❌ <b>Заказ #{order.order_number} отменён</b>\n\n"
                f"Если есть вопросы, свяжитесь с менеджером: @{manager}"),
        }
        message = status_messages.get(new_status)
        if not message:
            return False
        try:
            await self.bot.send_message(chat_id=order.user.telegram_id, text=message, parse_mode="HTML")
            return True
        except Exception as e:
            logger.error("Ошибка уведомления клиента: %s", e)
            return False

    def _get_shipped_message(self, order: Order) -> str:
        base = f"🚚 <b>Заказ #{order.order_number} отправлен!</b>\n\n"
        if order.delivery_type == DeliveryType.OZON:
            return base + "Посылка передана в службу ОЗОН. Отслеживайте в приложении ОЗОН."
        if order.delivery_type == DeliveryType.COURIER:
            return base + "Курьер свяжется с вами в указанное время."
        if order.delivery_type == DeliveryType.PICKUP:
            return base + "Заказ готов к самовывозу."
        return base + "Скоро вы получите свой заказ!"
```

- [ ] **Step 4: Запустить тест**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/services/test_notification_service.py -v`
Expected: PASS (2 теста).

- [ ] **Step 5: Commit**

```bash
git add src/services/notification_service.py tests/services/test_notification_service.py
git commit -m "feat: studio-aware NotificationService (manager_chat_id из Studio)"
```

---

### Task 7: FileService → пути storage/{studio_id}/...

**Files:**
- Modify: `src/services/file_service.py`
- Test: `tests/services/test_file_service.py`

**Interfaces:**
- Consumes: `Order.studio_id`, `ProductService.get_product(studio_id, product_id)`.
- Produces: `FileService.get_order_dir(order)` возвращает `self.photos_dir / str(order.studio_id) / order.order_number`; `delete_order_photos` использует тот же путь; имя файла берёт продукт через `ProductService.get_product(order.studio_id, photo.product_id)`. Конструктор `FileService(bot_token)` без изменений (токен теперь — токен бота студии, передаётся вызывающим).

- [ ] **Step 1: Написать тест `tests/services/test_file_service.py`**

```python
"""Тесты путей хранилища с studio_id."""
from pathlib import Path
from types import SimpleNamespace
from src.services.file_service import FileService


def test_order_dir_includes_studio_id(tmp_path, monkeypatch):
    from src.services import file_service as mod
    monkeypatch.setattr(mod.settings, "photos_dir", tmp_path / "photos")
    monkeypatch.setattr(mod.settings, "temp_dir", tmp_path / "temp")
    fs = FileService(bot_token="x")
    order = SimpleNamespace(studio_id=7, order_number="240101-AAAA")
    d = fs.get_order_dir(order)
    assert d == (tmp_path / "photos" / "7" / "240101-AAAA")
    assert d.exists()
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/services/test_file_service.py -v`
Expected: FAIL — путь без `studio_id` (`.../photos/240101-AAAA`).

- [ ] **Step 3: Изменить `src/services/file_service.py`**

`get_order_dir`:
```python
    def get_order_dir(self, order: Order) -> Path:
        """Директория фото заказа: storage/{studio_id}/{order_number}/."""
        order_dir = self.photos_dir / str(order.studio_id) / order.order_number
        order_dir.mkdir(parents=True, exist_ok=True)
        return order_dir
```
`delete_order_photos`:
```python
    def delete_order_photos(self, order: Order) -> None:
        order_dir = self.photos_dir / str(order.studio_id) / order.order_number
        if order_dir.exists():
            import shutil
            shutil.rmtree(order_dir)
```
В `download_photo_from_telegram` заменить lookup продукта:
```python
        from src.services.product_service import ProductService
        product = ProductService.get_product(order.studio_id, photo.product_id)
```

- [ ] **Step 4: Запустить тест**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/services/test_file_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/file_service.py tests/services/test_file_service.py
git commit -m "feat: пути хранилища storage/{studio_id}/{order_number}"
```

---

### Task 8: Реестр студий и сборка Dispatcher на студию

**Files:**
- Create: `src/bot/registry.py`
- Test: `tests/bot/test_registry.py`

**Interfaces:**
- Consumes: `StudioMiddleware` (Task 3), существующие роутеры (`src/bot/handlers/*` через `setup_routers`), `Studio`, `decrypt_secret`.
- Produces:
  - `BASE_ROUTER_FACTORIES: list[Callable[[], Router]]` — фабрики базовых роутеров (по одной на каждый handlers-модуль: start, order, delivery, payment, my_orders, manager, crop). Каждая возвращает `router` соответствующего модуля.
  - `STUDIO_ROUTER_FACTORIES: dict[str, list[Callable[[], Router]]]` — опциональные доп-роутеры по `studio.slug` (по умолчанию пусто).
  - `build_dispatcher(studio: Studio) -> Dispatcher` — создаёт `Dispatcher(storage=MemoryStorage())`, включает базовые роутеры + роутеры студии, навешивает `StudioMiddleware(studio.id)` на `message` и `callback_query` обсерверы.
  - `build_bot(studio: Studio) -> Bot` — `Bot(token=decrypt_secret(studio.bot_token), default=DefaultBotProperties(parse_mode=MARKDOWN))`.

- [ ] **Step 1: Написать тест `tests/bot/test_registry.py`**

```python
"""Тесты сборки Dispatcher на студию."""
import os
import pytest
from cryptography.fernet import Fernet
from aiogram import Dispatcher

from src.services.studio_provisioning import provision_studio
from src.bot.registry import build_dispatcher, STUDIO_ROUTER_FACTORIES, BASE_ROUTER_FACTORIES


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_build_dispatcher_has_studio_middleware(db_session):
    studio = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                                    admin_username="a", admin_password="p")
    dp = build_dispatcher(studio)
    assert isinstance(dp, Dispatcher)
    # StudioMiddleware навешан на message-обсервер
    from src.bot.middlewares.studio import StudioMiddleware
    assert any(isinstance(m, StudioMiddleware) for m in dp.message.outer_middleware)


def test_base_router_factories_nonempty():
    assert len(BASE_ROUTER_FACTORIES) >= 7


@pytest.mark.asyncio
async def test_studio_specific_routers_included(db_session, monkeypatch):
    from aiogram import Router
    marker = Router(name="custom_marker")
    monkeypatch.setitem(STUDIO_ROUTER_FACTORIES, "s1", [lambda: marker])
    studio = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                                    admin_username="a", admin_password="p")
    dp = build_dispatcher(studio)
    # роутер студии включён в дерево
    assert any(r.name == "custom_marker" for r in dp.sub_routers)
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_registry.py -v`
Expected: FAIL — нет модуля `src.bot.registry`.

- [ ] **Step 3: Создать `src/bot/registry.py`**

```python
"""Реестр студий: сборка Bot и Dispatcher на студию с композицией роутеров."""
from typing import Callable, Dict, List

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.models.studio import Studio
from src.services.crypto import decrypt_secret
from src.bot.middlewares.studio import StudioMiddleware

from src.bot.handlers.start import router as start_router
from src.bot.handlers.order import router as order_router
from src.bot.handlers.delivery import router as delivery_router
from src.bot.handlers.payment import router as payment_router
from src.bot.handlers.my_orders import router as my_orders_router
from src.bot.handlers.manager import router as manager_router
from src.bot.handlers.crop import router as crop_router

# Базовые роутеры — одинаковы для всех студий.
BASE_ROUTER_FACTORIES: List[Callable[[], Router]] = [
    lambda: start_router,
    lambda: order_router,
    lambda: delivery_router,
    lambda: payment_router,
    lambda: my_orders_router,
    lambda: manager_router,
    lambda: crop_router,
]

# Доп-роутеры под конкретные студии (ключ — slug). Кастомный экран для студии =
# добавить сюда фабрику её роутера. По умолчанию пусто.
STUDIO_ROUTER_FACTORIES: Dict[str, List[Callable[[], Router]]] = {}


def build_dispatcher(studio: Studio) -> Dispatcher:
    """Собирает Dispatcher для студии: базовые роутеры + её доп-роутеры + middleware."""
    dp = Dispatcher(storage=MemoryStorage())
    root = Router(name=f"studio_{studio.slug}")
    for factory in BASE_ROUTER_FACTORIES:
        root.include_router(factory())
    for factory in STUDIO_ROUTER_FACTORIES.get(studio.slug, []):
        root.include_router(factory())
    dp.include_router(root)
    mw = StudioMiddleware(studio.id)
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)
    return dp


def build_bot(studio: Studio) -> Bot:
    """Создаёт Bot с расшифрованным токеном студии."""
    return Bot(
        token=decrypt_secret(studio.bot_token),
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
```

> Примечание: роутеры aiogram нельзя включать в несколько Dispatcher одновременно (router имеет один parent). Поскольку каждый модульный `router` — singleton, при нескольких студиях повторное `include_router(start_router)` бросит ошибку «router is already attached». Поэтому фабрики на этом шаге возвращают singleton — это корректно для ОДНОЙ студии (текущее состояние). Поддержка нескольких студий одновременно требует, чтобы фабрики СОЗДАВАЛИ новые роутеры на каждый вызов; это вводится в Task 9 (превращение `router = Router()` модулей в функции `build_*_router()`), но интерфейс `BASE_ROUTER_FACTORIES` уже готов к этому. Тест этой задачи использует одну студию.

- [ ] **Step 4: Запустить тест**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_registry.py -v`
Expected: PASS (3 теста).

- [ ] **Step 5: Commit**

```bash
git add src/bot/registry.py tests/bot/test_registry.py
git commit -m "feat: реестр студий + build_dispatcher с композицией роутеров"
```

---

### Task 9: Хендлеры → ctx (миграция всех 7 модулей)

> Это самая объёмная задача. Каждый handlers-модуль переводится на инжектируемый `ctx: StudioContext`. Трансформация ЕДИНООБРАЗНА — ниже её контракт и worked-пример на `start.py`. Реализатору: применять контракт к каждому файлу, сверяясь с уже прочитанным кодом, и писать юнит-тест на 1-2 ключевых хендлера каждого файла на фейках из `tests/bot/conftest.py`.

**Files:**
- Modify: `src/bot/handlers/start.py`, `order.py`, `delivery.py`, `payment.py`, `my_orders.py`, `manager.py`, `crop.py`
- Modify: `src/bot/handlers/__init__.py` — превратить модульные `router = Router()` в фабрики `build_*_router()` НЕ требуется для одной студии; оставить как есть (singleton). (Мультистудийная развязка роутеров — отдельная задача плана 2b, где появляется webhook и реальная множественность.)
- Test: `tests/bot/test_handlers_*.py` (по файлу на модуль)

**Interfaces:**
- Consumes: `StudioContext` (`ctx.orders`, `ctx.settings`, `ctx.products`, `ctx.studio`, `ctx.studio_id`), `delivery_options.*`, `PricingService.<m>(ctx.studio_id, ...)`, `NotificationService(bot, ctx.studio, ctx.settings, ctx.products)`.

**Контракт трансформации (применять ко всем модулям):**
1. Каждый хендлер добавляет параметр `ctx: StudioContext` (aiogram инжектит из `data["ctx"]`). Пример: `async def cmd_start(message, state, ctx)`.
2. Убрать `async with async_session() as session: service = OrderService(session)` → использовать `ctx.orders` напрямую (сессия уже открыта middleware и общая на апдейт). Множественные `async with` в одном хендлере схлопываются в работу через `ctx.orders`.
3. `SettingsService.get(KEY, d)` / `get_int` / `get_bool` → `ctx.settings.get(KEY, d)` / `get_int` / `get_bool`.
4. `ProductService.get_product(id)` → `ctx.products.get(id)`; `get_top_level_products()` → `ctx.products.top_level()`; `get_active_children(pid)` → `ctx.products.children(pid)`.
5. `PricingService.calculate_total_cost(pbp)` → `PricingService.calculate_total_cost(ctx.studio_id, pbp)` (и `get_price_optimization_hint`, `format_price_breakdown` аналогично).
6. `NotificationService(bot)` → `NotificationService(bot, ctx.studio, ctx.settings, ctx.products)`.
7. `order.delivery_type.display_name` → `delivery_display_name(ctx.settings, order.delivery_type)` (импорт из `src.services.delivery_options`); аналогично для `delivery_cost`/`is_enabled` в `get_delivery_message`.
8. Модульные хелперы (`get_welcome_message`, `get_min_photos`, `get_delivery_message`, `analyze_photos_for_crop`, `show_order_summary`, `show_order_summary_new`, `_get_photo_caption`, `_send_photo_preview`, `format_payment_summary`, `check_channel_subscription`) получают `ctx` параметром и используют `ctx.*` вместо глобальных сервисов. Вызовы этих хелперов передают `ctx`.
9. Контакт менеджера `SettingsService.get(MANAGER_USERNAME)` → `ctx.studio.manager_username or "manager"`. Реквизиты оплаты в `payment.py` (`PAYMENT_PHONE/CARD/RECEIVER`) → `ctx.studio.payment_phone/payment_card/payment_receiver`.
10. Фоновые `asyncio.create_task(_send_*_confirmation(bot, ...))` в `order.py`: эти задачи живут вне апдейта (сессия middleware уже закрыта). Они должны открыть СВОЮ сессию и построить временный `OrderService(session, ctx.studio_id)` — передавать в них `studio_id`, а не `ctx`. См. worked-пример ниже.

**Worked-пример (start.py — `get_welcome_message` и `cmd_start`):**

```python
# было: def get_welcome_message() -> str: ... SettingsService.get(...) / ProductService...
def get_welcome_message(ctx) -> str:
    manager = ctx.studio.manager_username or "manager"
    products = ctx.products.top_level()
    format_lines = []
    for p in products:
        children = ctx.products.children(p.id)
        if children:
            variants = ", ".join(c.name.lower() for c in children)
            format_lines.append(f"• {p.emoji} {p.name} ({variants})")
        else:
            format_lines.append(f"• {p.emoji} {p.name}")
    formats_text = "\n".join(format_lines) if format_lines else "• Форматы загружаются..."
    template = ctx.settings.get(SettingKeys.WELCOME_MESSAGE, "")
    if template:
        try:
            return template.replace("{formats}", formats_text).replace("{manager}", manager)
        except Exception:
            pass
    return (f"Здравствуйте! 👋\n\nЯ бот приёма заказов <b>{ctx.studio.name}</b>!\n\n"
            f"Какой формат фотографий вы хотите напечатать?\n\n"
            f"📷 <b>Форматы:</b>\n{formats_text}\n\nДля связи с менеджером: @{manager}")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, ctx):
    await state.clear()
    user = await ctx.orders.get_or_create_user(
        telegram_id=message.from_user.id, username=message.from_user.username,
        first_name=message.from_user.first_name, last_name=message.from_user.last_name)
    draft_order = await ctx.orders.get_user_draft_order(user)
    if draft_order and draft_order.photos_count > 0:
        await message.answer(CONTINUE_ORDER_MESSAGE.format(photos_count=draft_order.photos_count),
                             reply_markup=get_continue_keyboard(draft_order.id), parse_mode="HTML")
        return
    order = await ctx.orders.create_order(user)
    await state.update_data(order_id=order.id, user_id=user.id)
    await message.answer(get_welcome_message(ctx), reply_markup=get_format_keyboard(), parse_mode="HTML")
    await state.set_state(OrderStates.selecting_format)
```

**Worked-пример (order.py — фоновая задача с собственной сессией):**

```python
async def _send_single_photo_confirmation(bot, user_id: int, order_id: int, studio_id: int):
    await asyncio.sleep(0.3)
    single_info = _single_photo_tasks.pop(user_id, None)
    if not single_info:
        return
    added_count = single_info.get("count", 1)
    async with async_session() as session:        # своя сессия — апдейт уже завершён
        service = OrderService(session, studio_id)
        order = await service.get_order_by_id(order_id)
        if not order:
            return
        photos_count = order.photos_count
    ...
# вызов: asyncio.create_task(_send_single_photo_confirmation(bot, user_id, order_id, ctx.studio_id))
```

**Шаги (повторить цикл RED→GREEN для КАЖДОГО из 7 модулей):**

- [ ] **Step 1 (start.py): тест** `tests/bot/test_handlers_start.py`

```python
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
```

- [ ] **Step 2 (start.py): RED**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_handlers_start.py -v`
Expected: FAIL — `cmd_start()` пока не принимает `ctx` / падает на старых вызовах.

- [ ] **Step 3 (start.py): применить контракт трансформации** ко всему `start.py` (все хендлеры `cmd_start`, `continue_order`, `new_order`, `cmd_cancel`, `cmd_help`, хелпер `get_welcome_message`), по worked-примеру. `cmd_chatid` не использует сервисы — добавить только `ctx` если нужно единообразие (можно без). Сохранить `async_session`/`OrderService` импорты только если остаются фоновые задачи (в start.py их нет — убрать неиспользуемые импорты).

- [ ] **Step 4 (start.py): GREEN**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_handlers_start.py -v`
Expected: PASS.

- [ ] **Step 5: повторить Step 1-4 для каждого модуля** с такими тестами-якорями (минимум один хендлер на файл):
  - `order.py` → `tests/bot/test_handlers_order.py`: `select_format_category` показывает варианты из `ctx.products.children`; `finish_photos` при < min_photos отвечает алертом (мокнуть `ctx.settings` MIN_PHOTOS). Проверить фоновые задачи получают `studio_id`.
  - `delivery.py` → `test_handlers_delivery.py`: `get_delivery_message(ctx)` содержит включённые способы из `ctx.settings`; `select_delivery` редактирует сообщение.
  - `payment.py` → `test_handlers_payment.py`: `skip_promocode` показывает реквизиты из `ctx.studio.payment_*` и ставит статус PENDING_PAYMENT; `process_payment_receipt_photo` сохраняет file_id, ставит PAID и зовёт `NotificationService(bot, ctx.studio, ...)` (проверить через FakeBot, что при заданном manager_chat_id ушло фото).
  - `my_orders.py` → `test_handlers_my_orders.py`: `cmd_orders` показывает заказы пользователя текущей студии; `show_order_details` использует `delivery_display_name(ctx.settings, ...)`.
  - `manager.py` → `test_handlers_manager.py`: `manager_confirm_payment` переводит PAID→CONFIRMED и шлёт сообщение клиенту (FakeBot). Получает `ctx` (studio_id из ctx).
  - `crop.py` → `test_handlers_crop.py`: `skip_crop` показывает сводку; `handle_webapp_data` сохраняет кроп и зовёт `get_delivery_message(ctx)`.

  Каждый модуль — отдельный commit:
```bash
git add src/bot/handlers/<module>.py tests/bot/test_handlers_<module>.py
git commit -m "refactor: <module> на StudioContext (studio-скоуп)"
```

- [ ] **Step 6: полный прогон**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest -W error`
Expected: всё зелёное, ноль warnings.

> Замечание для реализатора: модульные `router = Router()` и декораторы `@router.callback_query(...)` остаются как есть — на этом этапе одна студия, один Dispatcher. Развязка singleton-роутеров для одновременного запуска нескольких студий делается в плане 2b (webhook) — там фабрики `BASE_ROUTER_FACTORIES` начнут создавать новые роутеры на каждый вызов. Сейчас НЕ дублировать роутеры между студиями.

---

### Task 10: config slim + main.py на реестр студий

**Files:**
- Modify: `src/config.py` (`bot_token` опционален)
- Modify: `main.py`
- Test: `tests/bot/test_main_wiring.py`

**Interfaces:**
- Consumes: `build_dispatcher`, `build_bot` (Task 8), `Studio`, `SettingsService.load_cache(studio_id)`, `ProductService.load_cache(studio_id)`.
- Produces: функция `load_active_studios(session) -> list[Studio]` (в `main.py` или `src/bot/registry.py`); `main()` грузит активные студии, для каждой греет кеши настроек/товаров и (для одной студии сейчас) строит bot+dispatcher и запускает polling. `config.bot_token` больше не обязателен (`Field(default="", alias="BOT_TOKEN")`).

- [ ] **Step 1: Написать тест `tests/bot/test_main_wiring.py`**

```python
"""Тест выборки активных студий и прогрева кешей."""
import os, pytest
from cryptography.fernet import Fernet
from src.services.studio_provisioning import provision_studio
from src.bot.registry import load_active_studios


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_load_active_studios_excludes_inactive(db_session):
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    b = await provision_studio(db_session, slug="b", name="B", bot_token="t", admin_username="b", admin_password="p")
    b.is_active = False
    await db_session.commit()
    studios = await load_active_studios(db_session)
    slugs = {s.slug for s in studios}
    assert "a" in slugs and "b" not in slugs
```

- [ ] **Step 2: RED**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_main_wiring.py -v`
Expected: FAIL — нет `load_active_studios`.

- [ ] **Step 3: Добавить `load_active_studios` в `src/bot/registry.py`**

```python
from sqlalchemy import select

async def load_active_studios(session) -> list[Studio]:
    """Возвращает активные студии."""
    result = await session.execute(select(Studio).where(Studio.is_active.is_(True)))
    return list(result.scalars().all())
```

- [ ] **Step 4: Сделать `bot_token` опциональным в `src/config.py`**

Заменить `bot_token: str = Field(..., alias="BOT_TOKEN")` на:
```python
    bot_token: str = Field(default="", alias="BOT_TOKEN")  # legacy; рантайм берёт токены из Studio
```

- [ ] **Step 5: Переписать `main.py`** на реестр студий

```python
"""Точка входа: polling всех активных студий."""
import asyncio
import logging

from src.database import init_db, async_session
from src.services.settings_service import SettingsService
from src.services.product_service import ProductService
from src.bot.registry import load_active_studios, build_bot, build_dispatcher

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    async with async_session() as session:
        studios = await load_active_studios(session)
        for s in studios:
            await SettingsService(session).load_cache(s.id)
            await ProductService(session).load_cache(s.id)

    if not studios:
        logger.warning("Нет активных студий — бот простаивает.")
        return

    bots, tasks = [], []
    for studio in studios:
        bot = build_bot(studio)
        dp = build_dispatcher(studio)
        bots.append(bot)
        tasks.append(dp.start_polling(bot, handle_signals=False))
        logger.info("Студия %s (%s): polling запущен", studio.slug, studio.id)

    try:
        await asyncio.gather(*tasks)
    finally:
        for bot in bots:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
```

> Фоновые задачи `check_restart_signal`/`cleanup_old_drafts` из старого main.py временно опускаются (перезапуск студии — план 2c через kill-switch; очистка черновиков — отдельная per-studio задача, выносится в план 2b). Это сознательное сокращение; залогировано здесь.

- [ ] **Step 6: GREEN + полный прогон**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest -W error`
Expected: всё зелёное. Дополнительно: `/Users/user/Work/photo28/.venv/bin/python -c "import main; import src.config; print('import ok')"` — без ошибок импорта.

- [ ] **Step 7: Commit**

```bash
git add src/config.py main.py src/bot/registry.py tests/bot/test_main_wiring.py
git commit -m "feat: main.py на реестр студий (polling всех активных), bot_token опционален в config"
```

---

## Что остаётся для следующих планов

- **План 2b (webhook + мультистудийность одновременно):** развязка singleton-роутеров (фабрики создают новые роутеры на вызов), webhook-эндпоинт `/webhook/{token}`, динамическая регистрация/снятие при создании/отключении студии, возврат фоновых задач (cleanup черновиков per-studio).
- **План 2c (роли админки + CRUD студий):** вход через `admin_users` (bcrypt), middleware ролей + зажатие `studio_id`, миграция всех роутов админки на studio-скоуп (включая вызовы `OrderService(session, studio_id)`, `SettingsService.*(studio_id, ...)`, `ProductService.*`), супер-админ CRUD студий, «смотреть как студия», kill-switch. **Сюда же — carry-forward из плана 1:** заскоупить `ProductService.get_product_by_id` по `studio_id`.
- `src/services/notification_service.py` вызывается также из админки (`app.py`) — этот вызов мигрирует в плане 2c.

## Self-Review (выполнено при написании)

- **Покрытие:** инжекция studio_id (Tasks 2,3,9), pricing/delivery/notification/file миграция (Tasks 4-7), реестр+Dispatcher на студию с кастом-роутерами (Task 8), entrypoint (Task 10), тест-оснастка (Task 1). Per-studio кастом-хендлеры — `STUDIO_ROUTER_FACTORIES` (Task 8).
- **Плейсхолдеры:** инфраструктурные задачи (1-8,10) содержат полный код. Task 9 — единообразная механическая трансформация с полным контрактом + worked-примеры + якорные тесты на файл (по дизайну, т.к. 2300 строк before/after — шум; каждый файл верифицируется юнит-тестом).
- **Согласованность типов:** `ctx.settings.get(key, default)` / `ctx.products.get(id)` / `ctx.orders` / `PricingService.calculate_total_cost(studio_id, pbp)` / `NotificationService(bot, studio, settings, products)` / `delivery_display_name(settings, dt)` — сигнатуры совпадают между определениями (Tasks 2,4,5,6) и использованием (Task 9).
- **Известное ограничение:** одновременный запуск нескольких студий упрётся в singleton-роутеры aiogram; в плане 2a одна студия, развязка — план 2b (явно отмечено в Task 8/9).
