"""Тесты Print API: пайринг + аутентификация."""
import os
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from src.services.studio_provisioning import provision_studio
from src.services.print_agent_service import PrintAgentService
from src.admin import print_api
from tests.admin.conftest import FakeRequest, use_test_session


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_pair_endpoint_returns_token(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                               admin_username="a", admin_password="p")
    agent = await PrintAgentService(db_session).create_pairing(s.id)
    resp = await print_api.pair(FakeRequest(), payload={"code": agent.pairing_code})
    assert "token" in resp
    assert resp["token"]


@pytest.mark.asyncio
async def test_pair_bad_code_404(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    with pytest.raises(HTTPException) as exc:
        await print_api.pair(FakeRequest(), payload={"code": "nope"})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_agent_valid_and_invalid(db_session, monkeypatch):
    use_test_session(monkeypatch, db_session)
    s = await provision_studio(db_session, slug="s1", name="S1", bot_token="t",
                               admin_username="a", admin_password="p")
    agent = await PrintAgentService(db_session).create_pairing(s.id)
    _, raw = await PrintAgentService(db_session).pair(agent.pairing_code)

    req = FakeRequest(headers={"authorization": f"Bearer {raw}"})
    resolved = await print_api.resolve_agent(req, db_session)
    assert resolved.studio_id == s.id

    with pytest.raises(HTTPException) as exc:
        await print_api.resolve_agent(FakeRequest(headers={}), db_session)
    assert exc.value.status_code == 401
