"""Тесты изоляции промокодов по студиям (studio_id-фильтр).

Стратегия: прямой вызов функций-обработчиков с FakeRequest (без TestClient).
"""
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select

from src.services.studio_provisioning import provision_studio
from src.models.admin_user import AdminRole
from src.models.promocode import Promocode
from tests.admin.conftest import (
    FakeRequest, use_test_session, admin_session,
)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


async def _make_promocode(db_session, studio_id: int, code: str = "PROMO10") -> Promocode:
    """Создаёт промокод для заданной студии и возвращает объект."""
    promo = Promocode(
        studio_id=studio_id,
        code=code,
        discount_percent=10,
    )
    db_session.add(promo)
    await db_session.commit()
    await db_session.refresh(promo)
    return promo


# ===========================================================================
# KEY SECURITY TESTS: studio_admin A cannot see/modify studio B's promocodes
# ===========================================================================

@pytest.mark.asyncio
async def test_promocodes_list_shows_only_own_studio(db_session, monkeypatch):
    """promocodes_list для студии A не показывает промокоды студии B."""
    s1 = await provision_studio(
        db_session, slug="pl1", name="Promo Studio A", bot_token="pt1",
        admin_username="pa1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="pl2", name="Promo Studio B", bot_token="pt2",
        admin_username="pa2", admin_password="pw",
    )
    await _make_promocode(db_session, s1.id, code="CODEA")
    await _make_promocode(db_session, s2.id, code="CODEB")

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.promocodes_list(req)

    assert resp.status_code == 200
    promocodes = resp.context["promocodes"]
    codes = [p.code for p in promocodes]
    assert "CODEA" in codes
    assert "CODEB" not in codes


@pytest.mark.asyncio
async def test_delete_cross_studio_404(db_session, monkeypatch):
    """studio_admin A пытается удалить промокод студии B → HTTPException 404."""
    s1 = await provision_studio(
        db_session, slug="pd1", name="Del Studio A", bot_token="dt1",
        admin_username="da1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="pd2", name="Del Studio B", bot_token="dt2",
        admin_username="da2", admin_password="pw",
    )
    promo_b = await _make_promocode(db_session, s2.id, code="DELB")

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))

    with pytest.raises(HTTPException) as exc_info:
        await app.delete_promocode(req, promo_id=promo_b.id)
    assert exc_info.value.status_code == 404

    # Промокод студии B должен остаться нетронутым
    result = await db_session.execute(
        select(Promocode).where(Promocode.id == promo_b.id)
    )
    still_exists = result.scalar_one_or_none()
    assert still_exists is not None


@pytest.mark.asyncio
async def test_toggle_cross_studio_404(db_session, monkeypatch):
    """studio_admin A пытается переключить промокод студии B → HTTPException 404."""
    s1 = await provision_studio(
        db_session, slug="pt1s", name="Tog Studio A", bot_token="tt1",
        admin_username="ta1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="pt2s", name="Tog Studio B", bot_token="tt2",
        admin_username="ta2", admin_password="pw",
    )
    promo_b = await _make_promocode(db_session, s2.id, code="TOGB")
    assert promo_b.is_active is True

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))

    with pytest.raises(HTTPException) as exc_info:
        await app.toggle_promocode(req, promo_id=promo_b.id)
    assert exc_info.value.status_code == 404

    # Промокод студии B должен остаться активным
    result = await db_session.execute(
        select(Promocode).where(Promocode.id == promo_b.id).execution_options(populate_existing=True)
    )
    reloaded = result.scalar_one()
    assert reloaded.is_active is True


# ===========================================================================
# HAPPY PATH: studio_admin создаёт промокод — привязывается к своей студии
# ===========================================================================

class FakeFormData(dict):
    """Имитирует starlette MultiDict / FormData для прямого вызова create_promocode."""
    def get(self, key, default=None):
        return super().get(key, default)


class FakeRequestWithForm(FakeRequest):
    """FakeRequest с поддержкой async form()."""

    def __init__(self, form_data: dict, **kwargs):
        super().__init__(**kwargs)
        self._form_data = FakeFormData(form_data)

    async def form(self):
        return self._form_data


@pytest.mark.asyncio
async def test_create_promocode_sets_studio_id(db_session, monkeypatch):
    """POST /promocodes создаёт промокод с studio_id текущей студии."""
    s1 = await provision_studio(
        db_session, slug="cp1", name="Create Studio A", bot_token="ct1",
        admin_username="ca1", admin_password="pw",
    )

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequestWithForm(
        form_data={
            "code": "NEWCODE",
            "discount_percent": "15",
            "discount_amount": "",
            "max_uses": "",
            "description": "Test promo",
            "min_order_amount": "0",
            "min_photos": "0",
            "require_subscription": "0",
        },
        session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id),
    )

    resp = await app.create_promocode(req)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/promocodes"

    # Промокод должен быть привязан к studio A
    result = await db_session.execute(
        select(Promocode).where(Promocode.code == "NEWCODE")
    )
    promo = result.scalar_one_or_none()
    assert promo is not None
    assert promo.studio_id == s1.id
    assert promo.discount_percent == 15


@pytest.mark.asyncio
async def test_delete_own_studio_promocode_ok(db_session, monkeypatch):
    """studio_admin A успешно удаляет свой промокод → 303."""
    s1 = await provision_studio(
        db_session, slug="do1", name="Own Studio A", bot_token="ot1",
        admin_username="oa1", admin_password="pw",
    )
    promo = await _make_promocode(db_session, s1.id, code="MYPROMO")

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.delete_promocode(req, promo_id=promo.id)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/promocodes"

    result = await db_session.execute(select(Promocode).where(Promocode.id == promo.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_toggle_own_studio_promocode_ok(db_session, monkeypatch):
    """studio_admin A успешно переключает свой промокод → is_active меняется."""
    s1 = await provision_studio(
        db_session, slug="to1", name="Toggle Own A", bot_token="tot1",
        admin_username="toa1", admin_password="pw",
    )
    promo = await _make_promocode(db_session, s1.id, code="MYTOG")
    assert promo.is_active is True

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.toggle_promocode(req, promo_id=promo.id)

    assert resp.status_code == 303

    result = await db_session.execute(
        select(Promocode).where(Promocode.id == promo.id).execution_options(populate_existing=True)
    )
    reloaded = result.scalar_one()
    assert reloaded.is_active is False
