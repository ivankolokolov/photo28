# Webhook-транспорт + одновременная мультистудийность — План реализации (под-проект №1, план 2b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести бота с polling на webhook и снять ограничение «одна студия на процесс»: несколько студий работают одновременно, каждая на своём `Bot`+`Dispatcher`, апдейты маршрутизируются по секрету в URL; студии можно добавлять/отключать без рестарта процесса.

**Architecture:** Роутеры хендлеров становятся фабриками (`build_*_router()` создают новый `Router` на каждый вызов), поэтому `build_dispatcher(studio)` можно вызывать для многих студий. In-memory `StudioBotRegistry` держит для каждой активной студии `(bot, dispatcher, secret)`. aiohttp-приложение принимает `POST /webhook/{secret}`, находит студию в реестре по секрету и зовёт `dispatcher.feed_webhook_update(bot, update)`. На старте реестр строится из активных студий и каждому боту ставится webhook (`set_webhook` на `{BASE_WEBHOOK_URL}/webhook/{secret}`). Функции `register_studio`/`unregister_studio` позволяют админке (план 2c) подключать/отключать студию на лету.

**Tech Stack:** Python 3.9+, aiogram 3.4.1 (`Dispatcher.feed_webhook_update`, `Bot.set_webhook`/`delete_webhook`, `aiogram.webhook.aiohttp_server`), aiohttp 3.9.1, SQLAlchemy 2.0 async, PostgreSQL, pytest + pytest-asyncio.

## Global Constraints

- Python 3.9+. Проектный venv: `/Users/user/Work/photo28/.venv/bin/python -m pytest`.
- PostgreSQL только; тесты на `TEST_DATABASE_URL` (`photo28_test`); фикстура `db_session` пересоздаёт схему per-test; `FERNET_KEY` — autouse-фикстура где нужен.
- Тенантность остаётся ЯВНОЙ: `StudioMiddleware(studio_id)` привязан к Dispatcher студии (из 2a) — НЕ менять на резолв по bot.id.
- Каждая студия = свой `Bot` + свой `Dispatcher` (из 2a `build_dispatcher`). Несколько студий в одном процессе → роутеры ОБЯЗАНЫ создаваться заново на каждую студию (фабрики).
- Webhook-секрет НЕ равен токену бота: отдельное случайное поле `Studio.webhook_secret` (urlsafe), путь `/webhook/{webhook_secret}`. Токен в URL не светим.
- `BASE_WEBHOOK_URL` — из env (инфраструктура), напр. `https://bots.example.com`.
- Пристойный вывод тестов под `-W error`. Commit-сообщения на русском (`feat:`/`refactor:`/`test:`/`fix:`/`chore:`).
- Не трогать `src/admin/app.py` (план 2c). Carry-forwards из 2a (ProductService.get_product_by_id scope, get_storage_stats.orders_count, SettingsFacade layering) — НЕ в этом плане, если явно не указано.

## Карта файлов

Создаётся:
- `src/bot/webhook_app.py` — aiohttp-приложение, эндпоинт `/webhook/{secret}`, health.
- `src/bot/lifecycle.py` — `register_studio`/`unregister_studio`/`startup`/`shutdown` (set/delete webhook + работа с реестром).
- тесты под задачи.

Модифицируется:
- `src/models/studio.py` — поле `webhook_secret`.
- `src/services/studio_provisioning.py` — генерация `webhook_secret` при создании студии.
- `src/bot/handlers/*.py` (7 файлов) — `router = Router()` + декораторы → `build_<name>_router()` фабрики.
- `src/bot/registry.py` — `BASE_ROUTER_FACTORIES` зовут `build_*_router()`; `StudioBotRegistry` (in-memory); удалить namespace-комментарии про singleton.
- `tests/bot/test_registry.py` — убрать `_reset_singleton_routers`-шим (фабрики делают его ненужным); добавить тест, что 2 студии строят независимые диспетчеры.
- `src/config.py` — `base_webhook_url` (env `BASE_WEBHOOK_URL`).
- `main.py` — запуск webhook-сервера вместо polling; восстановление фоновой очистки черновиков.

---

### Task 1: Studio.webhook_secret + генерация при провижининге

**Files:**
- Modify: `src/models/studio.py`
- Modify: `src/services/studio_provisioning.py`
- Test: `tests/models/test_studio_webhook_secret.py`

**Interfaces:**
- Produces: `Studio.webhook_secret: Mapped[Optional[str]]` (String(64), unique, index, nullable). `provision_studio(...)` генерирует случайный `secrets.token_urlsafe(32)` и сохраняет в `webhook_secret`.

