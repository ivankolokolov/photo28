# Роли админки + CRUD студий + kill-switch — План реализации (под-проект №1, план 2c)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать FastAPI-админку мультитенантной и безопасной: вход через `admin_users` (bcrypt), роли super_admin/studio_admin, все роуты и сервисы зажаты на «эффективную студию», супер-админ управляет студиями (создание/kill-switch/«смотреть как студия»); бот-процесс подхватывает создание/отключение студий через реконсиляцию реестра.

**Architecture:** Сессия после логина хранит `user_id/username/role/studio_id`. «Эффективная студия» = `studio_id` для studio_admin (зафиксирован), либо выбранная супер-админом `active_studio_id` (для «смотреть как студия»). Зависимость `get_current_admin`/`require_studio` отдаёт роутам эффективный `studio_id`. Все вызовы сервисов получают этот `studio_id`. Супер-админ имеет раздел `/studios` (список/создать/toggle is_active/view-as). Бот (webhook-процесс из 2b) получает периодический reconcile-цикл: сверяет активные студии в БД со своим `StudioBotRegistry` и регистрирует/снимает их (set/delete webhook) — так создание студии в админке и kill-switch доезжают до бота без общей памяти между процессами.

**Tech Stack:** Python 3.9+, FastAPI + Starlette SessionMiddleware, Jinja2, SQLAlchemy 2.0 async, PostgreSQL, aiohttp (бот), pytest + pytest-asyncio + httpx (FastAPI TestClient).

## Global Constraints

- Python 3.9+. Проектный venv: `/Users/user/Work/photo28/.venv/bin/python -m pytest`.
- PostgreSQL только; тесты на `TEST_DATABASE_URL` (`photo28_test`); `db_session` пересоздаёт схему per-test; `FERNET_KEY` — autouse-фикстура где нужен.
- Авторизация ТОЛЬКО через `admin_users` (bcrypt `verify_password`); хардкод `settings.admin_username/password` удалить из логики входа.
- Роли: `super_admin` (studio_id=NULL, видит все студии, может «смотреть как студия») и `studio_admin` (зажат своим `studio_id`).
- «Эффективная студия»: studio_admin → его `studio_id`; super_admin → `session["active_studio_id"]` (None, пока не выбрал). Роуты с данными требуют выбранной студии.
- Изоляция: studio_admin НИКОГДА не видит/не меняет данные чужой студии (главный тест безопасности). Все сервисы вызываются со studio_id; CRUD промокодов/товаров/настроек фильтруется по studio_id; редактирование/удаление товара проверяет принадлежность студии.
- Бот — один webhook-процесс на все студии (2b). RESTART-сигнал из polling-эпохи устарел — заменяется reconcile-циклом; старые `/bot-control/restart-*` роуты удаляются.
- Пристойный вывод тестов под `-W error`. Commit-сообщения на русском.
- Carry-forwards, закрываемые здесь: `ProductService.get_product_by_id` → проверка студии при update/delete/toggle; `get_storage_stats` per-studio; webhook-эндпоинт top-level try/except; guard на пустой `base_webhook_url` при старте. `SettingsFacade` layering — опционально, можно оставить на потом.

## Карта файлов

Создаётся:
- `src/admin/auth.py` — `get_current_admin`, `require_studio`, `require_super_admin`, логин-хелперы.
- `src/admin/templates/studios.html` — супер-админ список студий.
- `scripts/seed_admin.py` — CLI создания super_admin.
- `src/bot/reconcile.py` — `reconcile_studios(registry, session)`.
- `tests/admin/__init__.py`, `tests/admin/conftest.py` — TestClient-фикстуры (логин под ролью).
- тесты под задачи.

