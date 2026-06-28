# Мультитенантный фундамент данных — План реализации (под-проект №1, план 1 из 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Превратить схему данных и сервисный слой photo28 в мультитенантные: таблица `studios`, `studio_id` во всех доменных таблицах, пер-студийные кеши настроек и товаров, изоляция сервисов по студии, на PostgreSQL — с покрытием тестами на изоляцию.

**Architecture:** Одна общая база PostgreSQL, изоляция строками через `studio_id` (FK, NOT NULL, индекс) во всех доменных таблицах. Глобальные классовые кеши `SettingsService` и `ProductService` переводятся на словари, ключённые по `studio_id`. Сервисы получают `studio_id` в конструкторе и фильтруют все запросы. Секретные токены студий шифруются Fernet. Этот план НЕ трогает рантайм бота (polling/webhook) и UI админки — только данные и сервисы; рантайм и роли — план 2.

**Tech Stack:** Python 3.9+, SQLAlchemy 2.0 (async, `Mapped`), asyncpg, aiogram 3.4.1, FastAPI, PostgreSQL, cryptography (Fernet), bcrypt, pytest + pytest-asyncio.

## Global Constraints

- Python 3.9+ (встроенные дженерики `list[...]`/`tuple[...]` в аннотациях разрешены).
- SQLAlchemy 2.0 async-стиль (`Mapped[...]`, `mapped_column`, `async_sessionmaker`) — следовать существующему стилю в `src/models/`.
- БД — **только PostgreSQL** (`postgresql+asyncpg://...`); SQLite больше не цель. Тесты идут на отдельную тестовую БД из `TEST_DATABASE_URL`.
- Все доменные таблицы (`users`, `orders`, `products`, `promocodes`, `settings`) обязаны иметь `studio_id: Mapped[int]` (FK → `studios.id`, NOT NULL, индекс).
- `users` уникальны по паре **(studio_id, telegram_id)**, НЕ по `telegram_id`.
- Номер заказа уникален в рамках студии: уникальный индекс **(studio_id, order_number)**.
- Денежные комиссии хранить как `Numeric(10, 2)` (тип Python `Decimal`), значение по умолчанию `platform_fee_per_photo = 5.00`, `monthly_minimum = 0`.
- Секреты (`bot_token`, `yandex_disk_token`, `payment_gateway_creds`) хранить зашифрованными Fernet; ключ — из env `FERNET_KEY`.
- Пароли админов — только bcrypt-хеш, открытый текст не хранить.
- Каждая задача завершается коммитом. Commit-сообщения на русском, префиксы `feat:`/`test:`/`chore:`.

---

### Task 1: Зависимости и тестовая инфраструктура

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_infra.py`
- Modify: `env.example`

**Interfaces:**
- Produces: pytest-фикстура `db_session` (async `AsyncSession` на тестовой БД с пересозданными таблицами); фикстура `engine` (session-scoped async engine).

- [ ] **Step 1: Добавить зависимости в `requirements.txt`**

Добавить в конец файла:

```
# PostgreSQL driver
asyncpg==0.29.0

# Secrets & auth
cryptography==42.0.5
bcrypt==4.1.2

# Tests
pytest==8.1.1
pytest-asyncio==0.23.6
```

- [ ] **Step 2: Установить зависимости**

Run: `pip install -r requirements.txt`
Expected: успешная установка asyncpg, cryptography, bcrypt, pytest, pytest-asyncio.

- [ ] **Step 3: Прописать тестовые переменные в `env.example`**

Добавить строки:

```
# Тестовая БД (отдельная от рабочей!)
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/photo28_test
# Ключ шифрования секретов студий (сгенерировать: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
FERNET_KEY=
```

- [ ] **Step 4: Создать `tests/__init__.py`**

```python
```
(пустой файл)

- [ ] **Step 5: Создать `tests/conftest.py`**

```python
"""Общие фикстуры для тестов."""
import os
import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.models.base import Base
# Импорт всех моделей, чтобы они зарегистрировались в Base.metadata.
import src.models  # noqa: F401

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/photo28_test",
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncSession:
    # Пересоздаём схему перед каждым тестом — полная изоляция.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
```

- [ ] **Step 6: Создать `src/models/__init__.py` с импортом всех моделей** (если ещё нет — проверить и дополнить)

```python
"""Реестр моделей — импорт регистрирует таблицы в Base.metadata."""
from src.models.base import Base
from src.models.user import User
from src.models.order import Order
from src.models.photo import Photo
from src.models.product import Product
from src.models.promocode import Promocode
from src.models.setting import Setting