- [ ] **Step 1: Тест `tests/models/test_studio_webhook_secret.py`**

```python
"""Тест webhook_secret студии."""
import os
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from src.services.studio_provisioning import provision_studio
from src.models.studio import Studio


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_provision_sets_webhook_secret(db_session):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                               admin_username="a", admin_password="p")
    assert s.webhook_secret
    assert len(s.webhook_secret) >= 20


@pytest.mark.asyncio
async def test_webhook_secret_unique_across_studios(db_session):
    s1 = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                                admin_username="a", admin_password="p")
    s2 = await provision_studio(db_session, slug="s2", name="S2", bot_token="t",
                                admin_username="b", admin_password="p")
    assert s1.webhook_secret != s2.webhook_secret
```

- [ ] **Step 2: RED**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/models/test_studio_webhook_secret.py -v`
Expected: FAIL — нет атрибута `webhook_secret`.

- [ ] **Step 3: Добавить поле в `src/models/studio.py`**

Рядом с `bot_username` добавить:
```python
    # Секрет для пути webhook (/webhook/{webhook_secret}); не равен токену.
    webhook_secret: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
```

- [ ] **Step 4: Генерация в `src/services/studio_provisioning.py`**

В начало `provision_studio`, при создании `Studio(...)`, добавить `webhook_secret=secrets.token_urlsafe(32)` (и `import secrets` вверху файла):
```python
    studio = Studio(
        slug=slug, name=name,
        bot_token=encrypt_secret(bot_token),
        webhook_secret=secrets.token_urlsafe(32),
    )
```

- [ ] **Step 5: GREEN + полный сьют**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/models/test_studio_webhook_secret.py -W error -v` затем `/Users/user/Work/photo28/.venv/bin/python -m pytest -W error`
Expected: PASS, ноль warnings.

- [ ] **Step 6: Commit**

```bash
git add src/models/studio.py src/services/studio_provisioning.py tests/models/test_studio_webhook_secret.py
git commit -m "feat: Studio.webhook_secret + генерация при провижининге"
```

---

### Task 2: Фабрики роутеров (7 модулей) + build_dispatcher для многих студий

> Уникальное ограничение, оставленное в 2a: модульные `router = Router()` — singleton, поэтому `build_dispatcher` нельзя звать дважды. Эта задача переводит каждый handlers-модуль на фабрику `build_<name>_router()`, создающую НОВЫЙ `Router` на каждый вызов. Трансформация единообразна — контракт + worked-пример ниже.

**Files:**
- Modify: `src/bot/handlers/start.py`, `order.py`, `delivery.py`, `payment.py`, `my_orders.py`, `manager.py`, `crop.py`
- Modify: `src/bot/registry.py` (BASE_ROUTER_FACTORIES → вызывают build_*_router)
- Modify: `tests/bot/test_registry.py` (убрать singleton-reset шим; добавить тест независимости 2 студий)
- Test: существующие `tests/bot/test_handlers_*.py` должны продолжать проходить (они импортируют конкретные handler-функции — оставить функции на уровне модуля).

**Interfaces:**
- Produces в каждом модуле: `build_<name>_router() -> Router` (`build_start_router`, `build_order_router`, `build_delivery_router`, `build_payment_router`, `build_my_orders_router`, `build_manager_router`, `build_crop_router`). Каждая создаёт `Router(name="<name>")` и регистрирует все хендлеры модуля через `r.message.register(...)` / `r.callback_query.register(...)` с теми же фильтрами, что были в декораторах.
- `registry.BASE_ROUTER_FACTORIES = [build_start_router, build_order_router, ...]` (без lambda-singleton).

**Контракт трансформации (на каждый модуль):**
1. Убрать `router = Router()` на уровне модуля.
2. Каждый хендлер ОСТАВИТЬ функцией уровня модуля (тесты импортируют их по имени), но СНЯТЬ декоратор `@router.X(...)`.
3. Добавить `def build_<name>_router() -> Router:` которая создаёт `r = Router(name="<name>")`, регистрирует каждый хендлер: для `@router.message(FILTERS)` → `r.message.register(handler, FILTERS)`; для `@router.callback_query(FILTERS)` → `r.callback_query.register(handler, FILTERS)`. Порядок регистрации = порядку хендлеров в файле (важно для пересекающихся фильтров).
4. Импорты `Router` сохранить; `F`, фильтры (`CommandStart`, `Command`, `OrderStates.*`) — те же, что в декораторах.

