"""Пустой /report не должен уводить CONFIRMED-заказ в PRINTING."""
import os
import pytest
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.services.print_agent_service import PrintAgentService
from src.services.order_service import OrderService
from src.services.product_service import ProductService
from src.models.order import OrderStatus
from src.models.photo import Photo
from src.admin import print_api
from tests.admin.conftest import FakeRequest, use_test_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_empty_report_keeps_confirmed(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                               admin_username="a", admin_password="p")
    svc = OrderService(db_session, s.id)
    user = await svc.get_or_create_user(telegram_id=1)
    order = await svc.create_order(user)
    await ProductService(db_session).load_cache(s.id)
    product = ProductService.get_all_purchasable(s.id)[0]
    db_session.add(Photo(order_id=order.id, product_id=product.id, telegram_file_id="f", position=0))
    await db_session.commit()
    await svc.update_order_status(order, OrderStatus.CONFIRMED)

    ag = await PrintAgentService(db_session).create_pairing(s.id)
    _, raw = await PrintAgentService(db_session).pair(ag.pairing_code)
    req = FakeRequest(headers={"authorization": f"Bearer {raw}"})

    resp = await print_api.report(req, payload={"order_id": order.id, "printed_photo_ids": []})
    assert resp["billed"] == 0
    reloaded = await svc.get_order_by_id(order.id)
    assert reloaded.status == OrderStatus.CONFIRMED