Модифицируется:
- `requirements.txt` — `httpx` (тест-зависимость).
- `src/admin/app.py` — авторизация, все роуты на эффективную студию, NotificationService 4-арг, удаление restart-роутов, `/studios*` роуты, startup без глобального load_cache.
- `src/services/analytics_service.py` — studio_id во все методы.
- `src/services/file_service.py` — `get_storage_stats(studio_id)` per-studio (carry-forward).
- `src/services/product_service.py` — `get_product_by_id` со studio-проверкой ИЛИ guard в update/delete/toggle (carry-forward).
- `src/admin/templates/base.html` — навигация: индикатор роли/студии, ссылка «Студии» для super_admin, убрать «Бот».
- `src/admin/templates/order_detail.html` — имена товаров резолвятся в роуте (не передавать класс ProductService).
- `main.py` + `src/bot/webhook_app.py` + `src/bot/lifecycle.py` — reconcile-цикл, try/except в эндпоинте, guard base_webhook_url.

---

### Task 1: Тест-инфраструктура админки (httpx + TestClient-фикстуры)

**Files:**
- Modify: `requirements.txt`
- Create: `tests/admin/__init__.py`, `tests/admin/conftest.py`
- Test: `tests/admin/test_admin_infra.py`

**Interfaces:**
- Produces: фикстура/хелпер `make_admin_client(app, db_session)` и `login_as(client, username, password)` для интеграционных тестов админки; helper `seed_super_admin(session, username, password)` и `seed_studio_admin(session, studio, username, password)`.
- ВАЖНО: тесты админки должны использовать ТЕСТОВУЮ БД. `src/admin/app.py` использует `async_session` из `src.database` (рабочая БД). Фикстура должна подменять `async_session` модуля app на тестовую (monkeypatch на `src.admin.app.async_session`, возвращающую контекст с `db_session`), либо TestClient + dependency override. Решение: monkeypatch `async_session` в app-модуле на фабрику, отдающую `db_session` (как делали для StudioMiddleware-теста в 2b).

- [ ] **Step 1: Добавить httpx в requirements.txt**

В секцию Tests:
```
httpx==0.27.0
```

- [ ] **Step 2: Установить**

Run: `/Users/user/Work/photo28/.venv/bin/pip install "httpx==0.27.0"`
Expected: установлен httpx (и его зависимости).

- [ ] **Step 3: Создать `tests/admin/__init__.py`** (пустой) и `tests/admin/conftest.py`**

```python
"""Фикстуры для интеграционных тестов админки."""
import contextlib
import pytest
from fastapi.testclient import TestClient

from src.services.studio_provisioning import provision_studio
from src.services.auth import hash_password
from src.models.admin_user import AdminUser, AdminRole


def _session_factory(db_session):
    @contextlib.asynccontextmanager
    async def _factory():
        yield db_session
    return _factory


@pytest.fixture
def admin_client(db_session, monkeypatch):
    """TestClient с подменённым async_session на тестовую сессию."""
    import src.admin.app as app_module
    monkeypatch.setattr(app_module, "async_session", _session_factory(db_session))
    with TestClient(app_module.app) as client:
        yield client


async def seed_super_admin(db_session, username="root", password="pw"):
    admin = AdminUser(username=username, password_hash=hash_password(password),
                      role=AdminRole.SUPER_ADMIN, studio_id=None)
    db_session.add(admin)
    await db_session.commit()
    return admin


async def seed_studio_admin(db_session, studio, username, password="pw"):
    admin = AdminUser(username=username, password_hash=hash_password(password),
                      role=AdminRole.STUDIO_ADMIN, studio_id=studio.id)
    db_session.add(admin)
    await db_session.commit()
    return admin


def login(client, username, password):
    return client.post("/login", data={"username": username, "password": password},
                       follow_redirects=False)
```

- [ ] **Step 4: Создать `tests/admin/test_admin_infra.py`**

```python
"""Проверка тестовой инфраструктуры админки."""
import os
import pytest
from cryptography.fernet import Fernet
from tests.admin.conftest import seed_super_admin, login


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_login_page_renders(admin_client, db_session):
    resp = admin_client.get("/login")
    assert resp.status_code == 200
```

(Полные логин-тесты — в Task 2, когда auth переключён на AdminUser.)

- [ ] **Step 5: Запустить**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/admin/test_admin_infra.py -W error -v`
Expected: PASS (login-страница рендерится текущим кодом).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt tests/admin/
git commit -m "chore: httpx + тестовая инфраструктура админки (TestClient-фикстуры)"
```

---

### Task 2: Авторизация через AdminUser + роли + эффективная студия

