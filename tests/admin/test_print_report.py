"""Тесты POST /api/print/report — billing_events + статус заказа (идемпотентно)."""
import os
import pytest
from decimal import Decimal
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select, func

from src.services.studio_provisioning import provision_studio
from src.services.print_agent_service import PrintAgentService
from src.services.order_service import OrderService
from src.services.product_service import ProductService
from src.models.order import OrderStatus
from src.models.photo import Photo
from src.models.billing_event import BillingEvent
from src.admin import print_api
from tests.admin.conftest import FakeRequest, use_test_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


async def _order_with_photos(db_session, studio, n=2, tg=1):
    svc = OrderService(db_session, studio.id)
    user = await svc.get_or_create_user(telegram_id=tg)
    order = await svc.create_order(user)
    await ProductService(db_session).load_cache(studio.id)
    product = ProductService.get_all_purchasable(studio.id)[0]
    for i in range(n):
        p = Photo(order_id=order.id, product_id=product.id, telegram_file_id=f"f{i}", position=i)
        db_session.add(p)
    await db_session.commit()
    await svc.update_order_status(order, OrderStatus.CONFIRMED)
    order = await svc.get_order_by_id(order.id)
    ids = [p.id for p in order.photos]
    return order, ids


async def _agent_req(db_session, studio):
    a = await PrintAgentService(db_session).create_pairing(studio.id)
    _, raw = await PrintAgentService(db_session).pair(a.pairing_code)
    return FakeRequest(headers={"authorization": f"Bearer {raw}"})


@pytest.mark.asyncio
async def test_report_creates_billing_idempotent(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    order, photo_ids = await _order_with_photos(db_session, a, n=2)
    req = await _agent_req(db_session, a)

    r1 = await print_api.report(req, payload={"order_id": order.id, "printed_photo_ids": photo_ids})
    assert r1["billed"] == 2
    count = (await db_session.execute(
        select(func.count(BillingEvent.id)).where(BillingEvent.order_id == order.id))).scalar()
    assert count == 2
    ev = (await db_session.execute(select(BillingEvent).limit(1))).scalar_one()
    assert ev.fee == Decimal("5.00")
    # повторный рапорт — идемпотентно
    r2 = await print_api.report(req, payload={"order_id": order.id, "printed_photo_ids": photo_ids})
    assert r2["billed"] == 0


@pytest.mark.asyncio
async def test_report_foreign_order_404(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    b = await provision_studio(db_session, slug="b", name="B", bot_token="t", admin_username="b", admin_password="p")
    order_b, ids_b = await _order_with_photos(db_session, b, n=1, tg=2)
    req_a = await _agent_req(db_session, a)
    with pytest.raises(HTTPException) as exc:
        await print_api.report(req_a, payload={"order_id": order_b.id, "printed_photo_ids": ids_b})
    assert exc.value.status_code == 404