**Worked-пример (start.py):**
Было:
```python
router = Router()

@router.message(CommandStart())
async def cmd_start(message, state, ctx): ...

@router.message(Command("chatid"))
async def cmd_chatid(message): ...

@router.callback_query(F.data.startswith("continue_order:"))
async def continue_order(callback, state, ctx): ...
# ... new_order (F.data == "new_order"), cmd_cancel (Command("cancel")), cmd_help (Command("help"))
```
Стало (хендлеры те же, без декораторов; добавлена фабрика в конец файла):
```python
async def cmd_start(message, state, ctx): ...
async def cmd_chatid(message): ...
async def continue_order(callback, state, ctx): ...
async def new_order(callback, state, ctx): ...
async def cmd_cancel(message, state, ctx): ...
async def cmd_help(message, ctx): ...


def build_start_router() -> Router:
    r = Router(name="start")
    r.message.register(cmd_start, CommandStart())
    r.message.register(cmd_chatid, Command("chatid"))
    r.message.register(cmd_cancel, Command("cancel"))
    r.message.register(cmd_help, Command("help"))
    r.callback_query.register(continue_order, F.data.startswith("continue_order:"))
    r.callback_query.register(new_order, F.data == "new_order")
    return r
```

**Регистрация фильтров по состоянию (FSM):** где был `@router.message(OrderStates.uploading_photos, F.photo)` → `r.message.register(handle_photo, OrderStates.uploading_photos, F.photo)`. Несколько позиционных фильтров передаются как несколько аргументов в `register(...)`.

**ВАЖНО — порядок:** в `order.py`/`delivery.py` есть пересекающиеся message-фильтры в состояниях; регистрируйте СТРОГО в исходном порядке следования в файле, иначе изменится приоритет матчинга.

- [ ] **Step 1 (на каждый модуль): тест RED не требуется отдельный** — существующие `test_handlers_<module>.py` импортируют хендлеры по имени (функции остаются). Добавьте/обновите по одному тесту на модуль, проверяющему, что `build_<name>_router()` возвращает `Router` с зарегистрированными хендлерами, например для start:

```python
def test_build_start_router_registers_handlers():
    from src.bot.handlers.start import build_start_router
    r = build_start_router()
    from aiogram import Router
    assert isinstance(r, Router)
    # есть хотя бы message- и callback-хендлеры
    assert len(r.message.handlers) >= 4
    assert len(r.callback_query.handlers) >= 2
```

- [ ] **Step 2: применить контракт к каждому из 7 модулей** (start, order, delivery, payment, my_orders, manager, crop). После каждого — прогон `tests/bot/test_handlers_<module>.py` (должны проходить без изменений, т.к. функции на месте) + новый build_router-тест.

- [ ] **Step 3: обновить `src/bot/registry.py`**

```python
from src.bot.handlers.start import build_start_router
from src.bot.handlers.order import build_order_router
from src.bot.handlers.delivery import build_delivery_router
from src.bot.handlers.payment import build_payment_router
from src.bot.handlers.my_orders import build_my_orders_router
from src.bot.handlers.manager import build_manager_router
from src.bot.handlers.crop import build_crop_router

BASE_ROUTER_FACTORIES: List[Callable[[], Router]] = [
    build_start_router, build_order_router, build_delivery_router,
    build_payment_router, build_my_orders_router, build_manager_router,
    build_crop_router,
]
```
Обновить докстринг `build_dispatcher`: теперь его можно вызывать для многих студий — каждая фабрика создаёт новый Router.

- [ ] **Step 4: убрать singleton-шим и добавить тест независимости в `tests/bot/test_registry.py`**

Удалить автоюз-фикстуру `_reset_singleton_routers` (больше не нужна). Добавить:
```python
@pytest.mark.asyncio
async def test_two_studios_build_independent_dispatchers(db_session):
    s1 = await provision_studio(db_session, slug="a", name="A", bot_token="t1", admin_username="a", admin_password="p")
    s2 = await provision_studio(db_session, slug="b", name="B", bot_token="t2", admin_username="b", admin_password="p")
    dp1 = build_dispatcher(s1)
    dp2 = build_dispatcher(s2)
    assert dp1 is not dp2
    assert len(dp1.sub_routers) >= 7 and len(dp2.sub_routers) >= 7  # обе получили базовые роутеры
```