**Files:**
- Create: `src/admin/auth.py`
- Create: `scripts/seed_admin.py`
- Modify: `src/admin/app.py` (login/logout/check_auth → AdminUser; подключить зависимости)
- Test: `tests/admin/test_auth.py`

**Interfaces:**
- Produces (`src/admin/auth.py`):
  - `async def authenticate(session, username, password) -> Optional[AdminUser]` — ищет AdminUser, `verify_password`.
  - `def current_admin(request) -> dict | None` — из сессии `{user_id, username, role, studio_id}` или None.
  - `def effective_studio_id(request) -> Optional[int]` — studio_admin → его `studio_id`; super_admin → `session.get("active_studio_id")`.
  - FastAPI-зависимости: `require_admin(request)` (303 на /login если не залогинен), `require_studio(request)` (отдаёт int studio_id или 303/400 если super_admin не выбрал студию), `require_super_admin(request)` (403 если не super_admin).
- `src/admin/app.py` login: `authenticate(...)`, при успехе пишет в сессию `user_id/username/role/studio_id`; logout очищает; удалить сравнение с `settings.admin_username/password`.

- [ ] **Step 1: Тест `tests/admin/test_auth.py`**

```python
import os
import pytest
from cryptography.fernet import Fernet
from src.services.studio_provisioning import provision_studio
from tests.admin.conftest import seed_super_admin, seed_studio_admin, login


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_login_success_sets_session(admin_client, db_session):
    await seed_super_admin(db_session, "root", "pw")
    resp = login(admin_client, "root", "pw")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


@pytest.mark.asyncio
async def test_login_wrong_password(admin_client, db_session):
    await seed_super_admin(db_session, "root", "pw")
    resp = login(admin_client, "root", "WRONG")
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]


@pytest.mark.asyncio
async def test_studio_admin_dashboard_scoped(admin_client, db_session):
    studio = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                                    admin_username="ignored", admin_password="x")
    await seed_studio_admin(db_session, studio, "owner1", "pw")
    login(admin_client, "owner1", "pw")
    resp = admin_client.get("/", follow_redirects=False)
    assert resp.status_code == 200  # studio_admin сразу на своей студии


@pytest.mark.asyncio
async def test_unauthenticated_redirected(admin_client, db_session):
    resp = admin_client.get("/", follow_redirects=False)
    assert resp.status_code in (303, 307)
    assert "/login" in resp.headers["location"]
```

- [ ] **Step 2: RED**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/admin/test_auth.py -v`
Expected: FAIL (логин ещё на хардкоде/нет AdminUser-проверки; dashboard не зажат).

- [ ] **Step 3: Создать `src/admin/auth.py`**

```python
"""Авторизация и роли админки."""
from typing import Optional
from fastapi import Request, HTTPException
from sqlalchemy import select

from src.models.admin_user import AdminUser, AdminRole
from src.services.auth import verify_password


async def authenticate(session, username: str, password: str) -> Optional[AdminUser]:
    admin = (await session.execute(
        select(AdminUser).where(AdminUser.username == username)
    )).scalar_one_or_none()
    if admin and verify_password(password, admin.password_hash):
        return admin
    return None


def current_admin(request: Request) -> Optional[dict]:
    if not request.session.get("user_id"):
        return None
    return {
        "user_id": request.session["user_id"],
        "username": request.session.get("username"),
        "role": request.session.get("role"),
        "studio_id": request.session.get("studio_id"),
    }


def effective_studio_id(request: Request) -> Optional[int]:
    admin = current_admin(request)
    if not admin:
        return None
    if admin["role"] == AdminRole.STUDIO_ADMIN.value:
        return admin["studio_id"]
    return request.session.get("active_studio_id")


def require_admin(request: Request) -> dict:
    admin = current_admin(request)
    if not admin:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return admin


def require_super_admin(request: Request) -> dict:
    admin = require_admin(request)
    if admin["role"] != AdminRole.SUPER_ADMIN.value:
        raise HTTPException(status_code=403, detail="Только для супер-админа")
    return admin