__all__ = ["Base", "User", "Order", "Photo", "Product", "Promocode", "Setting"]
```

- [ ] **Step 7: Создать `tests/test_infra.py`**

```python
"""Проверка тестовой инфраструктуры и подключения к БД."""
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_db_session_connects(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1
```

- [ ] **Step 8: Создать `pytest.ini` в корне**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 9: Запустить тест**

Run: `pytest tests/test_infra.py -v`
Expected: PASS (требуется доступная локальная Postgres и созданная БД `photo28_test`; если нет — `createdb photo28_test`).

- [ ] **Step 10: Commit**

```bash
git add requirements.txt env.example tests/ src/models/__init__.py pytest.ini
git commit -m "chore: тестовая инфраструктура pytest + PostgreSQL, новые зависимости"
```

---

### Task 2: Модель Studio

**Files:**
- Create: `src/models/studio.py`
- Modify: `src/models/__init__.py`
- Test: `tests/models/test_studio.py`

**Interfaces:**
- Produces: класс `Studio(Base)` с таблицей `studios`. Поля: `id`, `slug` (unique), `name`, `is_active`, `bot_token` (зашифр.), `bot_username`, `manager_chat_id`, `manager_username`, `payment_phone`, `payment_card`, `payment_receiver`, `payment_gateway_creds` (зашифр., опц.), `yandex_disk_token` (зашифр., опц.), `platform_fee_per_photo: Decimal=5.00`, `monthly_minimum: Decimal=0`, `created_at`/`updated_at` (из Base).

- [ ] **Step 1: Создать тест `tests/models/test_studio.py`**

Создать `tests/models/__init__.py` (пустой), затем:

```python
"""Тесты модели Studio."""
from decimal import Decimal
import pytest
from sqlalchemy import select

from src.models.studio import Studio


@pytest.mark.asyncio
async def test_create_studio_defaults(db_session):
    studio = Studio(slug="photo28", name="Photo28")
    db_session.add(studio)
    await db_session.commit()

    loaded = (await db_session.execute(select(Studio))).scalar_one()
    assert loaded.slug == "photo28"
    assert loaded.is_active is True
    assert loaded.platform_fee_per_photo == Decimal("5.00")
    assert loaded.monthly_minimum == Decimal("0")


@pytest.mark.asyncio
async def test_studio_slug_unique(db_session):
    db_session.add(Studio(slug="dup", name="A"))
    await db_session.commit()
    db_session.add(Studio(slug="dup", name="B"))
    with pytest.raises(Exception):
        await db_session.commit()
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/models/test_studio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.models.studio'`.

- [ ] **Step 3: Создать `src/models/studio.py`**

```python
"""Модель студии (тенанта)."""
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Boolean, Numeric, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Studio(Base):
    """Фотостудия — единица мультитенантности."""

    __tablename__ = "studios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # kill-switch

    # Telegram — зашифрованный токен бота (Fernet), см. src/services/crypto.py
    bot_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    bot_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Группа чеков / менеджер
    manager_chat_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    manager_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Реквизиты P2P
    payment_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_card: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_receiver: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Опциональный собственный платёжный шлюз (зашифр. JSON-креды)
    payment_gateway_creds: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # Хранилище
    yandex_disk_token: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # Биллинг платформы
    platform_fee_per_photo: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("5.00")
    )
    monthly_minimum: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0")
    )

    def __repr__(self) -> str:
        return f"<Studio {self.slug}: {self.name}>"
```

- [ ] **Step 4: Зарегистрировать модель в `src/models/__init__.py`**

Добавить `from src.models.studio import Studio` и `"Studio"` в `__all__`.

- [ ] **Step 5: Запустить тест — убедиться, что проходит**

Run: `pytest tests/models/test_studio.py -v`
Expected: PASS (оба теста).

- [ ] **Step 6: Commit**

```bash
git add src/models/studio.py src/models/__init__.py tests/models/
git commit -m "feat: модель Studio (тенант) с биллинг-полями и шифруемыми токенами"
```

---

### Task 3: Утилита шифрования секретов (Fernet)

**Files:**
- Create: `src/services/crypto.py`
- Test: `tests/services/test_crypto.py`

**Interfaces:**
- Produces:
  - `encrypt_secret(plaintext: str) -> str` — шифрует и возвращает строку (urlsafe base64).
  - `decrypt_secret(ciphertext: str) -> str` — расшифровывает обратно.
  - `get_fernet() -> Fernet` — берёт ключ из `FERNET_KEY` (env), бросает `RuntimeError`, если ключ не задан.

- [ ] **Step 1: Создать тест `tests/services/test_crypto.py`**

Создать `tests/services/__init__.py` (пустой), затем:

```python
"""Тесты шифрования секретов."""
import os
from cryptography.fernet import Fernet
import pytest

from src.services.crypto import encrypt_secret, decrypt_secret


@pytest.fixture(autouse=True)
def _set_key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


def test_roundtrip():
    token = "8244811300:AAGnKMaBpdPdnHughXOvggH61XDFqS0RncE"
    enc = encrypt_secret(token)
    assert enc != token
    assert decrypt_secret(enc) == token


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("FERNET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        encrypt_secret("x")
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/services/test_crypto.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.crypto'`.

- [ ] **Step 3: Создать `src/services/crypto.py`**

```python
"""Шифрование секретов студий (Fernet)."""
import os
from cryptography.fernet import Fernet


def get_fernet() -> Fernet:
    key = os.environ.get("FERNET_KEY")
    if not key:
        raise RuntimeError("FERNET_KEY не задан в окружении")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    """Шифрует строку, возвращает urlsafe-токен."""
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Расшифровывает строку, зашифрованную encrypt_secret."""
    return get_fernet().decrypt(ciphertext.encode()).decode()
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `pytest tests/services/test_crypto.py -v`
Expected: PASS (оба теста).

- [ ] **Step 5: Commit**

```bash
git add src/services/crypto.py tests/services/
git commit -m "feat: Fernet-шифрование секретов студий"
```

---

### Task 4: Модель AdminUser (bcrypt)

**Files:**
- Create: `src/models/admin_user.py`
- Modify: `src/models/__init__.py`
- Create: `src/services/auth.py`
- Test: `tests/models/test_admin_user.py`

**Interfaces:**
- Produces:
  - `AdminRole(str, Enum)` со значениями `SUPER_ADMIN = "super_admin"`, `STUDIO_ADMIN = "studio_admin"`.
  - `AdminUser(Base)`: `id`, `username` (unique), `password_hash`, `role: AdminRole`, `studio_id: Optional[int]` (FK → `studios.id`, NULL для super_admin).
  - `src/services/auth.py`: `hash_password(raw: str) -> str`, `verify_password(raw: str, hashed: str) -> bool`.

- [ ] **Step 1: Создать тест `tests/models/test_admin_user.py`**

```python
"""Тесты AdminUser и хеширования паролей."""
import pytest
from sqlalchemy import select

from src.models.admin_user import AdminUser, AdminRole
from src.models.studio import Studio
from src.services.auth import hash_password, verify_password


def test_password_hashing():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h) is True
    assert verify_password("wrong", h) is False


@pytest.mark.asyncio
async def test_super_admin_has_no_studio(db_session):
    admin = AdminUser(
        username="ivan",
        password_hash=hash_password("pw"),
        role=AdminRole.SUPER_ADMIN,
        studio_id=None,
    )
    db_session.add(admin)
    await db_session.commit()
    loaded = (await db_session.execute(select(AdminUser))).scalar_one()
    assert loaded.role == AdminRole.SUPER_ADMIN
    assert loaded.studio_id is None


@pytest.mark.asyncio
async def test_studio_admin_linked_to_studio(db_session):
    studio = Studio(slug="s1", name="S1")
    db_session.add(studio)
    await db_session.commit()
    admin = AdminUser(
        username="owner1",
        password_hash=hash_password("pw"),
        role=AdminRole.STUDIO_ADMIN,
        studio_id=studio.id,
    )
    db_session.add(admin)
    await db_session.commit()
    loaded = (await db_session.execute(
        select(AdminUser).where(AdminUser.username == "owner1")
    )).scalar_one()
    assert loaded.studio_id == studio.id
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/models/test_admin_user.py -v`
Expected: FAIL — нет модуля `src.models.admin_user`.

- [ ] **Step 3: Создать `src/services/auth.py`**

```python
"""Хеширование и проверка паролей админов (bcrypt)."""
import bcrypt


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False
```

- [ ] **Step 4: Создать `src/models/admin_user.py`**

```python
"""Модель администратора (super_admin / studio_admin)."""
from enum import Enum
from typing import Optional
from sqlalchemy import String, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class AdminRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    STUDIO_ADMIN = "studio_admin"