- [ ] **Step 5: полный сьют + commit (по модулю или один коммит на задачу)**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest -W error`
Expected: всё зелёное, ноль warnings; `build_dispatcher` теперь вызывается дважды без RuntimeError.

```bash
git add src/bot/handlers/ src/bot/registry.py tests/bot/test_registry.py tests/bot/test_handlers_*.py
git commit -m "refactor: фабрики роутеров build_*_router — несколько студий в одном процессе"
```

---

### Task 3: StudioBotRegistry (in-memory)

**Files:**
- Modify: `src/bot/registry.py`
- Test: `tests/bot/test_studio_bot_registry.py`

**Interfaces:**
- Produces: класс `StudioBotRegistry` с методами:
  - `add(studio) -> None` — строит `build_bot(studio)` + `build_dispatcher(studio)`, хранит запись `{secret: (studio_id, bot, dispatcher)}` и `{studio_id: secret}`.
  - `get_by_secret(secret) -> Optional[tuple[int, Bot, Dispatcher]]`.
  - `remove(studio_id) -> Optional[Bot]` — удаляет запись, возвращает bot (для delete_webhook/закрытия сессии).
  - `bots() -> list[Bot]`, `entries() -> list[tuple[int, Bot, Dispatcher]]`.
  - Игнорирует студию без `bot_token` или без `webhook_secret` (лог + пропуск), чтобы одна некорректная запись не ломала остальные.

- [ ] **Step 1: Тест `tests/bot/test_studio_bot_registry.py`**

```python
"""Тесты in-memory реестра ботов студий."""
import os
import pytest
from cryptography.fernet import Fernet
from aiogram import Bot, Dispatcher

from src.services.studio_provisioning import provision_studio
from src.bot.registry import StudioBotRegistry


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_add_and_get_by_secret(db_session):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                               admin_username="a", admin_password="p")
    reg = StudioBotRegistry()
    reg.add(s)
    found = reg.get_by_secret(s.webhook_secret)
    assert found is not None
    studio_id, bot, dp = found
    assert studio_id == s.id
    assert isinstance(bot, Bot) and isinstance(dp, Dispatcher)
    assert reg.get_by_secret("nope") is None


@pytest.mark.asyncio
async def test_remove(db_session):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                               admin_username="a", admin_password="p")
    reg = StudioBotRegistry()
    reg.add(s)
    bot = reg.remove(s.id)
    assert bot is not None
    assert reg.get_by_secret(s.webhook_secret) is None


@pytest.mark.asyncio
async def test_skips_studio_without_token(db_session):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                               admin_username="a", admin_password="p")
    s.bot_token = None
    await db_session.commit()
    reg = StudioBotRegistry()
    reg.add(s)  # не должно падать
    assert reg.get_by_secret(s.webhook_secret) is None
```

- [ ] **Step 2: RED**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_studio_bot_registry.py -v`
Expected: FAIL — нет `StudioBotRegistry`.

- [ ] **Step 3: Добавить `StudioBotRegistry` в `src/bot/registry.py`**

```python
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class StudioBotRegistry:
    """In-memory реестр активных ботов студий (secret → bot+dispatcher)."""

    def __init__(self):
        # secret -> (studio_id, bot, dispatcher)
        self._by_secret: Dict[str, Tuple[int, "Bot", "Dispatcher"]] = {}
        self._secret_by_studio: Dict[int, str] = {}

    def add(self, studio) -> None:
        if not studio.bot_token or not studio.webhook_secret:
            logger.warning("Студия %s пропущена в реестре: нет токена/секрета", getattr(studio, "id", "?"))
            return
        bot = build_bot(studio)
        dp = build_dispatcher(studio)
        self._by_secret[studio.webhook_secret] = (studio.id, bot, dp)
        self._secret_by_studio[studio.id] = studio.webhook_secret

    def get_by_secret(self, secret: str) -> Optional[Tuple[int, "Bot", "Dispatcher"]]:
        return self._by_secret.get(secret)

    def remove(self, studio_id: int) -> Optional["Bot"]:
        secret = self._secret_by_studio.pop(studio_id, None)
        if secret is None:
            return None
        entry = self._by_secret.pop(secret, None)
        return entry[1] if entry else None

    def bots(self) -> List["Bot"]:
        return [bot for (_sid, bot, _dp) in self._by_secret.values()]

    def entries(self) -> List[Tuple[int, "Bot", "Dispatcher"]]:
        return list(self._by_secret.values())
```

- [ ] **Step 4: GREEN + полный сьют**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_studio_bot_registry.py -W error -v` затем полный `-W error`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bot/registry.py tests/bot/test_studio_bot_registry.py
git commit -m "feat: StudioBotRegistry (in-memory реестр ботов студий по секрету)"
```