def require_studio(request: Request) -> int:
    admin = require_admin(request)
    sid = effective_studio_id(request)
    if sid is None:
        # super_admin без выбранной студии → на список студий
        raise HTTPException(status_code=303, headers={"Location": "/studios"})
    return sid
```

- [ ] **Step 4: Переключить login/logout в `src/admin/app.py`**

Заменить тело `login` (строки ~133-148): rate-limit оставить; вместо сравнения с settings —
```python
    async with async_session() as session:
        admin = await authenticate(session, username, password)
    if admin:
        request.session["user_id"] = admin.id
        request.session["username"] = admin.username
        request.session["role"] = admin.role.value
        request.session["studio_id"] = admin.studio_id
        _login_attempts.pop(client_ip, None)
        return RedirectResponse("/", status_code=303)
    _record_login_attempt(client_ip)
    return RedirectResponse("/login?error=invalid", status_code=303)
```
Импортировать `from src.admin.auth import authenticate, require_admin, require_studio, require_super_admin, current_admin, effective_studio_id`. `logout` — `request.session.clear()`. Удалить старый `check_auth`-хардкод (заменить на зависимости в роутах — Task 4+). Startup-event: убрать глобальный `load_cache()` без studio_id (кеши греются per-request в Task 4+ или per-studio при reconcile — на этом шаге просто убрать сломанный вызов, чтобы приложение стартовало).

- [ ] **Step 5: GREEN + полный сьют**

Run: `/Users/user/Work/photo28/.venv/bin/python -m pytest tests/admin/test_auth.py -W error -v` затем полный `-W error`.
Expected: PASS. (dashboard-роут зажимается в Task 4; пока `test_studio_admin_dashboard_scoped` может потребовать заглушку — если dashboard ещё не мигрирован, временно проверяйте редирект на /login отсутствует; финально закрепится в Task 4. Реализатору: если dashboard ещё падает, перенесите ассерт «200» в Task 4, а здесь проверьте, что после логина GET / НЕ редиректит на /login.)

- [ ] **Step 6: Создать CLI `scripts/seed_admin.py`**

```python
"""CLI: создать super_admin. python -m scripts.seed_admin --username root --password ..."""
import argparse, asyncio
from src.database import async_session, init_db
from src.services.auth import hash_password
from src.models.admin_user import AdminUser, AdminRole


async def _run(args):
    await init_db()
    async with async_session() as session:
        session.add(AdminUser(username=args.username, password_hash=hash_password(args.password),
                              role=AdminRole.SUPER_ADMIN, studio_id=None))
        await session.commit()
    print(f"super_admin '{args.username}' создан")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--username", required=True); p.add_argument("--password", required=True)
    asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Commit**

```bash
git add src/admin/auth.py scripts/seed_admin.py src/admin/app.py tests/admin/test_auth.py
git commit -m "feat: авторизация админки через AdminUser + роли + эффективная студия"
```

---

### Task 3: Супер-админ — управление студиями (/studios, создать, kill-switch, view-as)

**Files:**
- Modify: `src/admin/app.py` (роуты /studios)
- Create: `src/admin/templates/studios.html`
- Test: `tests/admin/test_studios.py`

**Interfaces:**
- Consumes: `provision_studio`, `require_super_admin`, `Studio`, `crypto.encrypt_secret`.
- Produces роуты (только super_admin):
  - `GET /studios` — список всех студий (id, slug, name, is_active, bot_username).
  - `POST /studios` — создать: form (slug, name, bot_token, admin_username, admin_password) → `provision_studio(...)`.
  - `POST /studios/{id}/toggle` — kill-switch: инвертировать `is_active`.
  - `POST /studios/{id}/view-as` — записать `request.session["active_studio_id"] = id`, редирект на `/`.
  - `POST /studios/exit-view` — `session.pop("active_studio_id")`.

- [ ] **Step 1: Тест `tests/admin/test_studios.py`**

