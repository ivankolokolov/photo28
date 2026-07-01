"""Тесты изоляции заказов по студиям + happy-path для migrated order routes.

Стратегия: прямой вызов функций-обработчиков с FakeRequest (без TestClient).
"""
import os
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from src.services.studio_provisioning import provision_studio
from src.services.order_service import OrderService
from src.models.admin_user import AdminRole
from src.models.order import OrderStatus
from tests.admin.conftest import (
    FakeRequest, use_test_session, admin_session,
)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


# ---------------------------------------------------------------------------
# Helper: create a non-draft order in a studio
# ---------------------------------------------------------------------------

async def _make_order(db_session, studio_id: int) -> int:
    """Creates a PENDING_PAYMENT order in the given studio and returns its id."""
    svc = OrderService(db_session, studio_id)
    user = await svc.get_or_create_user(telegram_id=10001 + studio_id, username="tester")
    order = await svc.create_order(user)
    await svc.update_order_status(order, OrderStatus.PENDING_PAYMENT)
    return order.id


# ===========================================================================
# KEY SECURITY TESTS: studio_admin A cannot see/modify studio B's orders
# ===========================================================================

@pytest.mark.asyncio
async def test_order_detail_cross_studio_404(db_session, monkeypatch):
    """studio_admin A requests studio B's order_id → HTTPException 404."""
    s1 = await provision_studio(
        db_session, slug="s1", name="Studio A", bot_token="tok1",
        admin_username="a1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="s2", name="Studio B", bot_token="tok2",
        admin_username="a2", admin_password="pw",
    )
    order_b_id = await _make_order(db_session, s2.id)

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))

    with pytest.raises(HTTPException) as exc_info:
        await app.order_detail(req, order_id=order_b_id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_order_status_cross_studio_404(db_session, monkeypatch):
    """studio_admin A trying to change studio B's order status → HTTPException 404."""
    s1 = await provision_studio(
        db_session, slug="s1a", name="Studio A2", bot_token="tok1a",
        admin_username="aa1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="s2a", name="Studio B2", bot_token="tok2a",
        admin_username="aa2", admin_password="pw",
    )
    order_b_id = await _make_order(db_session, s2.id)

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))

    with pytest.raises(HTTPException) as exc_info:
        await app.update_order_status(req, order_id=order_b_id, status="confirmed", notify_client=False)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_orders_list_shows_only_own_studio(db_session, monkeypatch):
    """orders_list for studio A returns only studio A's orders (not B's)."""
    s1 = await provision_studio(
        db_session, slug="ls1", name="List Studio A", bot_token="lt1",
        admin_username="la1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="ls2", name="List Studio B", bot_token="lt2",
        admin_username="la2", admin_password="pw",
    )
    await _make_order(db_session, s1.id)
    await _make_order(db_session, s2.id)

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.orders_list(req, page=1)

    assert resp.status_code == 200
    orders = resp.context["orders"]
    assert len(orders) == 1
    assert orders[0].studio_id == s1.id


@pytest.mark.asyncio
async def test_dashboard_shows_only_own_studio(db_session, monkeypatch):
    """dashboard for studio A stats only counts studio A's orders."""
    s1 = await provision_studio(
        db_session, slug="ds1", name="Dash Studio A", bot_token="dt1",
        admin_username="da1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="ds2", name="Dash Studio B", bot_token="dt2",
        admin_username="da2", admin_password="pw",
    )
    # Create 2 orders for s1, 3 for s2
    for _ in range(2):
        await _make_order(db_session, s1.id)
    for _ in range(3):
        await _make_order(db_session, s2.id)

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.dashboard(req)

    assert resp.status_code == 200
    stats = resp.context["stats"]
    # s1 has 2 orders, s2 has 3 — dashboard must only see s1's 2
    assert stats["total_orders"] == 2


# ===========================================================================
# HAPPY PATH: studio_admin CAN access their own orders
# ===========================================================================

@pytest.mark.asyncio
async def test_order_detail_own_studio_ok(db_session, monkeypatch):
    """studio_admin A can view their own order → 200."""
    s1 = await provision_studio(
        db_session, slug="hp1", name="Happy Studio A", bot_token="ht1",
        admin_username="ha1", admin_password="pw",
    )
    order_id = await _make_order(db_session, s1.id)

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.order_detail(req, order_id=order_id)

    assert resp.status_code == 200
    # Must NOT pass ProductService class to template; instead pass pre-resolved dict
    assert "ProductService" not in resp.context
    assert "photos_by_product" in resp.context


@pytest.mark.asyncio
async def test_unauthenticated_order_detail_redirects(db_session, monkeypatch):
    """Unauthenticated request to order_detail raises HTTPException 303 → /login."""
    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session={})  # no user_id

    with pytest.raises(HTTPException) as exc_info:
        await app.order_detail(req, order_id=999)
    assert exc_info.value.status_code == 303
    assert "/login" in exc_info.value.headers["Location"]


@pytest.mark.asyncio
async def test_super_admin_without_studio_redirects_to_studios(db_session, monkeypatch):
    """super_admin who hasn't picked a studio → HTTPException 303 → /studios."""
    app = use_test_session(monkeypatch, db_session)
    # super_admin with no active_studio_id in session
    req = FakeRequest(session=admin_session(AdminRole.SUPER_ADMIN.value, studio_id=None))

    with pytest.raises(HTTPException) as exc_info:
        await app.order_detail(req, order_id=1)
    assert exc_info.value.status_code == 303
    assert "/studios" in exc_info.value.headers["Location"]