---

### Task 4: Webhook aiohttp-приложение + эндпоинт /webhook/{secret}

**Files:**
- Create: `src/bot/webhook_app.py`
- Test: `tests/bot/test_webhook_app.py`

**Interfaces:**
- Consumes: `StudioBotRegistry` (Task 3), `aiogram.types.Update`, `Dispatcher.feed_webhook_update`.
- Produces: `build_webhook_app(registry: StudioBotRegistry) -> aiohttp.web.Application` с маршрутами:
  - `POST /webhook/{secret}` — читает JSON, `Update.model_validate(data)`, по `secret` находит `(studio_id, bot, dp)` в реестре; если нет — HTTP 404; иначе `await dp.feed_webhook_update(bot, update)` и HTTP 200.
  - `GET /healthz` — HTTP 200 `{"status":"ok","studios":<n>}`.
  - Приложение хранит `app["registry"] = registry`.

- [ ] **Step 1: Тест `tests/bot/test_webhook_app.py`**

```python
"""Тесты webhook-приложения."""
import os
import pytest
from cryptography.fernet import Fernet
from aiohttp.test_utils import TestClient, TestServer

from src.services.studio_provisioning import provision_studio
from src.bot.registry import StudioBotRegistry
from src.bot.webhook_app import build_webhook_app


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_unknown_secret_404(db_session):
    reg = StudioBotRegistry()
    app = build_webhook_app(reg)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/webhook/doesnotexist", json={"update_id": 1})
        assert resp.status == 404


@pytest.mark.asyncio
async def test_known_secret_feeds_dispatcher(db_session, monkeypatch):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                               admin_username="a", admin_password="p")
    reg = StudioBotRegistry()
    reg.add(s)
    _sid, bot, dp = reg.get_by_secret(s.webhook_secret)

    called = {}
    async def fake_feed(b, update):
        called["bot"] = b
        called["update_id"] = update.update_id
    monkeypatch.setattr(dp, "feed_webhook_update", fake_feed)

    app = build_webhook_app(reg)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(f"/webhook/{s.webhook_secret}", json={"update_id": 42})
        assert resp.status == 200
    assert called["update_id"] == 42
    assert called["bot"] is bot


@pytest.mark.asyncio
async def test_healthz(db_session):
    reg = StudioBotRegistry()
    app = build_webhook_app(reg)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/healthz")
        assert resp.status == 200
        body = await resp.json()
        assert body["status"] == "ok"
```

- [ ] **Step 2: RED**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_webhook_app.py -v`
Expected: FAIL — нет модуля `src.bot.webhook_app`.

- [ ] **Step 3: Создать `src/bot/webhook_app.py`**

```python
"""aiohttp-приложение для приёма webhook-апдейтов всех студий."""
import logging
from aiohttp import web
from aiogram.types import Update

from src.bot.registry import StudioBotRegistry

logger = logging.getLogger(__name__)


async def _handle_webhook(request: web.Request) -> web.Response:
    registry: StudioBotRegistry = request.app["registry"]
    secret = request.match_info["secret"]
    entry = registry.get_by_secret(secret)
    if entry is None:
        return web.Response(status=404, text="unknown webhook")
    studio_id, bot, dp = entry
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_webhook_update(bot, update)
    return web.Response(status=200)


async def _handle_health(request: web.Request) -> web.Response:
    registry: StudioBotRegistry = request.app["registry"]
    return web.json_response({"status": "ok", "studios": len(registry.entries())})


def build_webhook_app(registry: StudioBotRegistry) -> web.Application:
    app = web.Application()
    app["registry"] = registry
    app.router.add_post("/webhook/{secret}", _handle_webhook)
    app.router.add_get("/healthz", _handle_health)
    return app
```

- [ ] **Step 4: GREEN + полный сьют**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_webhook_app.py -W error -v` затем полный `-W error`.
Expected: PASS (3 теста). Если `Update.model_validate(..., context=...)` ругается в 3.4.1 — убрать `context=` (тест передаёт минимальный апдейт), и оставить `Update.model_validate(data)`.

- [ ] **Step 5: Commit**

```bash
git add src/bot/webhook_app.py tests/bot/test_webhook_app.py
git commit -m "feat: webhook-приложение /webhook/{secret} + /healthz"
```

---

### Task 5: Lifecycle — set/delete webhook + register/unregister студии

**Files:**
- Modify: `src/config.py` (`base_webhook_url`)
- Create: `src/bot/lifecycle.py`
- Test: `tests/bot/test_lifecycle.py`