class AdminUser(Base):
    """Учётная запись для входа в админку."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[AdminRole] = mapped_column(SQLEnum(AdminRole), default=AdminRole.STUDIO_ADMIN)
    # NULL для super_admin, иначе — id студии
    studio_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), nullable=True, index=True
    )

    def __repr__(self) -> str:
        return f"<AdminUser {self.username} ({self.role.value})>"
```

- [ ] **Step 5: Зарегистрировать в `src/models/__init__.py`**

Добавить `from src.models.admin_user import AdminUser, AdminRole` и `"AdminUser"`, `"AdminRole"` в `__all__`.

- [ ] **Step 6: Запустить тесты — убедиться, что проходят**

Run: `pytest tests/models/test_admin_user.py -v`
Expected: PASS (три теста).

- [ ] **Step 7: Commit**

```bash
git add src/models/admin_user.py src/services/auth.py src/models/__init__.py tests/models/test_admin_user.py
git commit -m "feat: модель AdminUser с ролями + bcrypt-хеширование паролей"
```

---

### Task 5: Модель BillingEvent (задел под биллинг)

**Files:**
- Create: `src/models/billing_event.py`
- Modify: `src/models/__init__.py`
- Test: `tests/models/test_billing_event.py`

**Interfaces:**
- Produces: `BillingEvent(Base)`: `id`, `studio_id` (FK, индекс), `order_id` (FK), `photo_position: int`, `fee: Decimal`, `printed_at: datetime`. Наполняется под-проектом №2 (агент печати); здесь только таблица.

- [ ] **Step 1: Создать тест `tests/models/test_billing_event.py`**

```python
"""Тест модели BillingEvent."""
from decimal import Decimal
from datetime import datetime
import pytest
from sqlalchemy import select

from src.models.studio import Studio
from src.models.user import User
from src.models.order import Order, OrderStatus
from src.models.billing_event import BillingEvent


@pytest.mark.asyncio
async def test_create_billing_event(db_session):
    studio = Studio(slug="s1", name="S1")
    db_session.add(studio)
    await db_session.commit()
    user = User(studio_id=studio.id, telegram_id=1)
    db_session.add(user)
    await db_session.commit()
    order = Order(studio_id=studio.id, user_id=user.id, order_number="240101-AAAA",
                  status=OrderStatus.CONFIRMED)
    db_session.add(order)
    await db_session.commit()

    ev = BillingEvent(
        studio_id=studio.id, order_id=order.id, photo_position=0,
        fee=Decimal("5.00"), printed_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    db_session.add(ev)
    await db_session.commit()

    loaded = (await db_session.execute(select(BillingEvent))).scalar_one()
    assert loaded.studio_id == studio.id
    assert loaded.fee == Decimal("5.00")
```

(Тест зависит от `studio_id` в `User`/`Order` — выполняется ПОСЛЕ Task 6 и Task 7. Если выполняете задачи строго по порядку, перенесите запуск этого теста в конец Task 7. Реализацию модели делайте здесь.)

- [ ] **Step 2: Создать `src/models/billing_event.py`**

```python
"""Событие тарификации — один напечатанный отпечаток (наполняется в под-проекте №2)."""
from decimal import Decimal
from datetime import datetime
from sqlalchemy import Integer, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class BillingEvent(Base):
    """Факт печати одного изображения = одна единица комиссии платформы."""

    __tablename__ = "billing_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    photo_position: Mapped[int] = mapped_column(Integer, default=0)
    fee: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    printed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<BillingEvent studio={self.studio_id} order={self.order_id} fee={self.fee}>"
```

- [ ] **Step 3: Зарегистрировать в `src/models/__init__.py`**

Добавить `from src.models.billing_event import BillingEvent` и `"BillingEvent"` в `__all__`.

- [ ] **Step 4: Commit** (тест запустится в конце Task 7)

```bash
git add src/models/billing_event.py src/models/__init__.py tests/models/test_billing_event.py
git commit -m "feat: модель BillingEvent (задел под биллинг по факту печати)"
```

---

### Task 6: studio_id в User + уникальность (studio_id, telegram_id)

**Files:**
- Modify: `src/models/user.py`
- Test: `tests/models/test_user_tenancy.py`

**Interfaces:**
- Consumes: `Studio` (Task 2).
- Produces: `User.studio_id: Mapped[int]` (FK, NOT NULL, индекс); снят `unique=True` с `telegram_id`; добавлен `UniqueConstraint("studio_id", "telegram_id")`. Связь `User.studio` (lazy).

- [ ] **Step 1: Создать тест `tests/models/test_user_tenancy.py`**

```python
"""Тесты тенантности User."""
import pytest
from sqlalchemy import select

from src.models.studio import Studio
from src.models.user import User


@pytest.mark.asyncio
async def test_same_telegram_id_two_studios_allowed(db_session):
    s1 = Studio(slug="s1", name="S1")
    s2 = Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2])
    await db_session.commit()

    db_session.add(User(studio_id=s1.id, telegram_id=777))
    db_session.add(User(studio_id=s2.id, telegram_id=777))
    await db_session.commit()  # не должно падать

    users = (await db_session.execute(select(User))).scalars().all()
    assert len(users) == 2


@pytest.mark.asyncio
async def test_same_telegram_id_same_studio_rejected(db_session):
    s1 = Studio(slug="s1", name="S1")
    db_session.add(s1)
    await db_session.commit()
    db_session.add(User(studio_id=s1.id, telegram_id=777))
    await db_session.commit()
    db_session.add(User(studio_id=s1.id, telegram_id=777))
    with pytest.raises(Exception):
        await db_session.commit()
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/models/test_user_tenancy.py -v`
Expected: FAIL — `User` ещё без `studio_id` (TypeError/IntegrityError).

- [ ] **Step 3: Изменить `src/models/user.py`**

Заменить заголовок класса и поле `telegram_id`, добавить `studio_id` и `__table_args__`:

```python
"""Модель пользователя."""
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import BigInteger, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.order import Order
    from src.models.studio import Studio


class User(Base):
    """Пользователь бота (в рамках конкретной студии)."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("studio_id", "telegram_id", name="uq_user_studio_telegram"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    studio: Mapped["Studio"] = relationship(lazy="selectin")
    orders: Mapped[List["Order"]] = relationship(back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User s{self.studio_id}:{self.telegram_id}: {self.username or self.first_name}>"

    @property
    def display_name(self) -> str:
        if self.first_name:
            if self.last_name:
                return f"{self.first_name} {self.last_name}"
            return self.first_name
        return self.username or f"User_{self.telegram_id}"
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `pytest tests/models/test_user_tenancy.py -v`
Expected: PASS (оба теста).

- [ ] **Step 5: Commit**

```bash
git add src/models/user.py tests/models/test_user_tenancy.py
git commit -m "feat: studio_id в User, уникальность (studio_id, telegram_id)"
```

---

### Task 7: studio_id в Order + пер-студийная нумерация заказов

**Files:**
- Modify: `src/models/order.py:84-145` (заголовок класса, добавить поле, table_args)
- Test: `tests/models/test_order_tenancy.py`

**Interfaces:**
- Consumes: `Studio` (Task 2), `User` (Task 6).
- Produces: `Order.studio_id: Mapped[int]` (FK, NOT NULL, индекс); снят `unique=True` с `order_number`; добавлен `UniqueConstraint("studio_id", "order_number")`. Связь `Order.studio` (lazy).

- [ ] **Step 1: Создать тест `tests/models/test_order_tenancy.py`**

```python
"""Тесты тенантности Order."""
import pytest
from sqlalchemy import select

from src.models.studio import Studio
from src.models.user import User
from src.models.order import Order, OrderStatus


async def _studio_user(db_session, slug):
    s = Studio(slug=slug, name=slug)
    db_session.add(s)
    await db_session.commit()
    u = User(studio_id=s.id, telegram_id=1)
    db_session.add(u)
    await db_session.commit()
    return s, u


@pytest.mark.asyncio
async def test_same_order_number_two_studios_allowed(db_session):
    s1, u1 = await _studio_user(db_session, "s1")
    s2, u2 = await _studio_user(db_session, "s2")
    db_session.add(Order(studio_id=s1.id, user_id=u1.id, order_number="240101-AAAA"))
    db_session.add(Order(studio_id=s2.id, user_id=u2.id, order_number="240101-AAAA"))
    await db_session.commit()
    assert len((await db_session.execute(select(Order))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_same_order_number_same_studio_rejected(db_session):
    s1, u1 = await _studio_user(db_session, "s1")
    db_session.add(Order(studio_id=s1.id, user_id=u1.id, order_number="240101-AAAA"))
    await db_session.commit()
    db_session.add(Order(studio_id=s1.id, user_id=u1.id, order_number="240101-AAAA"))
    with pytest.raises(Exception):
        await db_session.commit()
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/models/test_order_tenancy.py -v`
Expected: FAIL — `Order` ещё без `studio_id`.

- [ ] **Step 3: Изменить `src/models/order.py`**

В импортах добавить `UniqueConstraint` и (в `TYPE_CHECKING`) `Studio`:

```python
from sqlalchemy import String, Integer, ForeignKey, Enum as SQLEnum, Text, Float, UniqueConstraint
```
```python
if TYPE_CHECKING:
    from src.models.user import User
    from src.models.photo import Photo
    from src.models.studio import Studio
```

Заменить определение таблицы (строки 84-99), сняв `unique=True` с `order_number` и добавив `studio_id` + `__table_args__`:

```python
class Order(Base):
    """Заказ пользователя (в рамках студии)."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("studio_id", "order_number", name="uq_order_studio_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    # Номер заказа для отображения клиенту (уникален в рамках студии)
    order_number: Mapped[str] = mapped_column(String(20), index=True)

    # Статус заказа
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus),
        default=OrderStatus.DRAFT
    )
```

Добавить связь `studio` рядом с существующими relationships (после `user`):

```python
    studio: Mapped["Studio"] = relationship(lazy="selectin")
```

- [ ] **Step 4: Запустить тесты тенантности заказа И отложенный тест BillingEvent**

Run: `pytest tests/models/test_order_tenancy.py tests/models/test_billing_event.py -v`
Expected: PASS (все три теста).

- [ ] **Step 5: Commit**

```bash
git add src/models/order.py tests/models/test_order_tenancy.py
git commit -m "feat: studio_id в Order, пер-студийная уникальность order_number"
```

---

### Task 8: studio_id в Product, Promocode, Setting

**Files:**
- Modify: `src/models/product.py:21-32`
- Modify: `src/models/promocode.py:13-18`
- Modify: `src/models/setting.py:22-27`
- Test: `tests/models/test_catalog_tenancy.py`

**Interfaces:**
- Consumes: `Studio` (Task 2).
- Produces: поле `studio_id` (FK, NOT NULL, индекс) в `Product`, `Promocode`, `Setting`. Снят глобальный `unique=True` со `slug`/`code`/`key`; добавлены `UniqueConstraint` по (studio_id, slug) / (studio_id, code) / (studio_id, key).

- [ ] **Step 1: Создать тест `tests/models/test_catalog_tenancy.py`**

```python
"""Тенантность каталога/промокодов/настроек."""
import pytest
from sqlalchemy import select

from src.models.studio import Studio
from src.models.product import Product
from src.models.promocode import Promocode
from src.models.setting import Setting


@pytest.mark.asyncio
async def test_same_slug_code_key_across_studios(db_session):
    s1 = Studio(slug="s1", name="S1")
    s2 = Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2])
    await db_session.commit()

    db_session.add(Product(studio_id=s1.id, slug="10x15", name="A", short_name="A"))
    db_session.add(Product(studio_id=s2.id, slug="10x15", name="A", short_name="A"))
    db_session.add(Promocode(studio_id=s1.id, code="SALE"))
    db_session.add(Promocode(studio_id=s2.id, code="SALE"))
    db_session.add(Setting(studio_id=s1.id, key="min_photos", value="10"))
    db_session.add(Setting(studio_id=s2.id, key="min_photos", value="5"))
    await db_session.commit()  # дубликаты в РАЗНЫХ студиях разрешены

    assert len((await db_session.execute(select(Product))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_same_key_same_studio_rejected(db_session):
    s1 = Studio(slug="s1", name="S1")
    db_session.add(s1)
    await db_session.commit()
    db_session.add(Setting(studio_id=s1.id, key="min_photos", value="10"))
    await db_session.commit()
    db_session.add(Setting(studio_id=s1.id, key="min_photos", value="20"))
    with pytest.raises(Exception):
        await db_session.commit()
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/models/test_catalog_tenancy.py -v`
Expected: FAIL — нет `studio_id` в моделях.

- [ ] **Step 3: Изменить `src/models/product.py`**

В импорт добавить `ForeignKey` (уже есть) и `UniqueConstraint`:
```python
from sqlalchemy import String, Integer, Float, ForeignKey, Text, Boolean, UniqueConstraint
```
Заменить начало класса (строки 21-32):
```python
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("studio_id", "slug", name="uq_product_studio_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Для двухуровневой навигации
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True
    )

    # Идентификатор (slug) — уникален в рамках студии
    slug: Mapped[str] = mapped_column(String(100), index=True)
```

- [ ] **Step 4: Изменить `src/models/promocode.py`**

В импорт добавить `ForeignKey, UniqueConstraint`:
```python
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
```
Заменить начало класса (строки 13-18):
```python
    __tablename__ = "promocodes"
    __table_args__ = (
        UniqueConstraint("studio_id", "code", name="uq_promocode_studio_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Код промокода (уникален в рамках студии, регистронезависимый)
    code: Mapped[str] = mapped_column(String(50), index=True)
```

- [ ] **Step 5: Изменить `src/models/setting.py`**

В импорт добавить `ForeignKey, UniqueConstraint`:
```python
from sqlalchemy import String, Text, ForeignKey, UniqueConstraint
```
Заменить начало класса (строки 22-27):
```python
    __tablename__ = "settings"
    __table_args__ = (
        UniqueConstraint("studio_id", "key", name="uq_setting_studio_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Ключ настройки (уникален в рамках студии)
    key: Mapped[str] = mapped_column(String(100), index=True)
```

- [ ] **Step 6: Запустить тесты — убедиться, что проходят**

Run: `pytest tests/models/test_catalog_tenancy.py -v`
Expected: PASS (оба теста).

- [ ] **Step 7: Commit**

```bash
git add src/models/product.py src/models/promocode.py src/models/setting.py tests/models/test_catalog_tenancy.py
git commit -m "feat: studio_id в Product/Promocode/Setting + пер-студийная уникальность"
```

---

### Task 9: SettingsService — пер-студийный кеш

**Files:**
- Modify: `src/services/settings_service.py`
- Test: `tests/services/test_settings_service.py`

**Interfaces:**
- Consumes: `Setting.studio_id` (Task 8).
- Produces (новая сигнатура — классовый кеш теперь `Dict[int, Dict[str, Any]]` по `studio_id`):
  - `await SettingsService(session).load_cache(studio_id: int)` — грузит настройки одной студии.
  - `SettingsService.get(studio_id: int, key: str, default=None)`, `.get_int(studio_id, key, default=0)`, `.get_float(...)`, `.get_bool(...)` — все classmethod, первым аргументом `studio_id`.
  - `SettingsService.invalidate_cache(studio_id: Optional[int] = None)` — сброс кеша одной студии или всех.
  - инстанс-методы `get_all`, `get_by_key`, `set_value`, `create_setting` принимают `studio_id`.

- [ ] **Step 1: Создать тест `tests/services/test_settings_service.py`**

```python
"""Тесты пер-студийного кеша настроек."""
import pytest

from src.models.studio import Studio
from src.models.setting import Setting, SettingType
from src.services.settings_service import SettingsService


async def _two_studios(db_session):
    s1, s2 = Studio(slug="s1", name="S1"), Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2])
    await db_session.commit()
    db_session.add(Setting(studio_id=s1.id, key="min_photos", value="10",
                           value_type=SettingType.INTEGER))
    db_session.add(Setting(studio_id=s2.id, key="min_photos", value="3",
                           value_type=SettingType.INTEGER))
    await db_session.commit()
    return s1, s2


@pytest.mark.asyncio
async def test_cache_is_per_studio(db_session):
    SettingsService.invalidate_cache()
    s1, s2 = await _two_studios(db_session)
    svc = SettingsService(db_session)
    await svc.load_cache(s1.id)
    await svc.load_cache(s2.id)

    assert SettingsService.get_int(s1.id, "min_photos", 0) == 10
    assert SettingsService.get_int(s2.id, "min_photos", 0) == 3


@pytest.mark.asyncio
async def test_set_value_updates_only_one_studio(db_session):
    SettingsService.invalidate_cache()
    s1, s2 = await _two_studios(db_session)
    svc = SettingsService(db_session)
    await svc.load_cache(s1.id)
    await svc.load_cache(s2.id)

    await svc.set_value(s1.id, "min_photos", "99")
    assert SettingsService.get_int(s1.id, "min_photos", 0) == 99
    assert SettingsService.get_int(s2.id, "min_photos", 0) == 3
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/services/test_settings_service.py -v`
Expected: FAIL — старая сигнатура `get(key, default)` не принимает `studio_id`.

- [ ] **Step 3: Переписать `src/services/settings_service.py` (часть класса до констант)**

Заменить тело класса `SettingsService` (строки 9-117 файла) на:

```python
class SettingsService:
    """Сервис настроек с пер-студийным кешем в памяти."""

    # Кеш: {studio_id: {key: typed_value}}
    _cache: Dict[int, Dict[str, Any]] = {}

    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_cache(self, studio_id: int) -> None:
        """Загружает настройки одной студии в кеш."""
        query = select(Setting).where(Setting.studio_id == studio_id)
        result = await self.session.execute(query)
        settings = result.scalars().all()
        SettingsService._cache[studio_id] = {
            s.key: s.get_typed_value() for s in settings
        }

    @classmethod
    def get(cls, studio_id: int, key: str, default: Any = None) -> Any:
        return cls._cache.get(studio_id, {}).get(key, default)

    @classmethod
    def get_int(cls, studio_id: int, key: str, default: int = 0) -> int:
        value = cls.get(studio_id, key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @classmethod
    def get_float(cls, studio_id: int, key: str, default: float = 0.0) -> float:
        value = cls.get(studio_id, key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @classmethod
    def get_bool(cls, studio_id: int, key: str, default: bool = False) -> bool:
        value = cls.get(studio_id, key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "да")
        return bool(value)

    @classmethod
    def invalidate_cache(cls, studio_id: Optional[int] = None) -> None:
        if studio_id is None:
            cls._cache = {}
        else:
            cls._cache.pop(studio_id, None)

    async def get_all(self, studio_id: int) -> list[Setting]:
        query = (
            select(Setting)
            .where(Setting.studio_id == studio_id)
            .order_by(Setting.group, Setting.sort_order)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_key(self, studio_id: int, key: str) -> Optional[Setting]:
        query = select(Setting).where(
            Setting.studio_id == studio_id, Setting.key == key
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def set_value(self, studio_id: int, key: str, value: Any) -> Setting:
        setting = await self.get_by_key(studio_id, key)
        if not setting:
            raise ValueError(f"Настройка {key} не найдена для студии {studio_id}")
        setting.value = str(value)
        await self.session.commit()
        SettingsService._cache.setdefault(studio_id, {})[key] = setting.get_typed_value()
        return setting

    async def create_setting(
        self,
        studio_id: int,
        key: str,
        value: str,
        value_type: SettingType = SettingType.STRING,
        display_name: str = "",
        description: str = "",
        group: str = "general",
        sort_order: int = 0,
    ) -> Setting:
        setting = Setting(
            studio_id=studio_id,
            key=key,
            value=value,
            value_type=value_type,
            display_name=display_name or key,
            description=description,
            group=group,
            sort_order=sort_order,
        )
        self.session.add(setting)
        await self.session.commit()
        SettingsService._cache.setdefault(studio_id, {})[key] = setting.get_typed_value()
        return setting
```

> Примечание: вызовы `SettingsService.get(...)` в `src/models/order.py` (enum `DeliveryType`), `src/services/notification_service.py` и хендлерах бота временно сломаются по сигнатуре. Их перевод на `studio_id` выполняется в Плане 2 (рантайм), где `studio_id` протягивается через контекст. В рамках Плана 1 эти модули не тестируются и не запускаются — фундамент данных проверяется юнит-тестами сервисов.

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `pytest tests/services/test_settings_service.py -v`
Expected: PASS (оба теста).

- [ ] **Step 5: Commit**

```bash
git add src/services/settings_service.py tests/services/test_settings_service.py
git commit -m "feat: пер-студийный кеш SettingsService (ключ studio_id)"
```

---

### Task 10: ProductService — пер-студийный кеш

**Files:**
- Modify: `src/services/product_service.py`
- Test: `tests/services/test_product_service.py`

**Interfaces:**
- Consumes: `Product.studio_id` (Task 8).
- Produces (классовый кеш по studio_id):
  - `await ProductService(session).load_cache(studio_id: int)`.
  - `ProductService.get_product(studio_id: int, product_id: int)`, `.get_top_level_products(studio_id)`, `.get_active_children(studio_id, parent_id)`, `.get_all_purchasable(studio_id)`, `.invalidate_cache(studio_id=None)`.
  - инстанс-методы `get_all_products(studio_id)`, `create_product(studio_id, **kwargs)`, `update_product`, `delete_product`, `toggle_product` (последние три грузят кеш нужной студии).

- [ ] **Step 1: Создать тест `tests/services/test_product_service.py`**

```python
"""Тесты пер-студийного кеша товаров."""
import pytest

from src.models.studio import Studio
from src.models.product import Product
from src.services.product_service import ProductService


async def _two_studios_with_products(db_session):
    s1, s2 = Studio(slug="s1", name="S1"), Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2])
    await db_session.commit()
    db_session.add(Product(studio_id=s1.id, slug="a", name="A", short_name="A",
                           price_per_unit=25, is_active=True))
    db_session.add(Product(studio_id=s2.id, slug="b", name="B", short_name="B",
                           price_per_unit=40, is_active=True))
    await db_session.commit()
    return s1, s2


@pytest.mark.asyncio
async def test_top_level_is_per_studio(db_session):
    ProductService.invalidate_cache()
    s1, s2 = await _two_studios_with_products(db_session)
    svc = ProductService(db_session)
    await svc.load_cache(s1.id)
    await svc.load_cache(s2.id)

    s1_slugs = [p.slug for p in ProductService.get_top_level_products(s1.id)]
    s2_slugs = [p.slug for p in ProductService.get_top_level_products(s2.id)]
    assert s1_slugs == ["a"]
    assert s2_slugs == ["b"]
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/services/test_product_service.py -v`
Expected: FAIL — старая сигнатура без `studio_id`.

- [ ] **Step 3: Переписать `src/services/product_service.py`**

```python
"""Сервис управления товарами/форматами (пер-студийный кеш)."""
import logging
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.product import Product

logger = logging.getLogger(__name__)


class ProductService:
    """Кеш товаров на уровне класса, ключённый по studio_id."""

    # {studio_id: {product_id: Product}}
    _products: Dict[int, Dict[int, Product]] = {}
    # {studio_id: [Product, ...]} — верхний уровень
    _top_level: Dict[int, List[Product]] = {}

    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_cache(self, studio_id: int) -> None:
        query = (
            select(Product)
            .where(Product.studio_id == studio_id)
            .options(selectinload(Product.children), selectinload(Product.parent))
            .order_by(Product.sort_order)
        )
        result = await self.session.execute(query)
        products = result.scalars().unique().all()
        ProductService._products[studio_id] = {p.id: p for p in products}
        ProductService._top_level[studio_id] = [
            p for p in products if p.parent_id is None and p.is_active
        ]
        logger.info(f"Студия {studio_id}: загружено {len(products)} товаров")

    @classmethod
    def get_product(cls, studio_id: int, product_id: int) -> Optional[Product]:
        return cls._products.get(studio_id, {}).get(product_id)

    @classmethod
    def get_top_level_products(cls, studio_id: int) -> List[Product]:
        return [p for p in cls._top_level.get(studio_id, []) if p.is_active]

    @classmethod
    def get_active_children(cls, studio_id: int, parent_id: int) -> List[Product]:
        parent = cls._products.get(studio_id, {}).get(parent_id)
        if not parent:
            return []
        return sorted(
            [c for c in parent.children if c.is_active],
            key=lambda x: x.sort_order,
        )

    @classmethod
    def get_all_purchasable(cls, studio_id: int) -> List[Product]:
        result = []
        for p in cls._top_level.get(studio_id, []):
            if not p.is_active:
                continue
            children = [c for c in p.children if c.is_active]
            if children:
                result.extend(children)
            else:
                result.append(p)
        return result

    @classmethod
    def invalidate_cache(cls, studio_id: Optional[int] = None):
        if studio_id is None:
            cls._products.clear()
            cls._top_level.clear()
        else:
            cls._products.pop(studio_id, None)
            cls._top_level.pop(studio_id, None)

    # === CRUD ===

    async def get_all_products(self, studio_id: int) -> List[Product]:
        query = (
            select(Product)
            .where(Product.studio_id == studio_id)
            .options(selectinload(Product.children), selectinload(Product.parent))
            .order_by(Product.sort_order)
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    async def get_product_by_id(self, product_id: int) -> Optional[Product]:
        query = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.children))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_product(self, studio_id: int, **kwargs) -> Product:
        product = Product(studio_id=studio_id, **kwargs)
        self.session.add(product)
        await self.session.commit()
        await self.session.refresh(product)
        await self.load_cache(studio_id)
        return product

    async def update_product(self, product_id: int, **kwargs) -> Optional[Product]:
        product = await self.get_product_by_id(product_id)
        if not product:
            return None
        for key, value in kwargs.items():
            if hasattr(product, key):
                setattr(product, key, value)
        await self.session.commit()
        await self.session.refresh(product)
        await self.load_cache(product.studio_id)
        return product

    async def delete_product(self, product_id: int) -> bool:
        product = await self.get_product_by_id(product_id)
        if not product:
            return False
        studio_id = product.studio_id
        await self.session.delete(product)
        await self.session.commit()
        await self.load_cache(studio_id)
        return True

    async def toggle_product(self, product_id: int) -> Optional[Product]:
        product = await self.get_product_by_id(product_id)
        if not product:
            return None
        product.is_active = not product.is_active
        await self.session.commit()
        await self.session.refresh(product)
        await self.load_cache(product.studio_id)
        return product
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `pytest tests/services/test_product_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/product_service.py tests/services/test_product_service.py
git commit -m "feat: пер-студийный кеш ProductService (ключ studio_id)"
```

---

### Task 11: OrderService — изоляция по студии

**Files:**
- Modify: `src/services/order_service.py`
- Test: `tests/services/test_order_service_tenancy.py`

**Interfaces:**
- Consumes: `Order.studio_id`, `User.studio_id`, `Product.studio_id`, `Promocode.studio_id`.
- Produces: конструктор `OrderService(session, studio_id: int)` хранит `self.studio_id`. Все методы фильтруют/проставляют `studio_id`. Затронуты: `get_or_create_user` (поиск по (studio_id, telegram_id), создание со studio_id), `create_order`, `get_order_by_id`, `get_order_by_number`, `get_user_draft_order`, `get_user_orders`, `get_orders_by_status`, `get_all_orders`, `search_orders`, `delete_old_drafts`, `get_promocode`, `create_promocode`. `add_photo`/`remove_photo`/`update_photo_crop`/`recalculate_order_cost` не меняют сигнатуру (работают через объект Order, у которого уже есть studio_id).

- [ ] **Step 1: Создать тест `tests/services/test_order_service_tenancy.py`**

```python
"""Изоляция OrderService по студии."""
import pytest

from src.models.studio import Studio
from src.services.order_service import OrderService


async def _two_studios(db_session):
    s1, s2 = Studio(slug="s1", name="S1"), Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2])
    await db_session.commit()
    return s1, s2


