"""Тест модели PrintAgent."""
import pytest
from sqlalchemy import select
from src.models.studio import Studio
from src.models.print_agent import PrintAgent


@pytest.mark.asyncio
async def test_create_print_agent(db_session):
    s = Studio(slug="s1", name="S1")
    db_session.add(s)
    await db_session.commit()
    agent = PrintAgent(studio_id=s.id, name="Касса-1", pairing_code="ABC123")
    db_session.add(agent)
    await db_session.commit()
    loaded = (await db_session.execute(select(PrintAgent))).scalar_one()
    assert loaded.studio_id == s.id
    assert loaded.pairing_code == "ABC123"
    assert loaded.token_hash is None
    assert loaded.queue_len == 0
