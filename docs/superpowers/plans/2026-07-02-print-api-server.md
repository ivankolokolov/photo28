# Серверный Print API (под-проект №2, план 2-I) — План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Серверный HTTP-API, которым локальный агент печати будет пользоваться: пайринг (код→токен агента, привязанный к студии), выдача подтверждённых заказов на печать, отдача байтов фото, рапорт о напечатанном (наполнение `billing_events`), heartbeat — всё студия-изолированно.

**Architecture:** Новый `PrintAgent` (модель) + `PrintAgentService` (пайринг/аутентификация по токену, sha256-хеш токена). Эндпоинты — отдельный модуль `src/admin/print_api.py` (FastAPI `APIRouter`, включённый в существующее админ-приложение), аутентификация по заголовку `Authorization: Bearer <token>` → резолв `studio_id`. Каждый эндпоинт фильтрует по студии агента. Фото сервер тянет из Telegram по расшифрованному токену бота студии. Тесты — прямым вызовом функций-эндпоинтов (FakeRequest + monkeypatch `async_session`), как в админке 2c.

**Tech Stack:** Python 3.9+, FastAPI (APIRouter), SQLAlchemy 2.0 async, PostgreSQL, aiogram (Bot.get_file/download_file), Pillow (не здесь), pytest + pytest-asyncio.

## Global Constraints

- Python 3.9+. Проектный venv: `/Users/user/Work/photo28/.venv/bin/python -m pytest`.
- PostgreSQL; тесты на `TEST_DATABASE_URL`; `db_session` пересоздаёт схему per-test; `FERNET_KEY` — autouse-фикстура где нужен (пайринг/фото используют шифрование токена студии).
- **Изоляция (красная нить):** каждый эндпоинт резолвит `studio_id` из токена агента и фильтрует по нему. Агент студии A не получает jobs/photo/report чужой студии; `photo_id`/`order_id` проверяются на принадлежность студии агента (иначе 404).
- Токен агента: `secrets.token_urlsafe(32)`; в БД хранится ТОЛЬКО `sha256`-хеш (`token_hash`), сырой токен отдаётся один раз при пайринге. Код пайринга — одноразовый, короткий, тоже сверяется и гасится.
- Биллинговая единица — фото (позиция). `fee` = snapshot `studio.platform_fee_per_photo` на момент печати. Рапорт идемпотентен (повторный рапорт того же фото не создаёт дубль `billing_event`).
- Тесты — прямым вызовом функций-эндпоинтов (НЕ Starlette TestClient: он гоняет на другом loop → кросс-loop с asyncpg). Использовать `FakeRequest` из `tests/admin/conftest.py` (+ при необходимости расширить его `headers`).
- v1: один агент на студию (без координации нескольких агентов).
- Commit-сообщения на русском; вывод тестов pristine под `-W error`.

## Карта файлов

Создаётся:
- `src/models/print_agent.py` — модель `PrintAgent`.
- `src/services/print_agent_service.py` — `PrintAgentService` (пайринг/аутентификация).
- `src/admin/print_api.py` — `APIRouter` с эндпоинтами `/api/print/*` + агент-аутентификация.
- тесты: `tests/services/test_print_agent_service.py`, `tests/admin/test_print_api.py`.

Модифицируется:
- `src/models/__init__.py` — регистрация `PrintAgent`.
- `src/admin/app.py` — `app.include_router(print_router)`; роут генерации кода пайринга в админке (`require_studio`).
- `src/admin/conftest.py` (tests) — при необходимости добавить `headers` в `FakeRequest` (для Bearer-токена).

---

### Task 1: Модель PrintAgent

**Files:**
- Create: `src/models/print_agent.py`
- Modify: `src/models/__init__.py`
- Test: `tests/models/test_print_agent.py`

**Interfaces:**
- Produces: `PrintAgent(Base)` — `id`, `studio_id` (FK studios.id CASCADE, index, NOT NULL), `name` (str, default ""), `token_hash` (str, nullable — до активации), `pairing_code` (str, nullable, index), `paired_at` (datetime, nullable), `last_seen_at` (datetime, nullable), `printer_status` (str, default ""), `queue_len` (int, default 0). created_at/updated_at из Base.

- [ ] **Step 1: Тест `tests/models/test_print_agent.py`**

