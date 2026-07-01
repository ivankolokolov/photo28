"""Тесты авторизации админки (прямой вызов роутов/зависимостей)."""
import os
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from src.services.studio_provisioning import provision_studio
from src.admin import auth as auth_mod
from src.admin.auth import (
    authenticate, effective_studio_id, require_admin, require_studio,
    require_super_admin,
)
from src.models.admin_user import AdminRole
from tests.admin.conftest import (
    FakeRequest, use_test_session, seed_super_admin, seed_studio_admin, admin_session,
)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_authenticate_success_and_failure(db_session):
    await seed_super_admin(db_session, "root", "pw")
    assert (await authenticate(db_session, "root", "pw")) is not None
    assert (await authenticate(db_session, "root", "WRONG")) is None
    assert (await authenticate(db_session, "nobody", "pw")) is None


@pytest.mark.asyncio
async def test_login_sets_session(db_session, monkeypatch):
    app = use_test_session(monkeypatch, db_session)
    await seed_super_admin(db_session, "root", "pw")
    req = FakeRequest()
    resp = await app.login(req, username="root", password="pw")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert req.session["user_id"] is not None
    assert req.session["role"] == AdminRole.SUPER_ADMIN.value
    assert req.session["studio_id"] is None


@pytest.mark.asyncio
async def test_login_wrong_password(db_session, monkeypatch):
    app = use_test_session(monkeypatch, db_session)
    await seed_super_admin(db_session, "root", "pw")
    req = FakeRequest()
    resp = await app.login(req, username="root", password="WRONG")
    assert resp.status_code == 303
    assert "error=invalid" in resp.headers["location"]
    assert "user_id" not in req.session


@pytest.mark.asyncio
async def test_studio_admin_effective_studio_is_own(db_session):
    studio = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                                    admin_username="x", admin_password="x")
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=studio.id))
    assert effective_studio_id(req) == studio.id
    assert require_studio(req) == studio.id


def test_super_admin_without_active_studio_redirects_to_studios():
    req = FakeRequest(session=admin_session(AdminRole.SUPER_ADMIN.value, studio_id=None))
    assert effective_studio_id(req) is None
    with pytest.raises(HTTPException) as exc:
        require_studio(req)
    assert exc.value.status_code == 303
    assert exc.value.headers["Location"] == "/studios"


def test_super_admin_active_studio_resolves():
    req = FakeRequest(session=admin_session(AdminRole.SUPER_ADMIN.value, studio_id=None))
    req.session["active_studio_id"] = 7
    assert effective_studio_id(req) == 7
    assert require_studio(req) == 7


def test_require_super_admin_forbids_studio_admin():
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=1))
    with pytest.raises(HTTPException) as exc:
        require_super_admin(req)
    assert exc.value.status_code == 403


def test_require_admin_unauthenticated_redirects_to_login():
    req = FakeRequest(session={})
    with pytest.raises(HTTPException) as exc:
        require_admin(req)
    assert exc.value.status_code == 303
    assert exc.value.headers["Location"] == "/login"
