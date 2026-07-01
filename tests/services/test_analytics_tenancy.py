"""AnalyticsService: studio-scoped isolation tests."""
import pytest
from datetime import datetime

from src.models.studio import Studio
from src.models.order import OrderStatus
from src.services.order_service import OrderService
from src.services.analytics_service import AnalyticsService


async def _two_studios(db_session):
    s1, s2 = Studio(slug="as1", name="Analytics S1"), Studio(slug="as2", name="Analytics S2")
    db_session.add_all([s1, s2])
    await db_session.commit()
    return s1, s2


async def _make_paid_order(db_session, studio_id: int, photos_cost: int = 1000):
    """Create a PAID order with given cost."""
    svc = OrderService(db_session, studio_id)
    user = await svc.get_or_create_user(telegram_id=9000 + studio_id, username="tester")
    order = await svc.create_order(user)
    # Set financial fields directly
    from sqlalchemy import update
    from src.models.order import Order
    await db_session.execute(
        update(Order).where(Order.id == order.id).values(
            status=OrderStatus.PAID,
            photos_cost=photos_cost,
            delivery_cost=0,
            discount=0,
        )
    )
    await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_analytics_revenue_scoped_by_studio(db_session):
    """Two studios have different paid orders — revenue is studio-isolated."""
    s1, s2 = await _two_studios(db_session)
    await _make_paid_order(db_session, s1.id, photos_cost=5000)
    await _make_paid_order(db_session, s2.id, photos_cost=9000)

    svc1 = AnalyticsService(db_session, s1.id)
    svc2 = AnalyticsService(db_session, s2.id)

    rev1 = await svc1.get_revenue_stats()
    rev2 = await svc2.get_revenue_stats()

    assert rev1["orders_count"] == 1
    assert rev2["orders_count"] == 1
    assert rev1["total_revenue"] == 5000
    assert rev2["total_revenue"] == 9000


@pytest.mark.asyncio
async def test_analytics_orders_by_status_scoped(db_session):
    """get_orders_by_status returns only own studio's orders."""
    s1, s2 = await _two_studios(db_session)
    await _make_paid_order(db_session, s1.id)

    svc1 = AnalyticsService(db_session, s1.id)
    svc2 = AnalyticsService(db_session, s2.id)

    status1 = await svc1.get_orders_by_status()
    status2 = await svc2.get_orders_by_status()

    # s1 has 1 paid order; s2 has 0
    assert sum(status1.values()) == 1
    assert sum(status2.values()) == 0


@pytest.mark.asyncio
async def test_dashboard_summary_scoped(db_session):
    """dashboard_summary revenue reflects only own studio."""
    s1, s2 = await _two_studios(db_session)
    await _make_paid_order(db_session, s1.id, photos_cost=3000)
    await _make_paid_order(db_session, s1.id, photos_cost=2000)
    await _make_paid_order(db_session, s2.id, photos_cost=7777)

    svc1 = AnalyticsService(db_session, s1.id)
    summary = await svc1.get_dashboard_summary()

    # s1 has 2 paid orders totaling 5000; s2's 7777 must not appear
    month_orders = summary["revenue"]["month_orders"]
    month_revenue = summary["revenue"]["month"]
    assert month_orders == 2
    assert month_revenue == 5000


@pytest.mark.asyncio
async def test_conversion_stats_scoped(db_session):
    """get_conversion_stats counts only own studio's orders."""
    s1, s2 = await _two_studios(db_session)
    await _make_paid_order(db_session, s1.id)

    svc1 = AnalyticsService(db_session, s1.id)
    svc2 = AnalyticsService(db_session, s2.id)

    conv1 = await svc1.get_conversion_stats()
    conv2 = await svc2.get_conversion_stats()

    assert conv1["total_paid"] == 1
    assert conv2["total_paid"] == 0