```python
"""Тест модели PrintAgent."""
import pytest
from sqlalchemy import select
from src.models.studio import Studio
from src.models.print_agent import PrintAgent


@pytest.mark.asyncio
async def test_create_print_agent(db_session):
    s = Studio(slug="s1", name="S1")
    db_session.add(s)
    await db_session.commit()
    agent = PrintAgent(studio_id=s.id, name="Касса-1", pairing_code="ABC123")
    db_session.add(agent)
    await db_session.commit()
    loaded = (await db_session.execute(select(PrintAgent))).scalar_one()
    assert loaded.studio_id == s.id
    assert loaded.pairing_code == "ABC123"
    assert loaded.token_hash is None
    assert loaded.queue_len == 0
```

- [ ] **Step 2: RED** — `pytest tests/models/test_print_agent.py -v` → нет модуля.

- [ ] **Step 3: Создать `src/models/print_agent.py`**

```python
"""Модель локального агента печати студии."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class PrintAgent(Base):
    """Агент печати, привязанный к студии (пайринг по коду → токен)."""

    __tablename__ = "print_agents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    token_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    pairing_code: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    paired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    printer_status: Mapped[str] = mapped_column(String(255), default="")
    queue_len: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<PrintAgent studio={self.studio_id} name={self.name}>"
```

- [ ] **Step 4: Зарегистрировать в `src/models/__init__.py`** — `from src.models.print_agent import PrintAgent` + `"PrintAgent"` в `__all__`.

- [ ] **Step 5: GREEN + полный сьют** (`-W error`). **Commit:** `git add src/models/print_agent.py src/models/__init__.py tests/models/test_print_agent.py && git commit -m "feat: модель PrintAgent (агент печати студии)"`

---

### Task 2: PrintAgentService — пайринг и аутентификация по токену

**Files:**
- Create: `src/services/print_agent_service.py`
- Test: `tests/services/test_print_agent_service.py`

**Interfaces:**
- Consumes: `PrintAgent`, `Studio`.
- Produces `PrintAgentService(session)`:
  - `@staticmethod _hash_token(raw: str) -> str` — `hashlib.sha256(raw.encode()).hexdigest()`.
  - `async def create_pairing(studio_id: int, name: str = "") -> PrintAgent` — создаёт `PrintAgent` с новым `pairing_code = secrets.token_urlsafe(6)` (без токена), commit, возвращает агента (с кодом).
  - `async def pair(code: str) -> Optional[tuple[PrintAgent, str]]` — находит агента по `pairing_code`; если найден: генерирует `raw = secrets.token_urlsafe(32)`, ставит `token_hash = _hash_token(raw)`, `pairing_code = None`, `paired_at = now`, commit; возвращает `(agent, raw)`. Если код не найден → None.
  - `async def authenticate(token: str) -> Optional[PrintAgent]` — по `_hash_token(token)` находит агента с таким `token_hash` (и `token_hash is not None`); иначе None.

- [ ] **Step 1: Тест `tests/services/test_print_agent_service.py`**

```python
"""Тесты пайринга/аутентификации агента печати."""
import pytest
from src.models.studio import Studio
from src.services.print_agent_service import PrintAgentService


async def _studio(db_session, slug="s1"):
    s = Studio(slug=slug, name=slug)
    db_session.add(s)
    await db_session.commit()
    return s


@pytest.mark.asyncio
async def test_create_pairing_generates_code(db_session):
    s = await _studio(db_session)
    svc = PrintAgentService(db_session)
    agent = await svc.create_pairing(s.id, name="Касса")
    assert agent.pairing_code
    assert agent.token_hash is None
    assert agent.studio_id == s.id


@pytest.mark.asyncio
async def test_pair_exchanges_code_for_token(db_session):
    s = await _studio(db_session)
    svc = PrintAgentService(db_session)
    agent = await svc.create_pairing(s.id)
    code = agent.pairing_code

    result = await svc.pair(code)
    assert result is not None
    paired, raw_token = result
    assert paired.id == agent.id
    assert paired.pairing_code is None
    assert paired.token_hash == PrintAgentService._hash_token(raw_token)
    # код больше не работает
    assert await svc.pair(code) is None


@pytest.mark.asyncio
async def test_authenticate_by_token(db_session):
    s = await _studio(db_session)
    svc = PrintAgentService(db_session)
    agent = await svc.create_pairing(s.id)
    _, raw = await svc.pair(agent.pairing_code)

    authed = await svc.authenticate(raw)
    assert authed is not None
    assert authed.id == agent.id
    assert authed.studio_id == s.id
    assert await svc.authenticate("garbage") is None
```

