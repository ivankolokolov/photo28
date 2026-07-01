"""Тесты изоляции настроек и товаров по студиям.

Прямой вызов функций-обработчиков с FakeRequest (без TestClient).
"""
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from src.services.studio_provisioning import provision_studio
from src.models.admin_user import AdminRole
from src.models.product import Product
from src.models.setting import Setting, SettingType
from src.services.product_service import ProductService
from src.services.settings_service import SettingsService
from tests.admin.conftest import (
    FakeRequest, use_test_session, admin_session,
)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_setting(db_session, studio_id: int, key: str, value: str) -> Setting:
    s = Setting(
        studio_id=studio_id,
        key=key,
        value=value,
        value_type=SettingType.STRING,
        display_name=key,
        group="general",
        sort_order=1,
    )
    db_session.add(s)
    await db_session.commit()
    return s


async def _make_product(db_session, studio_id: int, slug: str) -> Product:
    p = Product(
        studio_id=studio_id,
        slug=slug,
        name=f"Product {slug}",
        short_name=slug,
        price_per_unit=100,
        is_active=True,
    )
    db_session.add(p)
    await db_session.commit()
    return p


# ===========================================================================
# SETTINGS ISOLATION
# ===========================================================================

@pytest.mark.asyncio
async def test_settings_page_shows_only_own_studio(db_session, monkeypatch):
    """settings_page для studio A показывает только свои настройки (не B)."""
    s1 = await provision_studio(
        db_session, slug="ss1", name="Studio A", bot_token="tok1",
        admin_username="sa1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="ss2", name="Studio B", bot_token="tok2",
        admin_username="sa2", admin_password="pw",
    )
    # Добавляем уникальную настройку для каждой студии
    await _make_setting(db_session, s1.id, "unique_key_a", "value_a")
    await _make_setting(db_session, s2.id, "unique_key_b", "value_b")

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.settings_page(req)

    assert resp.status_code == 200
    grouped = resp.context["grouped_settings"]
    all_keys = [s.key for group in grouped.values() for s in group]
    assert "unique_key_a" in all_keys
    assert "unique_key_b" not in all_keys


@pytest.mark.asyncio
async def test_save_settings_only_affects_own_studio(db_session, monkeypatch):
    """save_settings для studio A не меняет настройки studio B."""
    s1 = await provision_studio(
        db_session, slug="svs1", name="Save Studio A", bot_token="svtok1",
        admin_username="svsa1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="svs2", name="Save Studio B", bot_token="svtok2",
        admin_username="svsa2", admin_password="pw",
    )
    setting_b = await _make_setting(db_session, s2.id, "shared_key", "original_b")
    await _make_setting(db_session, s1.id, "shared_key", "original_a")

    class FakeFormRequest(FakeRequest):
        async def form(self):
            # Попытка обновить "shared_key" от имени studio A
            return {"setting_shared_key": "modified_by_a"}

    app = use_test_session(monkeypatch, db_session)
    req = FakeFormRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    await app.save_settings(req)

    # Проверяем что настройка B не изменилась
    svc_b = SettingsService(db_session)
    setting_b_refreshed = await svc_b.get_by_key(s2.id, "shared_key")
    assert setting_b_refreshed.value == "original_b"


# ===========================================================================
# PRODUCTS ISOLATION
# ===========================================================================

@pytest.mark.asyncio
async def test_products_list_shows_only_own_studio(db_session, monkeypatch):
    """products_list для studio A показывает только товары A (не B)."""
    s1 = await provision_studio(
        db_session, slug="pl1", name="Prod Studio A", bot_token="pt1",
        admin_username="pa1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="pl2", name="Prod Studio B", bot_token="pt2",
        admin_username="pa2", admin_password="pw",
    )
    ProductService.invalidate_cache()
    p_a = await _make_product(db_session, s1.id, "prod-a")
    p_b = await _make_product(db_session, s2.id, "prod-b")

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.products_list(req)

    assert resp.status_code == 200
    all_products = resp.context["all_products"]
    slugs = [p.slug for p in all_products]
    assert "prod-a" in slugs
    assert "prod-b" not in slugs


@pytest.mark.asyncio
async def test_update_product_cross_studio_returns_none(db_session, monkeypatch):
    """studio_admin A не может обновить товар студии B → возвращает None."""
    s1 = await provision_studio(
        db_session, slug="up1", name="Update Studio A", bot_token="ut1",
        admin_username="ua1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="up2", name="Update Studio B", bot_token="ut2",
        admin_username="ua2", admin_password="pw",
    )
    ProductService.invalidate_cache()
    p_b = await _make_product(db_session, s2.id, "update-prod-b")

    svc = ProductService(db_session)
    # studio A (id=s1.id) пытается обновить товар студии B
    result = await svc.update_product(p_b.id, studio_id=s1.id, name="HACKED")
    assert result is None

    # Товар B не изменился
    fresh = await svc.get_product_by_id(p_b.id)
    assert fresh.name == f"Product update-prod-b"


