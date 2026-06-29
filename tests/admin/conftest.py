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


@contextlib.asynccontextmanager
async def _noop_lifespan(app):
    """No-op lifespan для тестов — пропускаем прогрев кешей."""
    yield


@pytest.fixture
def admin_client(db_session, monkeypatch):
    """TestClient с подменённым async_session на тестовую сессию."""
    import src.admin.app as app_module
    monkeypatch.setattr(app_module, "async_session", _session_factory(db_session))
    # Lifespan использует старые сигнатуры — подменяем на no-op для тестов.
    app_module.app.router.lifespan_context = _noop_lifespan
    client = TestClient(app_module.app)
    with client:
        # Патчим wait_shutdown, чтобы также закрывать stream_receive.
        # Starlette TestClient оставляет его открытым, что вызывает ResourceWarning
        # в __del__ при GC в последующих async-тестах (баг Starlette/anyio + Python 3.9).
        _orig_wait_shutdown = client.wait_shutdown

        async def _patched_wait_shutdown() -> None:
            await _orig_wait_shutdown()
            await client.stream_receive.aclose()

        client.wait_shutdown = _patched_wait_shutdown
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
