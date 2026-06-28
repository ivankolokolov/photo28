"""Тесты тенантности Order."""
import pytest
from sqlalchemy import select

from src.models.studio import Studio
from src.models.user import User
from src.models.order import Order, OrderStatus


async def _studio_user(db_session, slug):
    s = Studio(slug=slug, name=slug)
    db_session.add(s)
    await db_session.commit()
    u = User(studio_id=s.id, telegram_id=1)
    db_session.add(u)
    await db_session.commit()
    return s, u


@pytest.mark.asyncio
async def test_same_order_number_two_studios_allowed(db_session):
    s1, u1 = await _studio_user(db_session, "s1")
    s2, u2 = await _studio_user(db_session, "s2")
    db_session.add(Order(studio_id=s1.id, user_id=u1.id, order_number="240101-AAAA"))
    db_session.add(Order(studio_id=s2.id, user_id=u2.id, order_number="240101-AAAA"))
    await db_session.commit()
    assert len((await db_session.execute(select(Order))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_same_order_number_same_studio_rejected(db_session):
    s1, u1 = await _studio_user(db_session, "s1")
    db_session.add(Order(studio_id=s1.id, user_id=u1.id, order_number="240101-AAAA"))
    await db_session.commit()
    db_session.add(Order(studio_id=s1.id, user_id=u1.id, order_number="240101-AAAA"))
    with pytest.raises(Exception):
        await db_session.commit()
