"""Тесты навигации по ролям: base_context + рендер base.html."""
import pytest
from cryptography.fernet import Fernet

from src.models.admin_user import AdminRole
from tests.admin.conftest import FakeRequest, admin_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


# ── helpers ────────────────────────────────────────────────────────────────

def _make_super_admin_req(active_studio_id=None):
    sess = admin_session(AdminRole.SUPER_ADMIN.value, studio_id=None, username="root")
    if active_studio_id is not None:
        sess["active_studio_id"] = active_studio_id
    return FakeRequest(session=sess)


def _make_studio_admin_req(studio_id=1):
    return FakeRequest(session=admin_session(
        AdminRole.STUDIO_ADMIN.value, studio_id=studio_id, username="alice"
    ))


# ── base_context tests ──────────────────────────────────────────────────────

def test_base_context_contains_admin_for_super_admin():
    """base_context возвращает admin dict с ролью super_admin."""
    from src.admin.app import base_context
    req = _make_super_admin_req()
    ctx = base_context(req)
    assert ctx["admin"]["role"] == AdminRole.SUPER_ADMIN.value
    assert ctx["admin"]["username"] == "root"


def test_base_context_contains_admin_for_studio_admin():
    """base_context возвращает admin dict с ролью studio_admin."""
    from src.admin.app import base_context
    req = _make_studio_admin_req(studio_id=3)
    ctx = base_context(req)
    assert ctx["admin"]["role"] == AdminRole.STUDIO_ADMIN.value
    assert ctx["admin"]["username"] == "alice"


def test_base_context_includes_extra_kwargs():
    """Дополнительные kwargs пробрасываются в контекст."""
    from src.admin.app import base_context
    req = _make_super_admin_req()
    ctx = base_context(req, stats={"total": 5})
    assert ctx["stats"] == {"total": 5}


def test_base_context_has_request_key():
    """Контекст содержит 'request' (нужен шаблонизатору)."""
    from src.admin.app import base_context
    req = _make_super_admin_req()
    ctx = base_context(req)
    assert ctx["request"] is req


# ── template render tests ───────────────────────────────────────────────────

def _render_base(session_dict, active_studio_name=None):
    """Рендерит base.html через Jinja2 env из src.admin.app, возвращает HTML."""
    from src.admin.app import templates
    from types import SimpleNamespace

    req = FakeRequest(session=session_dict)
    ctx = {
        "request": req,
        "admin": {
            "user_id": session_dict["user_id"],
            "username": session_dict.get("username", "u"),
            "role": session_dict["role"],
            "studio_id": session_dict.get("studio_id"),
        },
        "active_studio_name": active_studio_name,
    }
    template = templates.get_template("base.html")
    return template.render(ctx)


def test_super_admin_sees_studios_link():
    """super_admin видит ссылку /studios в навигации."""
    sess = admin_session(AdminRole.SUPER_ADMIN.value, studio_id=None, username="root")
    html = _render_base(sess)
    assert "/studios" in html


def test_studio_admin_does_not_see_studios_link():
    """studio_admin НЕ видит ссылку /studios в навигации."""
    sess = admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=1, username="alice")
    html = _render_base(sess)
    assert "/studios" not in html


def test_bot_control_link_removed():
    """Ссылка /bot-control отсутствует в base.html для обеих ролей."""
    for role, sid in [
        (AdminRole.SUPER_ADMIN.value, None),
        (AdminRole.STUDIO_ADMIN.value, 1),
    ]:
        sess = admin_session(role, studio_id=sid, username="u")
        html = _render_base(sess)
        assert "/bot-control" not in html, f"bot-control found for role={role}"
        assert "🤖 Бот" not in html, f"'🤖 Бот' found for role={role}"


def test_nav_shows_admin_username():
    """Имя залогиненного пользователя отображается в шапке."""
    sess = admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=2, username="alice")
    html = _render_base(sess)
    assert "alice" in html


def test_super_admin_with_active_studio_shows_studio_name():
    """super_admin с active_studio_name видит название студии."""
    sess = admin_session(AdminRole.SUPER_ADMIN.value, studio_id=None, username="root")
    html = _render_base(sess, active_studio_name="Студия Тест")
    assert "Студия Тест" in html


def test_super_admin_without_active_studio_shows_select_prompt():
    """super_admin без активной студии видит '— выберите студию'."""
    sess = admin_session(AdminRole.SUPER_ADMIN.value, studio_id=None, username="root")
    html = _render_base(sess, active_studio_name=None)
    assert "выберите студию" in html


def test_super_admin_with_active_studio_shows_exit_button():
    """super_admin с активной студией видит кнопку выхода из студии."""
    sess = admin_session(AdminRole.SUPER_ADMIN.value, studio_id=None, username="root")
    html = _render_base(sess, active_studio_name="Студия А")
    assert "exit-view" in html


def test_super_admin_without_active_studio_no_exit_button():
    """super_admin без активной студии НЕ видит кнопку выхода."""
    sess = admin_session(AdminRole.SUPER_ADMIN.value, studio_id=None, username="root")
    html = _render_base(sess, active_studio_name=None)
    assert "exit-view" not in html
