"""Тест модели BillingEvent."""
from decimal import Decimal
from datetime import datetime
import pytest
from sqlalchemy import select

from src.models.studio import Studio
from src.models.user import User
from src.models.order import Order, OrderStatus
from src.models.billing_event import BillingEvent


@pytest.mark.asyncio
async def test_create_billing_event(db_session):
    studio = Studio(slug="s1", name="S1")
    db_session.add(studio)
    await db_session.commit()
    user = User(studio_id=studio.id, telegram_id=1)
    db_session.add(user)
    await db_session.commit()
    order = Order(studio_id=studio.id, user_id=user.id, order_number="240101-AAAA",
                  status=OrderStatus.CONFIRMED)
    db_session.add(order)
    await db_session.commit()

    ev = BillingEvent(
        studio_id=studio.id, order_id=order.id, photo_position=0,
        fee=Decimal("5.00"), printed_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    db_session.add(ev)
    await db_session.commit()

    loaded = (await db_session.execute(select(BillingEvent))).scalar_one()
    assert loaded.studio_id == studio.id
    assert loaded.fee == Decimal("5.00")
