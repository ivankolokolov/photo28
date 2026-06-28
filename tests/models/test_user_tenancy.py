"""Тесты тенантности User."""
import pytest
from sqlalchemy import select

from src.models.studio import Studio
from src.models.user import User


@pytest.mark.asyncio
async def test_same_telegram_id_two_studios_allowed(db_session):
    s1 = Studio(slug="s1", name="S1")
    s2 = Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2])
    await db_session.commit()

    db_session.add(User(studio_id=s1.id, telegram_id=777))
    db_session.add(User(studio_id=s2.id, telegram_id=777))
    await db_session.commit()  # не должно падать

    users = (await db_session.execute(select(User))).scalars().all()
    assert len(users) == 2


@pytest.mark.asyncio
async def test_same_telegram_id_same_studio_rejected(db_session):
    s1 = Studio(slug="s1", name="S1")
    db_session.add(s1)
    await db_session.commit()
    db_session.add(User(studio_id=s1.id, telegram_id=777))
    await db_session.commit()
    db_session.add(User(studio_id=s1.id, telegram_id=777))
    with pytest.raises(Exception):
        await db_session.commit()