@pytest.mark.asyncio
async def test_delete_product_cross_studio_returns_false(db_session, monkeypatch):
    """studio_admin A не может удалить товар студии B → возвращает False, товар жив."""
    s1 = await provision_studio(
        db_session, slug="dp1", name="Del Studio A", bot_token="dt1",
        admin_username="da1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="dp2", name="Del Studio B", bot_token="dt2",
        admin_username="da2", admin_password="pw",
    )
    ProductService.invalidate_cache()
    p_b = await _make_product(db_session, s2.id, "del-prod-b")

    svc = ProductService(db_session)
    result = await svc.delete_product(p_b.id, studio_id=s1.id)
    assert result is False

    # Товар B всё ещё существует
    still_alive = await svc.get_product_by_id(p_b.id)
    assert still_alive is not None


@pytest.mark.asyncio
async def test_toggle_product_cross_studio_returns_none(db_session, monkeypatch):
    """studio_admin A не может переключить товар студии B → возвращает None."""
    s1 = await provision_studio(
        db_session, slug="tp1", name="Tog Studio A", bot_token="tt1",
        admin_username="ta1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="tp2", name="Tog Studio B", bot_token="tt2",
        admin_username="ta2", admin_password="pw",
    )
    ProductService.invalidate_cache()
    p_b = await _make_product(db_session, s2.id, "tog-prod-b")
    original_active = p_b.is_active

    svc = ProductService(db_session)
    result = await svc.toggle_product(p_b.id, studio_id=s1.id)
    assert result is None

    # Статус B не изменился
    fresh = await svc.get_product_by_id(p_b.id)
    assert fresh.is_active == original_active


@pytest.mark.asyncio
async def test_update_product_route_cross_studio_404(db_session, monkeypatch):
    """POST /products/{id}/update от studio A для товара B → HTTPException 404."""
    s1 = await provision_studio(
        db_session, slug="upr1", name="Route Studio A", bot_token="rt1",
        admin_username="ra1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="upr2", name="Route Studio B", bot_token="rt2",
        admin_username="ra2", admin_password="pw",
    )
    ProductService.invalidate_cache()
    p_b = await _make_product(db_session, s2.id, "route-prod-b")

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))

    with pytest.raises(HTTPException) as exc_info:
        await app.update_product(
            req, product_id=p_b.id,
            name="HACKED", short_name="H", emoji="📷",
            description="", price_per_unit=0, price_type="per_unit",
            price_tiers_json="", pricing_group="", aspect_ratio=None, sort_order=0,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_product_route_cross_studio_404(db_session, monkeypatch):
    """POST /products/{id}/delete от studio A для товара B → HTTPException 404."""
    s1 = await provision_studio(
        db_session, slug="dpr1", name="DRoute Studio A", bot_token="drt1",
        admin_username="dra1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="dpr2", name="DRoute Studio B", bot_token="drt2",
        admin_username="dra2", admin_password="pw",
    )
    ProductService.invalidate_cache()
    p_b = await _make_product(db_session, s2.id, "droute-prod-b")

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))

    with pytest.raises(HTTPException) as exc_info:
        await app.delete_product(req, product_id=p_b.id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_toggle_product_route_cross_studio_404(db_session, monkeypatch):
    """POST /products/{id}/toggle от studio A для товара B → HTTPException 404."""
    s1 = await provision_studio(
        db_session, slug="tpr1", name="TRoute Studio A", bot_token="trt1",
        admin_username="tra1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="tpr2", name="TRoute Studio B", bot_token="trt2",
        admin_username="tra2", admin_password="pw",
    )
    ProductService.invalidate_cache()
    p_b = await _make_product(db_session, s2.id, "troute-prod-b")

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))

    with pytest.raises(HTTPException) as exc_info:
        await app.toggle_product(req, product_id=p_b.id)
    assert exc_info.value.status_code == 404


# ===========================================================================
# HAPPY PATH: studio_admin CAN access their own settings/products
# ===========================================================================

@pytest.mark.asyncio
async def test_settings_page_own_studio_ok(db_session, monkeypatch):
    """settings_page для studio A — 200 OK."""
    s1 = await provision_studio(
        db_session, slug="hp_ss1", name="Happy Settings A", bot_token="hst1",
        admin_username="hsa1", admin_password="pw",
    )
    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.settings_page(req)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_products_list_own_studio_ok(db_session, monkeypatch):
    """products_list для studio A — 200 OK, товар A виден."""
    s1 = await provision_studio(
        db_session, slug="hp_pl1", name="Happy Prod A", bot_token="hpt1",
        admin_username="hpa1", admin_password="pw",
    )
    ProductService.invalidate_cache()
    await _make_product(db_session, s1.id, "my-prod")

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.products_list(req)

    assert resp.status_code == 200
    slugs = [p.slug for p in resp.context["all_products"]]
    assert "my-prod" in slugs


@pytest.mark.asyncio
async def test_update_product_own_studio_ok(db_session, monkeypatch):
    """update_product для своего товара — редирект 303."""
    s1 = await provision_studio(
        db_session, slug="hp_up1", name="Happy Update A", bot_token="hut1",
        admin_username="hua1", admin_password="pw",
    )
    ProductService.invalidate_cache()
    p = await _make_product(db_session, s1.id, "my-update-prod")

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.update_product(
        req, product_id=p.id,
        name="Updated Name", short_name="U", emoji="📷",
        description="", price_per_unit=50, price_type="per_unit",
        price_tiers_json="", pricing_group="", aspect_ratio=None, sort_order=0,
    )
    assert resp.status_code == 303
