"""Тесты пайринга/аутентификации агента печати."""
import pytest
from src.models.studio import Studio
from src.services.print_agent_service import PrintAgentService


async def _studio(db_session, slug="s1"):
    s = Studio(slug=slug, name=slug)
    db_session.add(s)
    await db_session.commit()
    return s


@pytest.mark.asyncio
async def test_create_pairing_generates_code(db_session):
    s = await _studio(db_session)
    svc = PrintAgentService(db_session)
    agent = await svc.create_pairing(s.id, name="Касса")
    assert agent.pairing_code
    assert agent.token_hash is None
    assert agent.studio_id == s.id


@pytest.mark.asyncio
async def test_pair_exchanges_code_for_token(db_session):
    s = await _studio(db_session)
    svc = PrintAgentService(db_session)
    agent = await svc.create_pairing(s.id)
    code = agent.pairing_code

    result = await svc.pair(code)
    assert result is not None
    paired, raw_token = result
    assert paired.id == agent.id
    assert paired.pairing_code is None
    assert paired.token_hash == PrintAgentService._hash_token(raw_token)
    # код больше не работает
    assert await svc.pair(code) is None


@pytest.mark.asyncio
async def test_authenticate_by_token(db_session):
    s = await _studio(db_session)
    svc = PrintAgentService(db_session)
    agent = await svc.create_pairing(s.id)
    _, raw = await svc.pair(agent.pairing_code)

    authed = await svc.authenticate(raw)
    assert authed is not None
    assert authed.id == agent.id
    assert authed.studio_id == s.id
    assert await svc.authenticate("garbage") is None