```python
import os, pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from src.services.studio_provisioning import provision_studio
from src.models.studio import Studio
from tests.admin.conftest import seed_super_admin, seed_studio_admin, login


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_super_admin_lists_studios(admin_client, db_session):
    await provision_studio(db_session, slug="s1", name="S1", bot_token="t", admin_username="a", admin_password="x")
    await seed_super_admin(db_session, "root", "pw")
    login(admin_client, "root", "pw")
    resp = admin_client.get("/studios")
    assert resp.status_code == 200
    assert "S1" in resp.text


@pytest.mark.asyncio
async def test_studio_admin_forbidden_from_studios(admin_client, db_session):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t", admin_username="a", admin_password="x")
    await seed_studio_admin(db_session, s, "owner", "pw")
    login(admin_client, "owner", "pw")
    resp = admin_client.get("/studios", follow_redirects=False)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_toggle_killswitch(admin_client, db_session):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t", admin_username="a", admin_password="x")
    await seed_super_admin(db_session, "root", "pw")
    login(admin_client, "root", "pw")
    admin_client.post(f"/studios/{s.id}/toggle", follow_redirects=False)
    reloaded = (await db_session.execute(select(Studio).where(Studio.id == s.id))).scalar_one()
    assert reloaded.is_active is False


@pytest.mark.asyncio
async def test_view_as_sets_active_studio(admin_client, db_session):
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t", admin_username="a", admin_password="x")
    await seed_super_admin(db_session, "root", "pw")
    login(admin_client, "root", "pw")
    resp = admin_client.post(f"/studios/{s.id}/view-as", follow_redirects=False)
    assert resp.status_code == 303
    # после view-as дашборд доступен
    assert admin_client.get("/", follow_redirects=False).status_code == 200
```

- [ ] **Step 2: RED → Step 3: реализовать роуты + шаблон → Step 4: GREEN.**

Роуты (эскиз; реализатор уточняет рендер): используют `require_super_admin`; `GET /studios` грузит `select(Studio).order_by(Studio.id)`, рендерит `studios.html`; `POST /studios` зовёт `provision_studio`; toggle инвертирует is_active+commit; view-as пишет session. `studios.html` наследует base.html, таблица студий + форма создания + кнопки toggle/view-as.

Run focused + full `-W error`. Commit: `git add src/admin/app.py src/admin/templates/studios.html tests/admin/test_studios.py && git commit -m "feat: супер-админ — список/создание/kill-switch/view-as студий"`.

---

### Task 4: Миграция роутов заказов на эффективную студию (+ NotificationService + order_detail)

**Files:**
- Modify: `src/admin/app.py` (dashboard, orders, order_detail, status, download, upload-yandex, photos, send_client_notification helper)
- Modify: `src/admin/templates/order_detail.html` (имена товаров из роута)
- Test: `tests/admin/test_orders_isolation.py`

**Контракт:** каждый роут получает `studio_id: int = Depends(require_studio)`; `OrderService(session)` → `OrderService(session, studio_id)`; `send_client_notification` строит `NotificationService(bot, studio, SettingsFacade(studio_id), ProductsFacade(studio_id))` (грузит Studio + кеши); order_detail резолвит имена товаров в роуте (`ProductService.get_product(studio_id, pid)` после load_cache) и передаёт готовый dict в шаблон вместо класса. FileService для скачивания — без изменений (работает по order). Перед `OrderService`/`ProductService` вызовами грузить кеши нужной студии (`SettingsService(session).load_cache(studio_id)`, `ProductService(session).load_cache(studio_id)`).

**Главный тест — изоляция:**
```python
# studio_admin студии A не видит заказ студии B (404), и /orders показывает только свои.
```

- [ ] Steps: тест изоляции (studio_admin A → GET /orders/{B_order_id} == 404; dashboard/orders只 свои) → RED → миграция роутов → GREEN → full `-W error`. Commit: `refactor: роуты заказов админки на эффективную студию + NotificationService`.

---

### Task 5: Миграция промокодов на studio_id (CRUD с фильтром)

**Files:** Modify `src/admin/app.py` (promocodes list/create/delete/toggle); Test `tests/admin/test_promocodes_isolation.py`.

**Контракт:** list — `select(Promocode).where(Promocode.studio_id == studio_id)`; create — `Promocode(studio_id=studio_id, ...)`; delete/toggle — `select(Promocode).where(Promocode.id==id, Promocode.studio_id==studio_id)` (None → 404, нельзя трогать чужой). Все через `Depends(require_studio)`.

