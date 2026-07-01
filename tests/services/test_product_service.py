"""Тесты пер-студийного кеша товаров."""
import pytest

from src.models.studio import Studio
from src.models.product import Product
from src.services.product_service import ProductService


async def _two_studios_with_products(db_session):
    s1, s2 = Studio(slug="s1", name="S1"), Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2])
    await db_session.commit()
    db_session.add(Product(studio_id=s1.id, slug="a", name="A", short_name="A",
                           price_per_unit=25, is_active=True))
    db_session.add(Product(studio_id=s2.id, slug="b", name="B", short_name="B",
                           price_per_unit=40, is_active=True))
    await db_session.commit()
    return s1, s2


@pytest.mark.asyncio
async def test_top_level_is_per_studio(db_session):
    ProductService.invalidate_cache()
    s1, s2 = await _two_studios_with_products(db_session)
    svc = ProductService(db_session)
    await svc.load_cache(s1.id)
    await svc.load_cache(s2.id)

    s1_slugs = [p.slug for p in ProductService.get_top_level_products(s1.id)]
    s2_slugs = [p.slug for p in ProductService.get_top_level_products(s2.id)]
    assert s1_slugs == ["a"]
    assert s2_slugs == ["b"]


@pytest.mark.asyncio
async def test_update_product_wrong_studio_returns_none(db_session):
    """update_product с чужим studio_id возвращает None, товар не меняется."""
    ProductService.invalidate_cache()
    s1, s2 = await _two_studios_with_products(db_session)
    svc = ProductService(db_session)

    # Найдём товар s2 (slug="b") и попытаемся обновить от имени s1
    products_s2 = await svc.get_all_products(s2.id)
    prod_b = products_s2[0]

    result = await svc.update_product(prod_b.id, studio_id=s1.id, name="HACKED")
    assert result is None

    fresh = await svc.get_product_by_id(prod_b.id)
    assert fresh.name == "B"  # не изменилось


@pytest.mark.asyncio
async def test_delete_product_wrong_studio_returns_false(db_session):
    """delete_product с чужим studio_id возвращает False, товар жив."""
    ProductService.invalidate_cache()
    s1, s2 = await _two_studios_with_products(db_session)
    svc = ProductService(db_session)

    products_s2 = await svc.get_all_products(s2.id)
    prod_b = products_s2[0]

    result = await svc.delete_product(prod_b.id, studio_id=s1.id)
    assert result is False

    still_alive = await svc.get_product_by_id(prod_b.id)
    assert still_alive is not None


@pytest.mark.asyncio
async def test_toggle_product_wrong_studio_returns_none(db_session):
    """toggle_product с чужим studio_id возвращает None, статус не меняется."""
    ProductService.invalidate_cache()
    s1, s2 = await _two_studios_with_products(db_session)
    svc = ProductService(db_session)

    products_s2 = await svc.get_all_products(s2.id)
    prod_b = products_s2[0]
    original_active = prod_b.is_active

    result = await svc.toggle_product(prod_b.id, studio_id=s1.id)
    assert result is None

    fresh = await svc.get_product_by_id(prod_b.id)
    assert fresh.is_active == original_active


@pytest.mark.asyncio
async def test_update_delete_toggle_own_studio_works(db_session):
    """update/delete/toggle работают для своей студии."""
    ProductService.invalidate_cache()
    s1, s2 = await _two_studios_with_products(db_session)
    svc = ProductService(db_session)

    products_s1 = await svc.get_all_products(s1.id)
    prod_a = products_s1[0]
    original_active = prod_a.is_active

    # update own
    updated = await svc.update_product(prod_a.id, studio_id=s1.id, name="Updated A")
    assert updated is not None
    assert updated.name == "Updated A"

    # toggle own
    toggled = await svc.toggle_product(prod_a.id, studio_id=s1.id)
    assert toggled is not None
    assert toggled.is_active != original_active

    # delete own
    ok = await svc.delete_product(prod_a.id, studio_id=s1.id)
    assert ok is True
    gone = await svc.get_product_by_id(prod_a.id)
    assert gone is None
