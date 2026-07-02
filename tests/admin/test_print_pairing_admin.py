"""Тест: admin-роут POST /print-agent/pairing создаёт запись PrintAgent."""
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from src.services.studio_provisioning import provision_studio
from src.models.print_agent import PrintAgent
from tests.admin.conftest import FakeRequest, use_test_session, admin_session
from src.models.admin_user import AdminRole


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_studio_admin_creates_pairing_code(db_session, monkeypatch):
    app = use_test_session(monkeypatch, db_session)
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                               admin_username="a", admin_password="p")
    req = FakeRequest(session=admin_session(AdminRole.STUDIO_ADMIN.value, studio_id=s.id))
    await app.create_print_pairing(req)
    agent = (await db_session.execute(
        select(PrintAgent).where(PrintAgent.studio_id == s.id))).scalar_one()
    assert agent.pairing_code