- [ ] Тест: studio_admin A не может удалить/переключить промокод студии B (404), не видит его в списке → RED → миграция → GREEN → commit `refactor: промокоды админки со studio_id-фильтром`.

---

### Task 6: Миграция настроек и товаров + guard принадлежности товара (carry-forward)

**Files:** Modify `src/admin/app.py` (settings get/post, products list/create/update/toggle/delete); Modify `src/services/product_service.py` (studio-проверка в update/delete/toggle); Test `tests/admin/test_settings_products_isolation.py`.

**Контракт:**
- settings: `SettingsService(session).get_all(studio_id)` / `set_value(studio_id, key, value)`; перед рендером `load_cache(studio_id)`.
- products: `get_all_products(studio_id)`, `create_product(studio_id, ...)`.
- **carry-forward (изоляция):** `ProductService.update_product/delete_product/toggle_product` сейчас находят товар по `get_product_by_id` без studio. Добавить параметр `studio_id` (или проверку `product.studio_id == studio_id` → если не совпадает, вернуть None/False). Админ-роуты передают эффективный `studio_id`. Тест: studio_admin A не может изменить/удалить товар студии B.

- [ ] Тест изоляции settings+products → RED → миграция + guard → GREEN → commit `refactor: настройки/товары админки со studio_id + guard принадлежности товара`.

---

### Task 7: AnalyticsService → studio_id + роут /analytics; api/photos, api/crop/save; get_storage_stats

**Files:** Modify `src/services/analytics_service.py`, `src/services/file_service.py`, `src/admin/app.py`; Test `tests/services/test_analytics_tenancy.py`, `tests/admin/test_analytics_isolation.py`.

**Контракт:**
- AnalyticsService: добавить `studio_id` параметром во все методы, использующие заказы/клиентов (`get_revenue_stats`, `get_revenue_by_days`, `get_orders_by_status`, `get_format_stats`, `get_delivery_stats`, `get_photos_to_print`, `get_customer_stats`, `get_top_customers`, `get_conversion_stats`, `get_dashboard_summary`); каждый SELECT по Order фильтровать `Order.studio_id == studio_id`. Конструктор можно оставить `(session)` и передавать studio_id в методы, ИЛИ `(session, studio_id)` — выбрать `(session, studio_id)` для единообразия с OrderService и хранить self.studio_id.
- `/analytics` роут: `AnalyticsService(session, studio_id)` через `require_studio`.
- `api/photos/{order_id}` и `api/crop/save`: эти Mini-App API вызываются с order_id+token (не сессией). studio_id берётся из самого заказа: загрузить заказ глобально по id (или резолвить студию по order.studio_id), затем строить сервисы с `order.studio_id`. ProductService.get_product(order.studio_id, ...). get_delivery_keyboard(ctx) — построить ctx по order.studio_id. (Тут нет admin-сессии — это публичный Mini-App с токеном; токен уже проверяется `verify_api_token`.)
- `FileService.get_storage_stats(studio_id)` (carry-forward): считать только `photos_dir/{studio_id}/...` (двухуровневый обход внутри студии); dashboard передаёт эффективный studio_id.

- [ ] Тесты: analytics studio-scoped (две студии, разная выручка); admin /analytics изоляция → RED → миграция → GREEN → commit `feat: studio-скоупленная аналитика + Mini-App API + get_storage_stats по студии`.

---

### Task 8: Бот — reconcile-цикл студий + 2b carry-forwards

**Files:** Create `src/bot/reconcile.py`; Modify `main.py`, `src/bot/webhook_app.py`, `src/bot/lifecycle.py`, `src/admin/app.py` (удалить /bot-control restart-роуты); Test `tests/bot/test_reconcile.py`.