**Interfaces:**
- Consumes: `StudioBotRegistry`, `Bot.set_webhook`/`delete_webhook`, `load_active_studios`, `config.base_webhook_url`.
- Produces:
  - `config.base_webhook_url: str` (env `BASE_WEBHOOK_URL`, default "").
  - `webhook_url_for(secret: str) -> str` — `f"{base_webhook_url}/webhook/{secret}"`.
  - `async def register_studio(registry, studio) -> None` — `registry.add(studio)`; если добавлен, `await bot.set_webhook(webhook_url_for(studio.webhook_secret))`.
  - `async def unregister_studio(registry, studio_id) -> None` — `bot = registry.remove(studio_id)`; если был, `await bot.delete_webhook()` + `await bot.session.close()`.
  - `async def startup(registry, session) -> None` — для каждой активной студии: прогреть кеши (SettingsService/ProductService load_cache) + `register_studio`.
  - `async def shutdown(registry) -> None` — для всех entries `delete_webhook` + `session.close`.

- [ ] **Step 1: Тест `tests/bot/test_lifecycle.py`**

```python
"""Тесты lifecycle (register/unregister без реальной сети — мокаем set_webhook)."""
import os
import pytest
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.bot.registry import StudioBotRegistry
from src.bot import lifecycle


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


def test_webhook_url_for(monkeypatch):
    monkeypatch.setattr(lifecycle.settings, "base_webhook_url", "https://b.example")
    assert lifecycle.webhook_url_for("abc") == "https://b.example/webhook/abc"


@pytest.mark.asyncio
async def test_register_sets_webhook(db_session, monkeypatch):
    monkeypatch.setattr(lifecycle.settings, "base_webhook_url", "https://b.example")
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="123:ABC",
                               admin_username="a", admin_password="p")
    reg = StudioBotRegistry()
    calls = {}
    # мокаем set_webhook на инстансе бота через подмену метода после add
    reg.add(s)
    _sid, bot, _dp = reg.get_by_secret(s.webhook_secret)
    async def fake_set_webhook(url, **kw):
        calls["url"] = url
    monkeypatch.setattr(bot, "set_webhook", fake_set_webhook)
    # повторно регистрируем уже добавленную студию через register_studio на чистом реестре
    reg2 = StudioBotRegistry()
    reg2.add(s)
    _sid2, bot2, _dp2 = reg2.get_by_secret(s.webhook_secret)
    monkeypatch.setattr(bot2, "set_webhook", fake_set_webhook)
    # вызываем внутреннюю установку вебхука напрямую
    await bot2.set_webhook(lifecycle.webhook_url_for(s.webhook_secret))
    assert calls["url"] == f"https://b.example/webhook/{s.webhook_secret}"
```

> Примечание: `register_studio` дергает реальный `bot.set_webhook` (сеть Telegram). В тесте мы мокаем метод бота. Реализатор: если структура теста неудобна для мока (bot создаётся внутри add), допускается реорганизовать тест так, чтобы мокать `Bot.set_webhook` классово через monkeypatch.setattr на `aiogram.Bot` ДО `reg.add`, и проверять, что `register_studio` его вызвал с правильным URL. Тест должен реально проверять, что register_studio ставит webhook на правильный URL и кладёт студию в реестр; не ослаблять до no-op.

- [ ] **Step 2: RED**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_lifecycle.py -v`
Expected: FAIL — нет `base_webhook_url`/модуля lifecycle.

- [ ] **Step 3: `src/config.py` — добавить поле**

```python
    base_webhook_url: str = Field(default="", alias="BASE_WEBHOOK_URL")
```

- [ ] **Step 4: Создать `src/bot/lifecycle.py`**

```python
"""Жизненный цикл webhook'ов студий."""
import logging

from src.config import settings
from src.services.settings_service import SettingsService
from src.services.product_service import ProductService
from src.bot.registry import StudioBotRegistry, load_active_studios

logger = logging.getLogger(__name__)


def webhook_url_for(secret: str) -> str:
    return f"{settings.base_webhook_url}/webhook/{secret}"


async def register_studio(registry: StudioBotRegistry, studio) -> None:
    registry.add(studio)
    entry = registry.get_by_secret(studio.webhook_secret) if studio.webhook_secret else None
    if entry is None:
        return
    _sid, bot, _dp = entry
    await bot.set_webhook(webhook_url_for(studio.webhook_secret))
    logger.info("Студия %s (%s): webhook установлен", studio.slug, studio.id)