- [ ] **Step 2: RED.**

- [ ] **Step 3: Создать `src/services/print_agent_service.py`**

```python
"""Пайринг и аутентификация агентов печати."""
import hashlib
import secrets
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.print_agent import PrintAgent


class PrintAgentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    async def create_pairing(self, studio_id: int, name: str = "") -> PrintAgent:
        agent = PrintAgent(
            studio_id=studio_id,
            name=name,
            pairing_code=secrets.token_urlsafe(6),
        )
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def pair(self, code: str) -> Optional[Tuple[PrintAgent, str]]:
        agent = (await self.session.execute(
            select(PrintAgent).where(PrintAgent.pairing_code == code)
        )).scalar_one_or_none()
        if agent is None:
            return None
        raw = secrets.token_urlsafe(32)
        agent.token_hash = self._hash_token(raw)
        agent.pairing_code = None
        agent.paired_at = datetime.now()
        await self.session.commit()
        await self.session.refresh(agent)
        return agent, raw

    async def authenticate(self, token: str) -> Optional[PrintAgent]:
        if not token:
            return None
        agent = (await self.session.execute(
            select(PrintAgent).where(PrintAgent.token_hash == self._hash_token(token))
        )).scalar_one_or_none()
        return agent
```

- [ ] **Step 4: GREEN + полный сьют.** **Commit:** `feat: PrintAgentService — пайринг код→токен + аутентификация`

---

### Task 3: Print API — роутер, агент-аутентификация, POST /api/print/pair

**Files:**
- Create: `src/admin/print_api.py`
- Modify: `src/admin/app.py` (`app.include_router(...)`)
- Modify: `tests/admin/conftest.py` (добавить `headers` в `FakeRequest`, если ещё нет)
- Test: `tests/admin/test_print_api.py`

**Interfaces:**
- Produces:
  - `print_router = APIRouter(prefix="/api/print")`.
  - `async def resolve_agent(request, session) -> PrintAgent` — читает `Authorization: Bearer <token>` из `request.headers`, `PrintAgentService(session).authenticate(token)`; None → `HTTPException(401)`.
  - `POST /api/print/pair` — тело `{"code": "..."}` (pydantic-модель или Form/JSON); `PrintAgentService(session).pair(code)`; успех → `{"token": raw}`; неверный код → 404.
- Consumes: `PrintAgentService` (Task 2), `async_session`.

- [ ] **Step 1: Убедиться, что `FakeRequest` поддерживает headers**

В `tests/admin/conftest.py` `FakeRequest.__init__` уже принимает `self.headers = {}`. Если нет — добавить параметр `headers=None` → `self.headers = headers or {}`. (Проверить и при необходимости дополнить.)

- [ ] **Step 2: Тест `tests/admin/test_print_api.py`**

```python
"""Тесты Print API: пайринг + аутентификация."""
import os
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from src.services.studio_provisioning import provision_studio
from src.services.print_agent_service import PrintAgentService
from src.admin import print_api
from tests.admin.conftest import FakeRequest, use_test_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_pair_endpoint_returns_token(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                               admin_username="a", admin_password="p")
    agent = await PrintAgentService(db_session).create_pairing(s.id)
    resp = await print_api.pair(FakeRequest(), payload={"code": agent.pairing_code})
    assert "token" in resp
    assert resp["token"]


@pytest.mark.asyncio
async def test_pair_bad_code_404(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    with pytest.raises(HTTPException) as exc:
        await print_api.pair(FakeRequest(), payload={"code": "nope"})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_agent_valid_and_invalid(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                               admin_username="a", admin_password="p")
    agent = await PrintAgentService(db_session).create_pairing(s.id)
    _, raw = await PrintAgentService(db_session).pair(agent.pairing_code)

    req = FakeRequest(headers={"authorization": f"Bearer {raw}"})
    resolved = await print_api.resolve_agent(req, db_session)
    assert resolved.studio_id == s.id

    with pytest.raises(HTTPException) as exc:
        await print_api.resolve_agent(FakeRequest(headers={}), db_session)
    assert exc.value.status_code == 401
```

