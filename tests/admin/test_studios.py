"""Тесты управления студиями (прямой вызов роутов).

Стратегия: вызываем функции-обработчики напрямую с FakeRequest,
минуя TestClient/Starlette, чтобы избежать проблем с asyncpg + event loop.
"""
import os
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select

from src.services.studio_provisioning import provision_studio
from src.models.studio import Studio
from src.models.admin_user import AdminRole
from tests.admin.conftest import (
    FakeRequest, use_test_session, seed_super_admin, seed_studio_admin, admin_session,
)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_super_admin_lists_studios(db_session, monkeypatch):
    """super_admin видит список студий."""
    await provision_studio(
        db_session, slug="s1", name="Studio One", bot_token="t",
        admin_username="a", admin_password="x",
    )
    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.SUPER_ADMIN.value))
    resp = await app.studios_list(req)
    assert resp.status_code == 200
    studios = resp.context["studios"]
    assert any(s.name == "Studio One" for s in studios)


@pytest.mark.asyncio
async def test_studio_admin_forbidden(db_session, monkeypatch):
    """studio_admin не может открыть /studios — HTTPException 403."""
    studio = await provision_studio(
        db_session, slug="s1", name="S1", bot_token="t",
        admin_username="a", admin_password="x",
    )
    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=studio.id))
    with pytest.raises(HTTPException) as exc:
        await app.studios_list(req)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_studio(db_session, monkeypatch):
    """POST /studios создаёт студию и редиректит на /studios."""
    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.SUPER_ADMIN.value))
    resp = await app.studios_create(
        req,
        slug="newstudio",
        name="New Studio",
        bot_token="fake_token",
        admin_username="newadmin",
        admin_password="securepass",
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/studios"
    # Проверяем, что студия создана в БД
    result = await db_session.execute(select(Studio).where(Studio.slug == "newstudio"))
    studio = result.scalar_one_or_none()
    assert studio is not None
    assert studio.name == "New Studio"


@pytest.mark.asyncio
async def test_toggle_killswitch(db_session, monkeypatch):
    """POST /studios/{id}/toggle инвертирует is_active."""
    studio = await provision_studio(
        db_session, slug="s1", name="S1", bot_token="t",
        admin_username="a", admin_password="x",
    )
    assert studio.is_active is True
    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.SUPER_ADMIN.value))
    resp = await app.studios_toggle(req, studio_id=studio.id)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/studios"
    # Перезагружаем из БД через явный SELECT
    studio_id = studio.id
    result = await db_session.execute(
        select(Studio).where(Studio.id == studio_id).execution_options(populate_existing=True)
    )
    reloaded = result.scalar_one()
    assert reloaded.is_active is False


@pytest.mark.asyncio
async def test_view_as(db_session, monkeypatch):
    """POST /studios/{id}/view-as записывает active_studio_id в сессию."""
    studio = await provision_studio(
        db_session, slug="s1", name="S1", bot_token="t",
        admin_username="a", admin_password="x",
    )
    app = use_test_session(monkeypatch, db_session)
    sess = admin_session(AdminRole.SUPER_ADMIN.value)
    req = FakeRequest(session=sess)
    resp = await app.studios_view_as(req, studio_id=studio.id)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert req.session["active_studio_id"] == studio.id


@pytest.mark.asyncio
async def test_exit_view(db_session, monkeypatch):
    """POST /studios/exit-view удаляет active_studio_id из сессии."""
    studio = await provision_studio(
        db_session, slug="s1", name="S1", bot_token="t",
        admin_username="a", admin_password="x",
    )
    app = use_test_session(monkeypatch, db_session)
    sess = admin_session(AdminRole.SUPER_ADMIN.value)
    sess["active_studio_id"] = studio.id
    req = FakeRequest(session=sess)
    resp = await app.studios_exit_view(req)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/studios"
    assert "active_studio_id" not in req.session
