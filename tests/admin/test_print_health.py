import os, pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from src.services.studio_provisioning import provision_studio
from src.services.print_agent_service import PrintAgentService
from src.models.print_agent import PrintAgent
from src.admin import print_api
from tests.admin.conftest import FakeRequest, use_test_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_health_updates_agent(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t", admin_username="a", admin_password="p")
    ag = await PrintAgentService(db_session).create_pairing(s.id)
    _, raw = await PrintAgentService(db_session).pair(ag.pairing_code)
    req = FakeRequest(headers={"authorization": f"Bearer {raw}"})

    resp = await print_api.health(req, payload={"printer_status": "ready", "queue_len": 3})
    assert resp["ok"] is True
    reloaded = (await db_session.execute(
        select(PrintAgent).where(PrintAgent.id == ag.id))).scalar_one()
    assert reloaded.printer_status == "ready"
    assert reloaded.queue_len == 3
    assert reloaded.last_seen_at is not None