- [ ] **Step 3: RED.**

- [ ] **Step 4: Создать `src/admin/print_api.py`**

```python
"""HTTP Print API для локального агента печати (аутентификация по Bearer-токену)."""
from fastapi import APIRouter, Request, HTTPException, Body

from src.database import async_session
from src.models.print_agent import PrintAgent
from src.services.print_agent_service import PrintAgentService

print_router = APIRouter(prefix="/api/print")


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "") or request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


async def resolve_agent(request: Request, session) -> PrintAgent:
    token = _bearer(request)
    agent = await PrintAgentService(session).authenticate(token)
    if agent is None:
        raise HTTPException(status_code=401, detail="Неверный токен агента")
    return agent


@print_router.post("/pair")
async def pair(request: Request, payload: dict = Body(...)):
    code = (payload or {}).get("code", "")
    async with async_session() as session:
        result = await PrintAgentService(session).pair(code)
    if result is None:
        raise HTTPException(status_code=404, detail="Код не найден")
    _agent, raw = result
    return {"token": raw}
```

- [ ] **Step 5: Включить роутер в `src/admin/app.py`**

После создания `app` и импортов добавить:
```python
from src.admin.print_api import print_router
app.include_router(print_router)
```

- [ ] **Step 6: GREEN + полный сьют.** **Commit:** `feat: Print API — роутер + агент-аутентификация + пайринг /api/print/pair`

---

### Task 4: Админ-роут генерации кода пайринга

**Files:**
- Modify: `src/admin/app.py` (роут `POST /print-agent/pairing`)
- Test: `tests/admin/test_print_pairing_admin.py`

**Interfaces:**
- Consumes: `require_studio` (эффективная студия), `PrintAgentService`.
- Produces: `POST /print-agent/pairing` — `studio_id = require_studio(request)`; `agent = await PrintAgentService(session).create_pairing(studio_id, name=...)`; редирект назад с показом кода ИЛИ рендер простой страницы с `agent.pairing_code`. Для теста достаточно вернуть код в контексте/redirect query.

- [ ] **Step 1: Тест (прямой вызов; studio_admin создаёт код для СВОЕЙ студии)**

```python
import os, pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from src.services.studio_provisioning import provision_studio
from src.models.print_agent import PrintAgent
from tests.admin.conftest import FakeRequest, use_test_session, admin_session
from src.models.admin_user import AdminRole


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_studio_admin_creates_pairing_code(db_session, monkeypatch):
    app = use_test_session(monkeypatch, db_session)
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                               admin_username="a", admin_password="p")
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s.id))
    await app.create_print_pairing(req)
    agent = (await db_session.execute(
        select(PrintAgent).where(PrintAgent.studio_id == s.id))).scalar_one()
    assert agent.pairing_code
```

- [ ] **Step 2: RED → Step 3: реализовать роут в app.py:**

```python
@app.post("/print-agent/pairing")
async def create_print_pairing(request: Request):
    studio_id = require_studio(request)
    async with async_session() as session:
        agent = await PrintAgentService(session).create_pairing(studio_id)
    return RedirectResponse(f"/settings?pairing_code={agent.pairing_code}", status_code=303)
```
(Импортировать `PrintAgentService`. Показ кода на странице настроек — косметика, можно позже; тест проверяет создание записи.)

- [ ] **Step 4: GREEN + полный сьют.** **Commit:** `feat: админ-роут генерации кода пайринга агента печати`

---

### Task 5: GET /api/print/jobs — подтверждённые заказы студии

**Files:**
- Modify: `src/admin/print_api.py`
- Test: `tests/admin/test_print_jobs.py`

**Interfaces:**
- Consumes: `resolve_agent`, `OrderService(session, studio_id)`, `ProductService`, `Photo`, `OrderStatus`.
- Produces: `GET /api/print/jobs` → `{"jobs": [{"order_id", "order_number", "photos": [{"photo_id", "product_slug", "aspect_ratio", "crop_data", "position"}]}]}` для заказов студии агента в статусе `CONFIRMED`. Использует `OrderService(session, agent.studio_id).get_orders_by_status(OrderStatus.CONFIRMED)`; product_slug/aspect_ratio через `ProductService.get_product(agent.studio_id, photo.product_id)` после `load_cache(agent.studio_id)`.