@pytest.mark.asyncio
async def test_get_or_create_user_is_scoped(db_session):
    s1, s2 = await _two_studios(db_session)
    svc1 = OrderService(db_session, studio_id=s1.id)
    svc2 = OrderService(db_session, studio_id=s2.id)

    u1 = await svc1.get_or_create_user(telegram_id=777, first_name="A")
    u2 = await svc2.get_or_create_user(telegram_id=777, first_name="A")
    # Один и тот же telegram_id, но РАЗНЫЕ пользователи в разных студиях
    assert u1.id != u2.id
    assert u1.studio_id == s1.id
    assert u2.studio_id == s2.id


@pytest.mark.asyncio
async def test_orders_isolated_between_studios(db_session):
    s1, s2 = await _two_studios(db_session)
    svc1 = OrderService(db_session, studio_id=s1.id)
    svc2 = OrderService(db_session, studio_id=s2.id)

    u1 = await svc1.get_or_create_user(telegram_id=1, first_name="A")
    order1 = await svc1.create_order(u1)
    from src.models.order import OrderStatus
    await svc1.update_order_status(order1, OrderStatus.PAID)

    # Студия 2 не видит заказ студии 1
    assert await svc2.get_order_by_id(order1.id) is None
    assert len(await svc2.get_all_orders()) == 0
    assert len(await svc1.get_all_orders()) == 1
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/services/test_order_service_tenancy.py -v`
Expected: FAIL — `OrderService.__init__()` не принимает `studio_id`.

- [ ] **Step 3: Изменить `src/services/order_service.py`**

Заменить конструктор (строки 20-21):
```python
    def __init__(self, session: AsyncSession, studio_id: int):
        self.session = session
        self.studio_id = studio_id
