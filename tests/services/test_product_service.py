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
