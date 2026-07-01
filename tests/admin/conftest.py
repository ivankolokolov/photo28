"""Хелперы для тестов админки.

Роуты тестируем ВЫЗОВОМ функций-обработчиков напрямую (с фейковым Request) на
том же event loop, что и тестовая БД-сессия. Это надёжнее TestClient: TestClient
гоняет приложение на отдельном loop'е, а asyncpg-соединение тестовой db_session
привязано к loop'у теста → иначе «Future attached to a different loop».
"""
import contextlib
from types import SimpleNamespace

from src.services.auth import hash_password
from src.models.admin_user import AdminUser, AdminRole


class FakeRequest:
    """Минимальный заменитель starlette Request для прямого вызова роутов."""
    def __init__(self, session=None, path="/", scheme="http", client_host="test",
                 query_params=None):
        self.session = session if session is not None else {}
        self.url = SimpleNamespace(path=path, scheme=scheme)
        self.client = SimpleNamespace(host=client_host)
        self.query_params = query_params or {}
        self.headers = {}


def use_test_session(monkeypatch, db_session):
    """Подменяет src.admin.app.async_session на фабрику, отдающую тестовую сессию."""
    import src.admin.app as app_module

    @contextlib.asynccontextmanager
    async def _factory():
        yield db_session

    monkeypatch.setattr(app_module, "async_session", _factory)
    return app_module


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


def admin_session(role, studio_id=None, user_id=1, username="u"):
    """Готовый session-словарь залогиненного админа для FakeRequest."""
    return {"user_id": user_id, "username": username, "role": role, "studio_id": studio_id}