async def unregister_studio(registry: StudioBotRegistry, studio_id: int) -> None:
    bot = registry.remove(studio_id)
    if bot is None:
        return
    try:
        await bot.delete_webhook()
    finally:
        await bot.session.close()
    logger.info("Студия %s: webhook снят", studio_id)


async def startup(registry: StudioBotRegistry, session) -> None:
    studios = await load_active_studios(session)
    for s in studios:
        await SettingsService(session).load_cache(s.id)
        await ProductService(session).load_cache(s.id)
        await register_studio(registry, s)


async def shutdown(registry: StudioBotRegistry) -> None:
    for _sid, bot, _dp in registry.entries():
        try:
            await bot.delete_webhook()
        finally:
            await bot.session.close()
```

- [ ] **Step 5: GREEN + полный сьют**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_lifecycle.py -W error -v` затем полный `-W error`.

- [ ] **Step 6: Commit**

```bash
git add src/config.py src/bot/lifecycle.py tests/bot/test_lifecycle.py
git commit -m "feat: lifecycle webhook'ов студий (register/unregister/startup/shutdown)"
```

---

### Task 6: main.py → webhook-сервер + восстановление очистки черновиков

**Files:**
- Modify: `main.py`
- Create: `src/bot/background.py` (периодическая очистка черновиков по студиям)
- Test: `tests/bot/test_background.py`

**Interfaces:**
- Consumes: `build_webhook_app`, `StudioBotRegistry`, `startup`/`shutdown`, `OrderService.delete_old_drafts`.
- Produces:
  - `src/bot/background.py`: `async def cleanup_old_drafts_once(session, studio_ids: list[int], days=7) -> int` — для каждой студии `OrderService(session, sid).delete_old_drafts(days)`, сумма удалённых. (Периодический цикл живёт в main.py, юнит-тестируем разовую функцию.)
  - `main.py`: строит `StudioBotRegistry`, `startup(registry, session)`, поднимает aiohttp `web.run_app(build_webhook_app(registry), host, port)` с on_shutdown → `shutdown(registry)`. Периодическая задача очистки — `aiohttp` `app.on_startup`-таск.

- [ ] **Step 1: Тест `tests/bot/test_background.py`**

```python
"""Тест разовой очистки черновиков по студиям."""
import os
import pytest
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.services.order_service import OrderService
from src.models.order import Order, OrderStatus
from src.bot.background import cleanup_old_drafts_once


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_cleanup_only_old_drafts_per_studio(db_session):
    s1 = await provision_studio(db_session, slug="s1", name="S1", bot_token="t", admin_username="a", admin_password="p")
    svc = OrderService(db_session, s1.id)
    user = await svc.get_or_create_user(telegram_id=1)
    old = await svc.create_order(user)
    # делаем черновик старым
    old.created_at = datetime.now() - timedelta(days=10)
    await db_session.commit()

    deleted = await cleanup_old_drafts_once(db_session, [s1.id], days=7)
    assert deleted == 1
```

- [ ] **Step 2: RED**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/bot/test_background.py -v`
Expected: FAIL — нет `src.bot.background`.

- [ ] **Step 3: Создать `src/bot/background.py`**

```python
"""Фоновые задачи бота (студия-скоупленные)."""
import logging
from src.services.order_service import OrderService

logger = logging.getLogger(__name__)


async def cleanup_old_drafts_once(session, studio_ids, days: int = 7) -> int:
    total = 0
    for sid in studio_ids:
        deleted = await OrderService(session, sid).delete_old_drafts(days=days)
        total += deleted
    if total:
        logger.info("Очищено %s старых черновиков по %s студиям", total, len(studio_ids))
    return total
```

- [ ] **Step 4: Переписать `main.py`**

```python
"""Точка входа: webhook-сервер всех активных студий."""
import asyncio
import logging
import os
from aiohttp import web

from src.database import init_db, async_session
from src.bot.registry import StudioBotRegistry, load_active_studios
from src.bot.webhook_app import build_webhook_app
from src.bot.lifecycle import startup, shutdown
from src.bot.background import cleanup_old_drafts_once

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60


async def _cleanup_loop():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            async with async_session() as session:
                studios = await load_active_studios(session)
                await cleanup_old_drafts_once(session, [s.id for s in studios], days=7)
        except Exception as e:
            logger.error("Ошибка очистки черновиков: %s", e)


async def _on_startup(app: web.Application):
    await init_db()
    async with async_session() as session:
        await startup(app["registry"], session)
    app["cleanup_task"] = asyncio.create_task(_cleanup_loop())


