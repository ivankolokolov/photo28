"""Тест изоляции GET /api/print/jobs — агент видит только заказы своей студии."""
import pytest
from cryptography.fernet import Fernet
from src.services.studio_provisioning import provision_studio
from src.services.print_agent_service import PrintAgentService
from src.services.order_service import OrderService
from src.models.order import OrderStatus
from src.models.photo import Photo
from src.admin import print_api
from tests.admin.conftest import FakeRequest, use_test_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


async def _confirmed_order(db_session, studio, tg=1):
    svc = OrderService(db_session, studio.id)
    user = await svc.get_or_create_user(telegram_id=tg)
    order = await svc.create_order(user)
    # используем товар из шаблона каталога студии
    from src.services.product_service import ProductService
    await ProductService(db_session).load_cache(studio.id)
    product = ProductService.get_all_purchasable(studio.id)[0]
    db_session.add(Photo(order_id=order.id, product_id=product.id,
                         telegram_file_id="f1", position=0, crop_data='{"x":0}'))
    await db_session.commit()
    await svc.update_order_status(order, OrderStatus.CONFIRMED)
    return order


async def _agent_req(db_session, studio):
    a = await PrintAgentService(db_session).create_pairing(studio.id)
    _, raw = await PrintAgentService(db_session).pair(a.pairing_code)
    return FakeRequest(headers={"authorization": f"Bearer {raw}"})


@pytest.mark.asyncio
async def test_jobs_returns_only_own_confirmed(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    b = await provision_studio(db_session, slug="b", name="B", bot_token="t", admin_username="b", admin_password="p")
    order_a = await _confirmed_order(db_session, a, tg=1)
    await _confirmed_order(db_session, b, tg=2)
    req = await _agent_req(db_session, a)

    result = await print_api.jobs(req)
    ids = [j["order_id"] for j in result["jobs"]]
    assert ids == [order_a.id]
    assert result["jobs"][0]["photos"][0]["crop_data"] == '{"x":0}'
    assert result["jobs"][0]["photos"][0]["product_slug"]