- [ ] **Step 1: Тест изоляции + формы (агент A видит только заказы A в CONFIRMED)**

```python
import os, pytest
from cryptography.fernet import Fernet
from src.services.studio_provisioning import provision_studio
from src.services.print_agent_service import PrintAgentService
from src.services.order_service import OrderService
from src.models.order import OrderStatus
from src.models.photo import Photo
from src.admin import print_api
from tests.admin.conftest import FakeRequest, use_test_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


async def _confirmed_order(db_session, studio, tg=1):
    svc = OrderService(db_session, studio.id)
    user = await svc.get_or_create_user(telegram_id=tg)
    order = await svc.create_order(user)
    # используем товар из шаблона каталога студии
    from src.services.product_service import ProductService
    await ProductService(db_session).load_cache(studio.id)
    product = ProductService.get_all_purchasable(studio.id)[0]
    db_session.add(Photo(order_id=order.id, product_id=product.id,
                         telegram_file_id="f1", position=0, crop_data='{"x":0}'))
    await db_session.commit()
    await svc.update_order_status(order, OrderStatus.CONFIRMED)
    return order


async def _agent_req(db_session, studio):
    a = await PrintAgentService(db_session).create_pairing(studio.id)
    _, raw = await PrintAgentService(db_session).pair(a.pairing_code)
    return FakeRequest(headers={"authorization": f"Bearer {raw}"})


@pytest.mark.asyncio
async def test_jobs_returns_only_own_confirmed(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    b = await provision_studio(db_session, slug="b", name="B", bot_token="t", admin_username="b", admin_password="p")
    order_a = await _confirmed_order(db_session, a, tg=1)
    await _confirmed_order(db_session, b, tg=2)
    req = await _agent_req(db_session, a)

    result = await print_api.jobs(req)
    ids = [j["order_id"] for j in result["jobs"]]
    assert ids == [order_a.id]
    assert result["jobs"][0]["photos"][0]["crop_data"] == '{"x":0}'
    assert result["jobs"][0]["photos"][0]["product_slug"]
```

- [ ] **Step 2: RED → Step 3: реализовать в print_api.py:**

```python
from src.services.order_service import OrderService
from src.services.product_service import ProductService
from src.models.order import OrderStatus


@print_router.get("/jobs")
async def jobs(request: Request):
    async with async_session() as session:
        agent = await resolve_agent(request, session)
        sid = agent.studio_id
        await ProductService(session).load_cache(sid)
        orders = await OrderService(session, sid).get_orders_by_status(OrderStatus.CONFIRMED)
        result = []
        for order in orders:
            photos = []
            for p in sorted(order.photos, key=lambda x: x.position):
                prod = ProductService.get_product(sid, p.product_id)
                photos.append({
                    "photo_id": p.id,
                    "product_slug": prod.slug if prod else None,
                    "aspect_ratio": prod.aspect_ratio if prod else None,
                    "crop_data": p.crop_data,
                    "position": p.position,
                })
            result.append({"order_id": order.id, "order_number": order.order_number, "photos": photos})
    return {"jobs": result}
```

- [ ] **Step 4: GREEN + полный сьют.** **Commit:** `feat: GET /api/print/jobs — подтверждённые заказы студии агента`

---

### Task 6: GET /api/print/photo/{photo_id} — байты фото (студия-скоуп)

**Files:**
- Modify: `src/admin/print_api.py`
- Test: `tests/admin/test_print_photo.py`

**Interfaces:**
- Consumes: `resolve_agent`, `Photo`, `Order`, `Studio`, `decrypt_secret`, aiogram `Bot`.
- Produces: `GET /api/print/photo/{photo_id}` — находит фото по id ТОЛЬКО если его заказ принадлежит студии агента (`join Order, Order.studio_id == agent.studio_id`); иначе 404. Тянет байты из Telegram `Bot(token=decrypt_secret(studio.bot_token)).get_file/download_file`, отдаёт `StreamingResponse(image/jpeg)`.

- [ ] **Step 1: Тест изоляции (агент A по фото студии B → 404). Bot-загрузку мокаем.**