async def _on_shutdown(app: web.Application):
    app["cleanup_task"].cancel()
    await shutdown(app["registry"])


def main():
    registry = StudioBotRegistry()
    app = build_webhook_app(registry)
    app.on_startup.append(_on_startup)
    app.on_shutdown.append(_on_shutdown)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("WEBHOOK_PORT", "8081")))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: GREEN + полный сьют + import-check**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest -W error` и `/Users/user/Work/photo28/.venv/bin/python -c "import main; print('ok')"`.
Expected: PASS, import ok. (`web.run_app` не вызывается при импорте — только в `main()`.)

- [ ] **Step 6: Commit**

```bash
git add main.py src/bot/background.py tests/bot/test_background.py
git commit -m "feat: webhook-сервер в main.py + периодическая очистка черновиков по студиям"
```

---

### Task 7: env.example + README/деплой-заметки для webhook

**Files:**
- Modify: `env.example`
- Modify: `README.md` (секция деплоя — webhook вместо polling)

**Interfaces:**
- Produces: документированные env-переменные `BASE_WEBHOOK_URL`, `WEBHOOK_PORT`; обновлённая инструкция (nginx проксирует `/webhook/` и `/healthz` на `WEBHOOK_PORT`; один systemd-сервис `photo28-bot` теперь webhook-сервер; Telegram setWebhook ставится автоматически на старте).

- [ ] **Step 1: Обновить `env.example`** — добавить:
```
# Webhook (план 2b)
BASE_WEBHOOK_URL=https://bots.example.com
WEBHOOK_PORT=8081
```

- [ ] **Step 2: Обновить секцию деплоя в `README.md`** — заменить описание polling на webhook: `main.py` теперь запускает aiohttp на `WEBHOOK_PORT`; nginx проксирует `https://bots.example.com/webhook/` и `/healthz` на него; вебхуки ставятся автоматически при старте через lifecycle.startup. (Текст — на русском, в стиле существующего README.)

- [ ] **Step 3: Commit**

```bash
git add env.example README.md
git commit -m "docs: env и деплой-заметки для webhook-режима"
```

---

## Что остаётся для следующих планов

- **План 2c (роли админки + CRUD студий):** вход через admin_users, middleware ролей + зажатие studio_id, миграция роутов админки на studio_id; супер-админ CRUD студий — при создании/активации студии админка зовёт `lifecycle.register_studio(registry, studio)`, при отключении — `lifecycle.unregister_studio(registry, studio_id)` (kill-switch). Для этого реестр должен быть доступен админ-процессу — если бот и админка это РАЗНЫЕ процессы, потребуется межпроцессный сигнал (через таблицу settings/студии, как текущий restart-signal) — спроектировать в 2c. Carry-forwards из 2a (ProductService.get_product_by_id scope, get_storage_stats.orders_count, SettingsFacade layering) — тоже 2c.
- **Под-проекты №2 (агент печати + счётчик), №3 (биллинг + онбординг-визард), №4 (лендинг).**

## Self-Review (выполнено при написании)

- **Покрытие:** webhook_secret (Task 1), фабрики роутеров для мультистудийности (Task 2), in-memory реестр (Task 3), webhook-приложение (Task 4), lifecycle set/delete webhook + register/unregister (Task 5), entrypoint+фоновые задачи (Task 6), env/деплой (Task 7).
- **Плейсхолдеры:** инфраструктурные задачи содержат полный код. Task 2 — единообразная механическая трансформация с контрактом + worked-пример (как Task 9 в 2a); каждый модуль верифицируется существующими handler-тестами (функции остаются на месте) + build_router-тестом.
- **Согласованность типов:** `StudioBotRegistry.add/get_by_secret/remove/entries`, `build_<name>_router() -> Router`, `register_studio(registry, studio)`/`unregister_studio(registry, studio_id)`, `webhook_url_for(secret)`, `build_webhook_app(registry)` — сигнатуры совпадают между определениями (Tasks 3,5,4,2) и использованием (Tasks 4,5,6).
- **Известный момент (для 2c):** межпроцессное взаимодействие админка→реестр бота, если это разные процессы — явно отмечено.
- **aiogram 3.4.1 проверено:** `TokenBasedRequestHandler`/`SimpleRequestHandler` есть, но используется собственный эндпоинт (per-studio Dispatcher); `Dispatcher.feed_webhook_update` и `Bot.set_webhook`/`delete_webhook` присутствуют.
