"""Admin /analytics route: studio isolation test."""
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from src.services.studio_provisioning import provision_studio
from src.services.order_service import OrderService
from src.models.admin_user import AdminRole
from src.models.order import OrderStatus, Order
from sqlalchemy import update
from tests.admin.conftest import FakeRequest, use_test_session, admin_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


async def _make_paid_order(db_session, studio_id: int, photos_cost: int = 1000):
    svc = OrderService(db_session, studio_id)
    user = await svc.get_or_create_user(telegram_id=8000 + studio_id, username="tester")
    order = await svc.create_order(user)
    await db_session.execute(
        update(Order).where(Order.id == order.id).values(
            status=OrderStatus.PAID, photos_cost=photos_cost, delivery_cost=0, discount=0,
        )
    )
    await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_analytics_studio_admin_sees_only_own(db_session, monkeypatch):
    """studio_admin A's /analytics only shows A's revenue, not B's."""
    s1 = await provision_studio(
        db_session, slug="an1", name="Analytics Studio A", bot_token="tok1",
        admin_username="an_a1", admin_password="pw",
    )
    s2 = await provision_studio(
        db_session, slug="an2", name="Analytics Studio B", bot_token="tok2",
        admin_username="an_a2", admin_password="pw",
    )
    await _make_paid_order(db_session, s1.id, photos_cost=4000)
    await _make_paid_order(db_session, s2.id, photos_cost=9999)

    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s1.id))
    resp = await app.analytics_page(req)

    assert resp.status_code == 200
    summary = resp.context["summary"]
    # s1 has 1 paid order with revenue=4000; s2's 9999 must NOT appear
    assert summary["revenue"]["month_orders"] == 1
    assert summary["revenue"]["month"] == 4000


@pytest.mark.asyncio
async def test_analytics_unauthenticated_raises_303(db_session, monkeypatch):
    """Unauthenticated /analytics raises 303 redirect."""
    app = use_test_session(monkeypatch, db_session)
    req = FakeRequest(session={})

    with pytest.raises(HTTPException) as exc_info:
        await app.analytics_page(req)
    assert exc_info.value.status_code == 303