```python
import os, io, pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from src.services.studio_provisioning import provision_studio
from src.services.print_agent_service import PrintAgentService
from src.services.order_service import OrderService
from src.models.photo import Photo
from src.admin import print_api
from tests.admin.conftest import FakeRequest, use_test_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


async def _order_photo(db_session, studio, tg=1):
    svc = OrderService(db_session, studio.id)
    user = await svc.get_or_create_user(telegram_id=tg)
    order = await svc.create_order(user)
    from src.services.product_service import ProductService
    await ProductService(db_session).load_cache(studio.id)
    product = ProductService.get_all_purchasable(studio.id)[0]
    photo = Photo(order_id=order.id, product_id=product.id, telegram_file_id="f1", position=0)
    db_session.add(photo); await db_session.commit()
    return photo


async def _agent_req(db_session, studio):
    a = await PrintAgentService(db_session).create_pairing(studio.id)
    _, raw = await PrintAgentService(db_session).pair(a.pairing_code)
    return FakeRequest(headers={"authorization": f"Bearer {raw}"})


@pytest.mark.asyncio
async def test_photo_foreign_studio_404(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    b = await provision_studio(db_session, slug="b", name="B", bot_token="t", admin_username="b", admin_password="p")
    photo_b = await _order_photo(db_session, b, tg=2)
    req_a = await _agent_req(db_session, a)
    with pytest.raises(HTTPException) as exc:
        await print_api.photo(req_a, photo_id=photo_b.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_photo_own_studio_streams(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    photo_a = await _order_photo(db_session, a, tg=1)
    req_a = await _agent_req(db_session, a)

    # мок загрузки из Telegram
    class _FakeFile: file_path = "x.jpg"
    class _FakeBot:
        def __init__(self, token): pass
        async def get_file(self, fid): return _FakeFile()
        async def download_file(self, path): return io.BytesIO(b"IMG")
        @property
        def session(self):
            class _S:
                async def close(self): pass
            return _S()
    monkeypatch.setattr(print_api, "Bot", _FakeBot)

    resp = await print_api.photo(req_a, photo_id=photo_a.id)
    assert resp.status_code == 200
```

- [ ] **Step 2: RED → Step 3: реализовать в print_api.py:**

```python
import io
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from aiogram import Bot
from src.models.photo import Photo
from src.models.order import Order
from src.models.studio import Studio
from src.services.crypto import decrypt_secret


@print_router.get("/photo/{photo_id}")
async def photo(request: Request, photo_id: int):
    async with async_session() as session:
        agent = await resolve_agent(request, session)
        row = (await session.execute(
            select(Photo, Studio)
            .join(Order, Photo.order_id == Order.id)
            .join(Studio, Order.studio_id == Studio.id)
            .where(Photo.id == photo_id, Order.studio_id == agent.studio_id)
        )).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Фото не найдено")
        photo_obj, studio = row
        if not studio.bot_token:
            raise HTTPException(status_code=409, detail="У студии нет токена бота")
        bot = Bot(token=decrypt_secret(studio.bot_token))
        try:
            f = await bot.get_file(photo_obj.telegram_file_id)
            data = await bot.download_file(f.file_path)
        finally:
            await bot.session.close()
    return StreamingResponse(io.BytesIO(data.read()), media_type="image/jpeg")
```

- [ ] **Step 4: GREEN + полный сьют.** **Commit:** `feat: GET /api/print/photo/{id} — байты фото по студии агента`

---

### Task 7: POST /api/print/report — billing_events + статус заказа (идемпотентно)

**Files:**
- Modify: `src/admin/print_api.py`
- Test: `tests/admin/test_print_report.py`

**Interfaces:**
- Consumes: `resolve_agent`, `OrderService(session, studio_id)`, `BillingEvent`, `Studio.platform_fee_per_photo`, `OrderStatus`.
- Produces: `POST /api/print/report` — тело `{"order_id", "printed_photo_ids": [...]}`. Проверяет: заказ принадлежит студии агента (`OrderService(session, sid).get_order_by_id(order_id)`; None → 404). Для каждого `photo_id` из заказа, по которому ещё НЕТ `billing_event` (идемпотентность по (studio_id, order_id, photo_position)), создаёт `BillingEvent(studio_id, order_id, photo_position=photo.position, fee=studio.platform_fee_per_photo, printed_at=now)`. Двигает статус заказа: если все фото заказа отрапортованы → `READY`, иначе `PRINTING`. Возвращает `{"billed": <кол-во новых событий>}`.