**Контракт:**
- `src/bot/reconcile.py`: `async def reconcile_studios(registry, session) -> tuple[int,int]` — сравнивает активные студии в БД (`load_active_studios`) с `registry` по studio_id: для новых активных, которых нет в реестре → `register_studio(registry, studio)` (+ счётчик added); для студий в реестре, которых больше нет среди активных (отключены/удалены) → `unregister_studio(registry, sid)` (+ removed). Возвращает (added, removed).
- `main.py`: добавить периодический `_reconcile_loop` (интервал, напр. 30с) рядом с cleanup-loop; он подхватывает создание студий и kill-switch из админки без общей памяти.
- `lifecycle.register_studio`: добавить guard — если `settings.base_webhook_url` пуст, логировать предупреждение и НЕ звать set_webhook (2b carry-forward), но всё равно добавить в реестр (для локальной разработки/тестов).
- `webhook_app._handle_webhook`: обернуть `feed_webhook_update` в try/except с логом, вернуть 200 даже при ошибке хендлера (чтобы Telegram не зацикливал ретраи) — 2b carry-forward.
- `src/admin/app.py`: удалить роуты `/bot-control`, `/bot-control/restart-now|schedule-restart|cancel-restart` и шаблон-ссылку (устарели при webhook). Настройки RESTART_* оставить в БД, но не использовать.

- [ ] Тест `test_reconcile.py`: реестр пуст + 1 активная студия → reconcile добавляет (added=1); студия стала is_active=False → reconcile убирает (removed=1). Мокать set_webhook/delete_webhook на Bot. → RED → реализация → GREEN → commit `feat: reconcile-цикл студий в боте + try/except webhook + guard base_webhook_url`.

---

### Task 9: Шаблоны — навигация по ролям, индикатор студии, удаление «Бот»

**Files:** Modify `src/admin/templates/base.html`; (order_detail.html уже в Task 4); Test: смоук через admin_client (рендер не падает под обеими ролями).

**Контракт:** base.html — в навигацию добавить:
- индикатор: имя залогиненного админа + (для super_admin) текущая «активная студия» или «— выберите студию», ссылка «🏢 Студии» (только super_admin), кнопка «выйти из просмотра студии» если active_studio_id задан.
- убрать пункт «🤖 Бот» (роуты удалены в Task 8).
Передавать в шаблоны контекст админа: добавить во все `TemplateResponse` переменные `admin` (из current_admin) и `active_studio` (имя). Проще — Jinja global/context processor: зарегистрировать функцию, читающую из request.session. Реализатор выбирает способ (рекомендуется добавлять `admin`/`studio_name` в контекст каждого рендера через хелпер `base_context(request, **extra)`).

- [ ] Тест: super_admin видит ссылку «Студии» в навигации; studio_admin — нет. → реализация → full `-W error` → commit `feat: навигация админки по ролям + индикатор активной студии`.

---

## Что остаётся для следующих под-проектов

- **Под-проект №2 — агент печати + счётчик** (foundational для биллинга): локальный Windows-агент, пайринг по коду, печать, billing_event при отпечатке, health-отчёт.
- **№3 — биллинг + онбординг-визард**; **№4 — лендинг.**
- Опционально: вынести `SettingsFacade` в сервисный слой (layering из 2a); реальная интеграция платёжного шлюза студии (оба режима оплаты).

## Self-Review (выполнено при написании)

- **Покрытие:** auth/роли (Task 2), эффективная студия (Task 2), супер-админ CRUD+kill-switch+view-as (Task 3), миграция роутов заказов/промокодов/настроек/товаров/аналитики/Mini-App (Tasks 4-7), reconcile + 2b carry-forwards (Task 8), шаблоны (Task 9). Carry-forwards 2a/2b закрыты в Tasks 6,7,8.
- **Плейсхолдеры:** ядро (auth.py, фикстуры, reconcile) — полный код; миграция роутов — контракт + worked-паттерн + тесты изоляции (как Task 9 в 2a). Реализатору каждой задачи: читать текущие строки роутов из app.py и применять контракт.
- **Согласованность:** `require_studio` → int studio_id; `effective_studio_id`; `NotificationService(bot, studio, SettingsFacade, ProductsFacade)`; `AnalyticsService(session, studio_id)`; `reconcile_studios(registry, session)`; `register_studio/unregister_studio` (из 2b) — сигнатуры согласованы между задачами.
- **Безопасность — главный инвариант:** в каждой миграционной задаче (4-7) обязателен тест, что studio_admin одной студии не видит/не меняет данные другой (404/пусто). Это красная нить плана.
