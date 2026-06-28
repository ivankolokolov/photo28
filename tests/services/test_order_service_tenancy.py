"""Изоляция OrderService по студии."""
import pytest

from src.models.studio import Studio
from src.services.order_service import OrderService


async def _two_studios(db_session):
    s1, s2 = Studio(slug="s1", name="S1"), Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2])
    await db_session.commit()
    return s1, s2


@pytest.mark.asyncio
async def test_get_or_create_user_is_scoped(db_session):
    s1, s2 = await _two_studios(db_session)
    svc1 = OrderService(db_session, studio_id=s1.id)
    svc2 = OrderService(db_session, studio_id=s2.id)

    u1 = await svc1.get_or_create_user(telegram_id=777, first_name="A")
    u2 = await svc2.get_or_create_user(telegram_id=777, first_name="A")
    # Один и тот же telegram_id, но РАЗНЫЕ пользователи в разных студиях
    assert u1.id != u2.id
    assert u1.studio_id == s1.id
    assert u2.studio_id == s2.id


@pytest.mark.asyncio
async def test_orders_isolated_between_studios(db_session):
    s1, s2 = await _two_studios(db_session)
    svc1 = OrderService(db_session, studio_id=s1.id)
    svc2 = OrderService(db_session, studio_id=s2.id)

    u1 = await svc1.get_or_create_user(telegram_id=1, first_name="A")
    order1 = await svc1.create_order(u1)
    from src.models.order import OrderStatus
    await svc1.update_order_status(order1, OrderStatus.PAID)

    # Студия 2 не видит заказ студии 1
    assert await svc2.get_order_by_id(order1.id) is None
    assert len(await svc2.get_all_orders()) == 0
    assert len(await svc1.get_all_orders()) == 1