- [ ] **Step 1: Тест (идемпотентность + fee snapshot + изоляция).** Ключевые проверки:
  - рапорт 2 фото → 2 billing_event, `fee == studio.platform_fee_per_photo`, статус PRINTING/READY;
  - повторный рапорт тех же → 0 новых (идемпотентно);
  - агент студии A по `order_id` студии B → 404.

```python
import os, pytest
from decimal import Decimal
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select, func
from src.services.studio_provisioning import provision_studio
from src.services.print_agent_service import PrintAgentService
from src.services.order_service import OrderService
from src.services.product_service import ProductService
from src.models.order import OrderStatus
from src.models.photo import Photo
from src.models.billing_event import BillingEvent
from src.admin import print_api
from tests.admin.conftest import FakeRequest, use_test_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


async def _order_with_photos(db_session, studio, n=2, tg=1):
    svc = OrderService(db_session, studio.id)
    user = await svc.get_or_create_user(telegram_id=tg)
    order = await svc.create_order(user)
    await ProductService(db_session).load_cache(studio.id)
    product = ProductService.get_all_purchasable(studio.id)[0]
    ids = []
    for i in range(n):
        p = Photo(order_id=order.id, product_id=product.id, telegram_file_id=f"f{i}", position=i)
        db_session.add(p)
    await db_session.commit()
    await svc.update_order_status(order, OrderStatus.CONFIRMED)
    order = await svc.get_order_by_id(order.id)
    ids = [p.id for p in order.photos]
    return order, ids


async def _agent_req(db_session, studio):
    a = await PrintAgentService(db_session).create_pairing(studio.id)
    _, raw = await PrintAgentService(db_session).pair(a.pairing_code)
    return FakeRequest(headers={"authorization": f"Bearer {raw}"})


@pytest.mark.asyncio
async def test_report_creates_billing_idempotent(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    order, photo_ids = await _order_with_photos(db_session, a, n=2)
    req = await _agent_req(db_session, a)

    r1 = await print_api.report(req, payload={"order_id": order.id, "printed_photo_ids": photo_ids})
    assert r1["billed"] == 2
    count = (await db_session.execute(
        select(func.count(BillingEvent.id)).where(BillingEvent.order_id == order.id))).scalar()
    assert count == 2
    ev = (await db_session.execute(select(BillingEvent).limit(1))).scalar_one()
    assert ev.fee == Decimal("5.00")
    # повторный рапорт — идемпотентно
    r2 = await print_api.report(req, payload={"order_id": order.id, "printed_photo_ids": photo_ids})
    assert r2["billed"] == 0


@pytest.mark.asyncio
async def test_report_foreign_order_404(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    b = await provision_studio(db_session, slug="b", name="B", bot_token="t", admin_username="b", admin_password="p")
    order_b, ids_b = await _order_with_photos(db_session, b, n=1, tg=2)
    req_a = await _agent_req(db_session, a)
    with pytest.raises(HTTPException) as exc:
        await print_api.report(req_a, payload={"order_id": order_b.id, "printed_photo_ids": ids_b})
    assert exc.value.status_code == 404
```

- [ ] **Step 2: RED → Step 3: реализовать в print_api.py:**

```python
from datetime import datetime
from src.models.billing_event import BillingEvent


@print_router.post("/report")
async def report(request: Request, payload: dict = Body(...)):
    order_id = (payload or {}).get("order_id")
    printed_ids = set((payload or {}).get("printed_photo_ids") or [])
    async with async_session() as session:
        agent = await resolve_agent(request, session)
        sid = agent.studio_id
        order_svc = OrderService(session, sid)
        order = await order_svc.get_order_by_id(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        studio = (await session.execute(
            select(Studio).where(Studio.id == sid))).scalar_one()
        # уже оттарифицированные позиции этого заказа
        billed_positions = set((await session.execute(
            select(BillingEvent.photo_position).where(BillingEvent.order_id == order.id)
        )).scalars().all())
        billed = 0
        for p in order.photos:
            if p.id in printed_ids and p.position not in billed_positions:
                session.add(BillingEvent(
                    studio_id=sid, order_id=order.id, photo_position=p.position,
                    fee=studio.platform_fee_per_photo, printed_at=datetime.now(),
                ))
                billed_positions.add(p.position)
                billed += 1
        # статус заказа
        total_positions = {p.position for p in order.photos}
        new_status = OrderStatus.READY if billed_positions >= total_positions else OrderStatus.PRINTING
        await order_svc.update_order_status(order, new_status)
        await session.commit()
    return {"billed": billed}
```