```

Заменить `get_or_create_user` (строки 32-60):
```python
    async def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """Получает или создаёт пользователя в рамках текущей студии."""
        query = select(User).where(
            User.studio_id == self.studio_id,
            User.telegram_id == telegram_id,
        )
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()

        if user:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            await self.session.commit()
            return user

        user = User(
            studio_id=self.studio_id,
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
```

Заменить `create_order` (строки 64-74):
```python
    async def create_order(self, user: User) -> Order:
        """Создаёт новый заказ-черновик в текущей студии."""
        order = Order(
            studio_id=self.studio_id,
            user_id=user.id,
            order_number=self.generate_order_number(),
            status=OrderStatus.DRAFT,
        )
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return order
```

Добавить фильтр `Order.studio_id == self.studio_id` (первым условием в `.where(...)`) в методах: `get_order_by_id`, `get_order_by_number`, `get_user_draft_order`, `get_user_orders`, `get_orders_by_status`, `get_all_orders`. Например, `get_order_by_id`:
```python
    async def get_order_by_id(self, order_id: int) -> Optional[Order]:
        query = select(Order).where(
            Order.studio_id == self.studio_id, Order.id == order_id
        ).options(
            selectinload(Order.photos),
            selectinload(Order.user),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
```
И аналогично `get_all_orders`:
```python
    async def get_all_orders(self, limit: int = 100, offset: int = 0) -> List[Order]:
        query = (
            select(Order)
            .where(Order.studio_id == self.studio_id, Order.status != OrderStatus.DRAFT)
            .options(selectinload(Order.photos), selectinload(Order.user))
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
```

В `search_orders` добавить `Order.studio_id == self.studio_id` в `base_query` и `count_query`:
```python
        base_query = select(Order).where(
            Order.studio_id == self.studio_id, Order.status != OrderStatus.DRAFT
        )
        count_query = select(func.count(Order.id)).where(
            Order.studio_id == self.studio_id, Order.status != OrderStatus.DRAFT
        )
```

В `delete_old_drafts` добавить фильтр студии в оба запроса:
```python
        count_query = select(func.count(Order.id)).where(
            Order.studio_id == self.studio_id,
            Order.status == OrderStatus.DRAFT,
            Order.created_at < cutoff_date,
        )
        ...
        delete_query = delete(Order).where(
            Order.studio_id == self.studio_id,
            Order.status == OrderStatus.DRAFT,
            Order.created_at < cutoff_date,
        )
```

Заменить `get_promocode` (строки 347-353):
```python
    async def get_promocode(self, code: str) -> Optional[Promocode]:
        query = select(Promocode).where(
            Promocode.studio_id == self.studio_id,
            Promocode.code == code.upper().strip(),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
```

Заменить `create_promocode` (добавить `studio_id` при создании):
```python
        promocode = Promocode(
            studio_id=self.studio_id,
            code=code.upper().strip(),
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            description=description,
            max_uses=max_uses,
        )
```

> Примечание: `recalculate_order_cost` вызывает `PricingService.calculate_total_cost(photos_by_product)`, который читает товары из `ProductService` глобально. Перевод `PricingService` на `studio_id` — в Плане 2 (рантайм), вместе с обновлением хендлеров; в Плане 1 тест на изоляцию заказов не задействует пересчёт цены через каталог.

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `pytest tests/services/test_order_service_tenancy.py -v`
Expected: PASS (оба теста).

- [ ] **Step 5: Commit**

```bash
git add src/services/order_service.py tests/services/test_order_service_tenancy.py
git commit -m "feat: изоляция OrderService по studio_id"
```

---

### Task 12: Скрипт сидинга студии (создание тенанта + админ + дефолтные настройки + шаблон каталога)

**Files:**
- Create: `src/services/studio_provisioning.py`
- Create: `scripts/seed_studio.py`
- Test: `tests/services/test_studio_provisioning.py`

**Interfaces:**
- Consumes: `Studio`, `AdminUser`, `Setting`, `Product`, `SettingsService.DEFAULT_SETTINGS`, `hash_password`, `encrypt_secret`.
- Produces:
  - `await provision_studio(session, *, slug, name, bot_token, admin_username, admin_password) -> Studio` — создаёт студию (с зашифрованным токеном), studio_admin, дефолтные настройки (из `DEFAULT_SETTINGS`, привязанные к studio_id) и шаблон каталога (`CATALOG_TEMPLATE`).
  - `CATALOG_TEMPLATE: list[dict]` — список словарей-товаров шаблона.

- [ ] **Step 1: Создать тест `tests/services/test_studio_provisioning.py`**

```python
"""Тесты провижининга студии."""
import os
from cryptography.fernet import Fernet
import pytest
from sqlalchemy import select

from src.models.studio import Studio
from src.models.admin_user import AdminUser, AdminRole
from src.models.setting import Setting
from src.models.product import Product
from src.services.studio_provisioning import provision_studio
from src.services.crypto import decrypt_secret
from src.services.auth import verify_password


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_provision_creates_full_studio(db_session):
    studio = await provision_studio(
        db_session,
        slug="photo28",
        name="Photo28",
        bot_token="123:ABC",
        admin_username="owner",
        admin_password="pw12345",
    )
    assert studio.id is not None
    # Токен зашифрован
    assert studio.bot_token != "123:ABC"
    assert decrypt_secret(studio.bot_token) == "123:ABC"

    # Создан studio_admin
    admin = (await db_session.execute(
        select(AdminUser).where(AdminUser.studio_id == studio.id)
    )).scalar_one()
    assert admin.role == AdminRole.STUDIO_ADMIN
    assert verify_password("pw12345", admin.password_hash)

    # Дефолтные настройки и каталог привязаны к студии
    settings = (await db_session.execute(
        select(Setting).where(Setting.studio_id == studio.id)
    )).scalars().all()
    assert len(settings) > 0
    products = (await db_session.execute(
        select(Product).where(Product.studio_id == studio.id)
    )).scalars().all()
    assert len(products) > 0
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/services/test_studio_provisioning.py -v`
Expected: FAIL — нет модуля `src.services.studio_provisioning`.

- [ ] **Step 3: Создать `src/services/studio_provisioning.py`**

```python
"""Провижининг новой студии: тенант + админ + дефолтные настройки + шаблон каталога."""
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.studio import Studio
from src.models.admin_user import AdminUser, AdminRole
from src.models.setting import Setting
from src.models.product import Product
from src.services.auth import hash_password
from src.services.crypto import encrypt_secret
from src.services.settings_service import DEFAULT_SETTINGS

# Шаблон каталога типовых форматов (владелец потом правит цены в админке).
CATALOG_TEMPLATE = [
    {"slug": "classic_10x15", "name": "Классика 10×15", "short_name": "10×15",
     "emoji": "🖼", "price_per_unit": 25, "price_type": "per_unit",
     "aspect_ratio": 1.5, "sort_order": 1},
    {"slug": "polaroid", "name": "Полароид", "short_name": "Полароид",
     "emoji": "📸", "price_per_unit": 22, "price_type": "tiered",
     "pricing_group": "polaroid", "aspect_ratio": 0.84, "sort_order": 2},
    {"slug": "square_10x10", "name": "Квадрат 10×10", "short_name": "10×10",
     "emoji": "⬜", "price_per_unit": 23, "price_type": "per_unit",
     "aspect_ratio": 1.0, "sort_order": 3},
]


async def provision_studio(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    bot_token: str,
    admin_username: str,
    admin_password: str,
) -> Studio:
    """Создаёт студию и весь её стартовый набор данных."""
    studio = Studio(slug=slug, name=name, bot_token=encrypt_secret(bot_token))
    session.add(studio)
    await session.flush()  # получить studio.id до коммита

    session.add(AdminUser(
        username=admin_username,
        password_hash=hash_password(admin_password),
        role=AdminRole.STUDIO_ADMIN,
        studio_id=studio.id,
    ))

    for s in DEFAULT_SETTINGS:
        session.add(Setting(
            studio_id=studio.id,
            key=s["key"],
            value=s["value"],
            value_type=s["value_type"],
            display_name=s.get("display_name", ""),
            description=s.get("description", ""),
            group=s.get("group", "general"),
            sort_order=s.get("sort_order", 0),
        ))

    for p in CATALOG_TEMPLATE:
        session.add(Product(studio_id=studio.id, **p))

    await session.commit()
    await session.refresh(studio)
    return studio
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `pytest tests/services/test_studio_provisioning.py -v`
Expected: PASS.

- [ ] **Step 5: Создать CLI-скрипт `scripts/seed_studio.py`**

```python
"""CLI: создать студию. Запуск: python -m scripts.seed_studio --slug photo28 --name Photo28 --bot-token ... --admin-user owner --admin-pass ..."""
import argparse
import asyncio

from src.database import async_session, init_db
from src.services.studio_provisioning import provision_studio


async def _run(args):
    await init_db()
    async with async_session() as session:
        studio = await provision_studio(
            session,
            slug=args.slug,
            name=args.name,
            bot_token=args.bot_token,
            admin_username=args.admin_user,
            admin_password=args.admin_pass,
        )
    print(f"Создана студия id={studio.id} slug={studio.slug}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--bot-token", required=True)
    parser.add_argument("--admin-user", required=True)
    parser.add_argument("--admin-pass", required=True)
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Прогнать весь набор тестов**

Run: `pytest -v`
Expected: PASS — все тесты из `tests/` зелёные.

- [ ] **Step 7: Commit**

```bash
git add src/services/studio_provisioning.py scripts/seed_studio.py tests/services/test_studio_provisioning.py
git commit -m "feat: провижининг студии (тенант + админ + дефолтные настройки + шаблон каталога)"
```

---

## Что остаётся для Плана 2 (рантайм под-проекта №1)

Эти изменения сознательно вынесены, т.к. требуют протаскивания `studio_id` через рантайм-контекст:

- Перевод `src/config.py` на инфраструктуру-only (`DATABASE_URL`, `FERNET_KEY`, `SESSION_SECRET`); чтение реквизитов/токенов из записи студии.
- `DeliveryType` enum (`src/models/order.py:44-81`) — методы `display_name`/`delivery_cost`/`is_enabled` сейчас зовут `SettingsService.get(...)` без `studio_id`. Перенести в studio-scoped сервис или прокинуть `studio_id`.
- `PricingService` — перевести на `studio_id` (используется в `OrderService.recalculate_order_cost`).
- **Изоляция (carry-forward из финального ревью Плана 1):** `ProductService.get_product_by_id` нескоуплен по `studio_id`, поэтому `update_product`/`delete_product`/`toggle_product` могут изменить чужой товар по переданному id. Заскоупить (параметр/guard `studio_id` или assert `product.studio_id == self.studio_id`) **до** подключения админ-хендлеров. В Плане 1 недостижимо (нет studio-scoped вызывающего кода).
- `NotificationService` — `studio_id` для `SettingsService.get(...)` и `ProductService.get_product(...)`.
- Хендлеры бота (`src/bot/handlers/*.py`) — получать `studio_id` из middleware и передавать в сервисы.
- Webhook-мультибот: FastAPI-роут `/webhook/{token}`, реестр ботов, резолв студии по токену, per-bot изоляция ошибок, регистрация/снятие вебхука при создании/отключении студии.
- Админка: вход через `admin_users` (bcrypt), middleware ролей и зажатие `studio_id` для studio_admin, супер-админский CRUD студий и «смотреть как студия».
- Пути хранения фото → `storage/{studio_id}/{order_number}/...`.

## Self-Review (выполнено при написании)

- **Покрытие спека:** схема `studios`/`studio_id`/`admin_users`/`billing_events` — Tasks 2,4,5,6,7,8; пер-студийные кеши — Tasks 9,10; изоляция сервисов — Task 11; шифрование секретов — Task 3; bcrypt — Task 4; шаблон каталога + сидинг — Task 12. Рантайм (webhook, роли, конфиг) явно вынесен в План 2.
- **Плейсхолдеры:** не обнаружено — каждый шаг содержит полный код или точную команду.
- **Согласованность типов:** `studio_id: int` единообразно; сигнатуры кешей `get(studio_id, key, ...)` / `get_product(studio_id, product_id)` совпадают между определением (Tasks 9,10) и использованием (Task 12 через `DEFAULT_SETTINGS`); `provision_studio(...)` совпадает между Task 12 реализацией, тестом и CLI.
