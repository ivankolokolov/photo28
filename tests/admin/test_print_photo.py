import io

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from src.services.studio_provisioning import provision_studio
from src.services.print_agent_service import PrintAgentService
from src.services.order_service import OrderService
from src.models.photo import Photo
from src.admin import print_api
from tests.admin.conftest import FakeRequest, use_test_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


async def _order_photo(db_session, studio, tg=1):
    svc = OrderService(db_session, studio.id)
    user = await svc.get_or_create_user(telegram_id=tg)
    order = await svc.create_order(user)
    from src.services.product_service import ProductService
    await ProductService(db_session).load_cache(studio.id)
    product = ProductService.get_all_purchasable(studio.id)[0]
    photo = Photo(order_id=order.id, product_id=product.id, telegram_file_id="f1", position=0)
    db_session.add(photo)
    await db_session.commit()
    return photo


async def _agent_req(db_session, studio):
    a = await PrintAgentService(db_session).create_pairing(studio.id)
    _, raw = await PrintAgentService(db_session).pair(a.pairing_code)
    return FakeRequest(headers={"authorization": f"Bearer {raw}"})


@pytest.mark.asyncio
async def test_photo_foreign_studio_404(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    b = await provision_studio(db_session, slug="b", name="B", bot_token="t", admin_username="b", admin_password="p")
    photo_b = await _order_photo(db_session, b, tg=2)
    req_a = await _agent_req(db_session, a)
    with pytest.raises(HTTPException) as exc:
        await print_api.photo(req_a, photo_id=photo_b.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_photo_own_studio_streams(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    a = await provision_studio(db_session, slug="a", name="A", bot_token="t", admin_username="a", admin_password="p")
    photo_a = await _order_photo(db_session, a, tg=1)
    req_a = await _agent_req(db_session, a)

    # мок загрузки из Telegram
    class _FakeFile:
        file_path = "x.jpg"

    class _FakeBot:
        def __init__(self, token):
            pass

        async def get_file(self, fid):
            return _FakeFile()

        async def download_file(self, path):
            return io.BytesIO(b"IMG")

        @property
        def session(self):
            class _S:
                async def close(self):
                    pass

            return _S()

    monkeypatch.setattr(print_api, "Bot", _FakeBot)

    resp = await print_api.photo(req_a, photo_id=photo_a.id)
    assert resp.status_code == 200