- [ ] **Step 4: GREEN + полный сьют.** **Commit:** `feat: POST /api/print/report — billing_events (идемпотентно) + статус заказа`

---

### Task 8: POST /api/print/health — heartbeat

**Files:**
- Modify: `src/admin/print_api.py`
- Test: `tests/admin/test_print_health.py`

**Interfaces:**
- Produces: `POST /api/print/health` — тело `{"printer_status": str, "queue_len": int}`; обновляет `agent.last_seen_at=now`, `printer_status`, `queue_len`; возвращает `{"ok": true}`.

- [ ] **Step 1: Тест** — после health у агента обновлены `printer_status`/`queue_len`/`last_seen_at`.

```python
import os, pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from src.services.studio_provisioning import provision_studio
from src.services.print_agent_service import PrintAgentService
from src.models.print_agent import PrintAgent
from src.admin import print_api
from tests.admin.conftest import FakeRequest, use_test_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_health_updates_agent(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t", admin_username="a", admin_password="p")
    ag = await PrintAgentService(db_session).create_pairing(s.id)
    _, raw = await PrintAgentService(db_session).pair(ag.pairing_code)
    req = FakeRequest(headers={"authorization": f"Bearer {raw}"})

    resp = await print_api.health(req, payload={"printer_status": "ready", "queue_len": 3})
    assert resp["ok"] is True
    reloaded = (await db_session.execute(
        select(PrintAgent).where(PrintAgent.id == ag.id))).scalar_one()
    assert reloaded.printer_status == "ready"
    assert reloaded.queue_len == 3
    assert reloaded.last_seen_at is not None
```

- [ ] **Step 2: RED → Step 3: реализовать в print_api.py:**

```python
@print_router.post("/health")
async def health(request: Request, payload: dict = Body(...)):
    async with async_session() as session:
        agent = await resolve_agent(request, session)
        agent.printer_status = str((payload or {}).get("printer_status", ""))[:255]
        agent.queue_len = int((payload or {}).get("queue_len", 0) or 0)
        agent.last_seen_at = datetime.now()
        await session.commit()
    return {"ok": True}
```

- [ ] **Step 4: GREEN + полный сьют.** **Commit:** `feat: POST /api/print/health — heartbeat агента`

---

## Что остаётся для следующих планов (№2)

- **2-II — ядро агента:** пайринг-клиент (обмен кода на токен через `/api/print/pair`), pull `/jobs`, скачивание `/photo/{id}`, применение crop + сборка макетов (Pillow), локальный конфиг макетов с дефолтами. Тестируется на любой ОС.
- **2-III — Windows-печать** (спулер) + очередь-UI + упаковка .exe + вызов `/health`.
- Показ кода пайринга и статуса агента в админке (супер-админ /studios) — косметика, можно в 2-III или отдельно.
- Мультиагентность/координация — отложено (v1: один агент на студию).

## Self-Review

- **Покрытие спека 2-I:** PrintAgent (Task 1), пайринг/аутентификация (Task 2), /pair (Task 3), генерация кода в админке (Task 4), /jobs (Task 5), /photo (Task 6), /report+billing (Task 7), /health (Task 8). Изоляция — тесты в Tasks 5,6,7.
- **Плейсхолдеры:** отсутствуют — полный код в каждом шаге.
- **Согласованность:** `PrintAgentService(session)` методы (create_pairing/pair/authenticate/_hash_token), `resolve_agent(request, session)`, эндпоинты `print_api.pair/jobs/photo/report/health` — сигнатуры совпадают между определением и тестами. `BillingEvent(studio_id, order_id, photo_position, fee, printed_at)` — как в модели. Идемпотентность по `photo_position` в рамках заказа.
- **Тесты:** прямой вызов функций-эндпоинтов (без TestClient), изоляция студий — красная нить.
