"""update_photo_crop привязан к заказу — нельзя переписать кроп чужого заказа."""
import pytest

from src.models.studio import Studio
from src.models.user import User
from src.models.product import Product
from src.models.order import Order, OrderStatus
from src.models.photo import Photo
from src.services.order_service import OrderService


async def _order_with_photo(db_session, studio, telegram_id=1):
    user = User(studio_id=studio.id, telegram_id=telegram_id)
    db_session.add(user)
    await db_session.commit()
    product = Product(studio_id=studio.id, slug=f"p{telegram_id}", name="P", short_name="P")
    db_session.add(product)
    order = Order(studio_id=studio.id, user_id=user.id,
                  order_number=f"240101-{telegram_id:04d}", status=OrderStatus.DRAFT)
    db_session.add(order)
    await db_session.commit()
    photo = Photo(order_id=order.id, product_id=product.id, telegram_file_id="f", position=0)
    db_session.add(photo)
    await db_session.commit()
    return order, photo


@pytest.mark.asyncio
async def test_update_photo_crop_rejects_foreign_order(db_session):
    s1 = Studio(slug="s1", name="S1"); s2 = Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2]); await db_session.commit()
    order_a, photo_a = await _order_with_photo(db_session, s1, telegram_id=1)
    order_b, _ = await _order_with_photo(db_session, s2, telegram_id=2)

    svc_b = OrderService(db_session, s2.id)
    # Пытаемся переписать кроп фото заказа A, подставив order_id заказа B → отказ
    result = await svc_b.update_photo_crop(photo_a.id, order_id=order_b.id, crop_data="HACK")
    assert result is None
    await db_session.refresh(photo_a)
    assert photo_a.crop_data != "HACK"
    assert photo_a.crop_confirmed is False


@pytest.mark.asyncio
async def test_update_photo_crop_works_for_own_order(db_session):
    s1 = Studio(slug="s1", name="S1"); db_session.add(s1); await db_session.commit()
    order_a, photo_a = await _order_with_photo(db_session, s1, telegram_id=1)
    svc = OrderService(db_session, s1.id)
    result = await svc.update_photo_crop(photo_a.id, order_id=order_a.id, crop_data="OK")
    assert result is not None
    assert result.crop_data == "OK"
    assert result.crop_confirmed is True
